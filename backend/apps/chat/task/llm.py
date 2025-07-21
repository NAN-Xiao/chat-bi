import json
import sqlparse
import logging
import traceback
import warnings
from typing import Any, List, Optional, Union, Dict

import numpy as np
import orjson
import pandas as pd
import requests
from langchain.chat_models.base import BaseChatModel
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, BaseMessageChunk
from sqlalchemy import and_, cast, or_
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import load_only
from sqlbot_xpack.permissions.api.permission import transRecord2DTO
from sqlbot_xpack.permissions.models.ds_permission import DsPermission, PermissionDTO
from sqlbot_xpack.permissions.models.ds_rules import DsRules

from apps.ai_model.model_factory import LLMConfig, LLMFactory, get_default_config
from apps.chat.curd.chat import save_question, save_full_sql_message, save_full_sql_message_and_answer, save_sql, \
    save_error_message, save_sql_exec_data, save_full_chart_message, save_full_chart_message_and_answer, save_chart, \
    finish_record, save_full_analysis_message_and_answer, save_full_predict_message_and_answer, save_predict_data, \
    save_full_select_datasource_message_and_answer, save_full_recommend_question_message_and_answer, \
    get_old_questions, save_analysis_predict_record, list_base_records, rename_chat
from apps.chat.models.chat_model import ChatQuestion, ChatRecord, Chat, RenameChat
from apps.datasource.crud.datasource import get_table_schema
from apps.datasource.crud.row_permission import transFilterTree
from apps.datasource.models.datasource import CoreDatasource, CoreTable
from apps.db.db import exec_sql
from apps.system.crud.assistant import AssistantOutDs, get_assistant_ds
from common.core.config import settings
from common.core.deps import CurrentAssistant, SessionDep, CurrentUser
from common.utils.utils import extract_nested_json

warnings.filterwarnings("ignore")

base_message_count_limit = 5


class LLMService:
    ds: CoreDatasource
    chat_question: ChatQuestion
    record: ChatRecord
    config: LLMConfig
    llm: BaseChatModel
    sql_message: List[Union[BaseMessage, dict[str, Any]]] = []
    chart_message: List[Union[BaseMessage, dict[str, Any]]] = []
    history_records: List[ChatRecord] = []
    session: SessionDep
    current_user: CurrentUser
    current_assistant: Optional[CurrentAssistant] = None
    assistant_certificate: str
    out_ds_instance: Optional[AssistantOutDs] = None
    change_title: bool = False

    def __init__(self, session: SessionDep, current_user: CurrentUser, chat_question: ChatQuestion,
                 current_assistant: Optional[CurrentAssistant] = None):

        self.session = session
        self.current_user = current_user
        self.current_assistant = current_assistant
        if chat_question.assistant_certificate:
            self.assistant_certificate = chat_question.assistant_certificate
        # chat = self.session.query(Chat).filter(Chat.id == chat_question.chat_id).first()
        chat_id = chat_question.chat_id
        chat: Chat = self.session.get(Chat, chat_id)
        if not chat:
            raise Exception(f"Chat with id {chat_id} not found")
        ds: CoreDatasource | None = None
        if chat.datasource:
            # Get available datasource
            # ds = self.session.query(CoreDatasource).filter(CoreDatasource.id == chat.datasource).first()
            ds = self.session.get(CoreDatasource, chat.datasource)
            if not ds:
                raise Exception("No available datasource configuration found")

            chat_question.engine = ds.type_name if ds.type != 'excel' else 'PostgreSQL'

        history_records: List[ChatRecord] = list(
            map(lambda x: ChatRecord(**x.model_dump()), filter(lambda r: True if r.first_chat != True else False,
                                                               list_base_records(session=self.session,
                                                                                 current_user=current_user,
                                                                                 chart_id=chat_id))))
        self.change_title = len(history_records) == 0

        # get schema
        if ds:
            chat_question.db_schema = get_table_schema(session=self.session, current_user=current_user, ds=ds)

        chat_question.lang = current_user.language

        self.ds = CoreDatasource(**ds.model_dump()) if ds else None
        self.chat_question = chat_question
        self.config = get_default_config()
        self.chat_question.ai_modal_id = self.config.model_id

        # Create LLM instance through factory
        llm_instance = LLMFactory.create_llm(self.config)
        self.llm = llm_instance.llm

        self.history_records = history_records

        self.init_messages()

    def init_messages(self):
        # self.agent_executor = create_react_agent(self.llm)
        last_sql_messages = list(
            filter(lambda r: True if r.full_sql_message is not None and r.full_sql_message.strip() != '' else False,
                   self.history_records))
        last_sql_message_str = "[]" if last_sql_messages is None or len(last_sql_messages) == 0 else last_sql_messages[
            -1].full_sql_message

        last_chart_messages = list(
            filter(
                lambda r: True if r.full_chart_message is not None and r.full_chart_message.strip() != '' else False,
                self.history_records))
        last_chart_message_str = "[]" if last_chart_messages is None or len(last_chart_messages) == 0 else \
            last_chart_messages[-1].full_chart_message

        last_sql_messages: List[dict[str, Any]] = orjson.loads(last_sql_message_str)

        # todo maybe can configure
        count_limit = 0 - base_message_count_limit

        self.sql_message = []
        if last_sql_messages is None or len(last_sql_messages) == 0:
            # add sys prompt
            self.sql_message.append(SystemMessage(content=self.chat_question.sql_sys_question()))
        else:
            # limit count
            for last_sql_message in last_sql_messages:
                if last_sql_message['type'] == 'system':
                    _msg = SystemMessage(content=last_sql_message['content'])
                    self.sql_message.append(_msg)
                    break
            for last_sql_message in last_sql_messages[count_limit:]:
                _msg: BaseMessage
                if last_sql_message['type'] == 'human':
                    _msg = HumanMessage(content=last_sql_message['content'])
                    self.sql_message.append(_msg)
                elif last_sql_message['type'] == 'ai':
                    _msg = AIMessage(content=last_sql_message['content'])
                    self.sql_message.append(_msg)

        last_chart_messages: List[dict[str, Any]] = orjson.loads(last_chart_message_str)

        self.chart_message = []
        if last_chart_messages is None or len(last_chart_messages) == 0:
            # add sys prompt
            self.chart_message.append(SystemMessage(content=self.chat_question.chart_sys_question()))
        else:
            # limit count
            for last_chart_message in last_chart_messages:
                if last_chart_message['type'] == 'system':
                    _msg = SystemMessage(content=last_chart_message['content'])
                    self.chart_message.append(_msg)
                    break
            for last_chart_message in last_chart_messages:
                _msg: BaseMessage
                if last_chart_message['type'] == 'human':
                    _msg = HumanMessage(content=last_chart_message['content'])
                    self.chart_message.append(_msg)
                elif last_chart_message['type'] == 'ai':
                    _msg = AIMessage(content=last_chart_message['content'])
                    self.chart_message.append(_msg)

    def init_record(self) -> ChatRecord:
        self.record = save_question(session=self.session, current_user=self.current_user, question=self.chat_question)
        return self.record

    def get_record(self):
        return self.record

    def set_record(self, record: ChatRecord):
        self.record = record

    def get_fields_from_chart(self):
        chart_info = orjson.loads(self.record.chart)
        fields = []
        if chart_info.get('columns') and len(chart_info.get('columns')) > 0:
            for column in chart_info.get('columns'):
                column_str = column.get('value')
                if column.get('value') != column.get('name'):
                    column_str = column_str + '(' + column.get('name') + ')'
                fields.append(column_str)
        if chart_info.get('axis'):
            for _type in ['x', 'y', 'series']:
                if chart_info.get('axis').get(_type):
                    column = chart_info.get('axis').get(_type)
                    column_str = column.get('value')
                    if column.get('value') != column.get('name'):
                        column_str = column_str + '(' + column.get('name') + ')'
                    fields.append(column_str)
        return fields

    def generate_analysis(self):
        fields = self.get_fields_from_chart()

        self.chat_question.fields = orjson.dumps(fields).decode()
        self.chat_question.data = orjson.dumps(orjson.loads(self.record.data).get('data')).decode()
        analysis_msg: List[Union[BaseMessage, dict[str, Any]]] = []
        analysis_msg.append(SystemMessage(content=self.chat_question.analysis_sys_question()))
        analysis_msg.append(HumanMessage(content=self.chat_question.analysis_user_question()))

        history_msg = []
        if self.record.full_analysis_message and self.record.full_analysis_message.strip() != '':
            history_msg = orjson.loads(self.record.full_analysis_message)

        self.record = save_full_analysis_message_and_answer(session=self.session, record_id=self.record.id, answer='',
                                                            full_message=orjson.dumps(history_msg +
                                                                                      [{'type': msg.type,
                                                                                        'content': msg.content} for msg
                                                                                       in
                                                                                       analysis_msg]).decode())
        full_thinking_text = ''
        full_analysis_text = ''
        res = self.llm.stream(analysis_msg)
        token_usage = {}
        for chunk in res:
            print(chunk)
            reasoning_content_chunk = ''
            if 'reasoning_content' in chunk.additional_kwargs:
                reasoning_content_chunk = chunk.additional_kwargs.get('reasoning_content', '')
            # else:
            #     reasoning_content_chunk = chunk.get('reasoning_content')
            if reasoning_content_chunk is None:
                reasoning_content_chunk = ''
            full_thinking_text += reasoning_content_chunk

            full_analysis_text += chunk.content
            yield {'content': chunk.content, 'reasoning_content': reasoning_content_chunk}
            get_token_usage(chunk, token_usage)

        analysis_msg.append(AIMessage(full_analysis_text))
        self.record = save_full_analysis_message_and_answer(session=self.session, record_id=self.record.id,
                                                            token_usage=token_usage,
                                                            answer=orjson.dumps({'content': full_analysis_text,
                                                                                 'reasoning_content': full_thinking_text}).decode(),
                                                            full_message=orjson.dumps(history_msg +
                                                                                      [{'type': msg.type,
                                                                                        'content': msg.content} for msg
                                                                                       in
                                                                                       analysis_msg]).decode())

    def generate_predict(self):
        fields = self.get_fields_from_chart()

        self.chat_question.fields = orjson.dumps(fields).decode()
        self.chat_question.data = orjson.dumps(orjson.loads(self.record.data).get('data')).decode()
        predict_msg: List[Union[BaseMessage, dict[str, Any]]] = []
        predict_msg.append(SystemMessage(content=self.chat_question.predict_sys_question()))
        predict_msg.append(HumanMessage(content=self.chat_question.predict_user_question()))

        history_msg = []
        if self.record.full_predict_message and self.record.full_predict_message.strip() != '':
            history_msg = orjson.loads(self.record.full_predict_message)

        self.record = save_full_predict_message_and_answer(session=self.session, record_id=self.record.id, answer='',
                                                           data='',
                                                           full_message=orjson.dumps(history_msg +
                                                                                     [{'type': msg.type,
                                                                                       'content': msg.content} for msg
                                                                                      in
                                                                                      predict_msg]).decode())
        full_thinking_text = ''
        full_predict_text = ''
        res = self.llm.stream(predict_msg)
        token_usage = {}
        for chunk in res:
            print(chunk)
            reasoning_content_chunk = ''
            if 'reasoning_content' in chunk.additional_kwargs:
                reasoning_content_chunk = chunk.additional_kwargs.get('reasoning_content', '')
            # else:
            #     reasoning_content_chunk = chunk.get('reasoning_content')
            if reasoning_content_chunk is None:
                reasoning_content_chunk = ''
            full_thinking_text += reasoning_content_chunk

            full_predict_text += chunk.content
            yield {'content': chunk.content, 'reasoning_content': reasoning_content_chunk}
            get_token_usage(chunk, token_usage)

        predict_msg.append(AIMessage(full_predict_text))
        self.record = save_full_predict_message_and_answer(session=self.session, record_id=self.record.id,
                                                           token_usage=token_usage,
                                                           answer=orjson.dumps({'content': full_predict_text,
                                                                                'reasoning_content': full_thinking_text}).decode(),
                                                           data='',
                                                           full_message=orjson.dumps(history_msg +
                                                                                     [{'type': msg.type,
                                                                                       'content': msg.content} for msg
                                                                                      in
                                                                                      predict_msg]).decode())

    def generate_recommend_questions_task(self):

        # get schema
        if self.ds and not self.chat_question.db_schema:
            self.chat_question.db_schema = get_table_schema(session=self.session, current_user=self.current_user, ds=self.ds)

        guess_msg: List[Union[BaseMessage, dict[str, Any]]] = []
        guess_msg.append(SystemMessage(content=self.chat_question.guess_sys_question()))

        old_questions = list(map(lambda q: q[0].strip(), get_old_questions(self.session, self.record.datasource)))
        guess_msg.append(
            HumanMessage(content=self.chat_question.guess_user_question(orjson.dumps(old_questions).decode())))

        self.record = save_full_recommend_question_message_and_answer(session=self.session, record_id=self.record.id,
                                                                      full_message=orjson.dumps([{'type': msg.type,
                                                                                                  'content': msg.content}
                                                                                                 for msg
                                                                                                 in
                                                                                                 guess_msg]).decode())
        full_thinking_text = ''
        full_guess_text = ''
        token_usage = {}
        res = self.llm.stream(guess_msg)
        for chunk in res:
            print(chunk)
            reasoning_content_chunk = ''
            if 'reasoning_content' in chunk.additional_kwargs:
                reasoning_content_chunk = chunk.additional_kwargs.get('reasoning_content', '')
            # else:
            #     reasoning_content_chunk = chunk.get('reasoning_content')
            if reasoning_content_chunk is None:
                reasoning_content_chunk = ''
            full_thinking_text += reasoning_content_chunk

            full_guess_text += chunk.content
            yield {'content': chunk.content, 'reasoning_content': reasoning_content_chunk}
            get_token_usage(chunk, token_usage)

        guess_msg.append(AIMessage(full_guess_text))
        self.record = save_full_recommend_question_message_and_answer(session=self.session, record_id=self.record.id,
                                                                      token_usage=token_usage,
                                                                      answer={'content': full_guess_text,
                                                                              'reasoning_content': full_thinking_text},
                                                                      full_message=orjson.dumps([{'type': msg.type,
                                                                                                  'content': msg.content}
                                                                                                 for msg
                                                                                                 in
                                                                                                 guess_msg]).decode())
        yield {'recommended_question': self.record.recommended_question}

    def select_datasource(self):
        datasource_msg: List[Union[BaseMessage, dict[str, Any]]] = []
        datasource_msg.append(SystemMessage(self.chat_question.datasource_sys_question()))
        if self.current_assistant:
            _ds_list = get_assistant_ds(llm_service=self)
        else:
            oid: str = self.current_user.oid
            stmt = select(CoreDatasource.id, CoreDatasource.name, CoreDatasource.description).where(CoreDatasource.oid == oid)
            _ds_list = [
                {
                    "id": ds.id,
                    "name": ds.name,
                    "description": ds.description
                }
                for ds in self.session.exec(stmt)
            ]
            """ _ds_list = self.session.exec(select(CoreDatasource).options(
                load_only(CoreDatasource.id, CoreDatasource.name, CoreDatasource.description))).all() """
        _ds_list_dict = []
        for _ds in _ds_list:
            _ds_list_dict.append(_ds)
        datasource_msg.append(
            HumanMessage(self.chat_question.datasource_user_question(orjson.dumps(_ds_list_dict).decode())))

        history_msg = []
        if self.record.full_select_datasource_message and self.record.full_select_datasource_message.strip() != '':
            history_msg = orjson.loads(self.record.full_select_datasource_message)

        self.record = save_full_select_datasource_message_and_answer(session=self.session, record_id=self.record.id,
                                                                     answer='',
                                                                     full_message=orjson.dumps(history_msg +
                                                                                               [{'type': msg.type,
                                                                                                 'content': msg.content}
                                                                                                for msg
                                                                                                in
                                                                                                datasource_msg]).decode())
        full_thinking_text = ''
        full_text = ''
        token_usage = {}
        res = self.llm.stream(datasource_msg)
        for chunk in res:
            print(chunk)
            reasoning_content_chunk = ''
            if 'reasoning_content' in chunk.additional_kwargs:
                reasoning_content_chunk = chunk.additional_kwargs.get('reasoning_content', '')
            # else:
            #     reasoning_content_chunk = chunk.get('reasoning_content')
            if reasoning_content_chunk is None:
                reasoning_content_chunk = ''
            full_thinking_text += reasoning_content_chunk

            full_text += chunk.content
            yield {'content': chunk.content, 'reasoning_content': reasoning_content_chunk}
            get_token_usage(chunk, token_usage)
        datasource_msg.append(AIMessage(full_text))

        json_str = extract_nested_json(full_text)

        _error: Exception | None = None
        _datasource: int | None = None
        _engine_type: str | None = None
        try:
            data = orjson.loads(json_str)

            if data['id'] and data['id'] != 0:
                _datasource = data['id']
                _chat = self.session.get(Chat, self.record.chat_id)
                _chat.datasource = _datasource
                if self.current_assistant and self.current_assistant.type == 1:
                    _ds = self.out_ds_instance.get_ds(data['id'])
                    self.ds = _ds
                    self.chat_question.engine = _ds.type
                    _engine_type = self.chat_question.engine
                    _chat.engine_type =  _ds.type
                else:
                    _ds = self.session.get(CoreDatasource, _datasource)
                    if not _ds:
                        _datasource = None
                        raise Exception(f"Datasource configuration with id {_datasource} not found")
                    self.ds = CoreDatasource(**_ds.model_dump())
                    self.chat_question.engine = _ds.type_name if _ds.type != 'excel' else 'PostgreSQL'
                    _engine_type = self.chat_question.engine
                    _chat.engine_type = _ds.type_name
                # save chat
                self.session.add(_chat)
                self.session.flush()
                self.session.refresh(_chat)
                self.session.commit()

            elif data['fail']:
                raise Exception(data['fail'])
            else:
                raise Exception('No available datasource configuration found')

        except Exception as e:
            _error = e

        self.record = save_full_select_datasource_message_and_answer(session=self.session, record_id=self.record.id,
                                                                     answer=orjson.dumps({'content': full_text,
                                                                                          'reasoning_content': full_thinking_text}).decode(),
                                                                     datasource=_datasource,
                                                                     engine_type=_engine_type,
                                                                     full_message=orjson.dumps(history_msg +
                                                                                               [{'type': msg.type,
                                                                                                 'content': msg.content}
                                                                                                for msg
                                                                                                in
                                                                                                datasource_msg]).decode())
        self.init_messages()

        if _error:
            raise _error

    def generate_sql(self):
        # append current question
        self.sql_message.append(HumanMessage(self.chat_question.sql_user_question()))
        self.record = save_full_sql_message(session=self.session, record_id=self.record.id,
                                            full_message=orjson.dumps(
                                                [{'type': msg.type, 'content': msg.content} for msg in
                                                 self.sql_message]).decode())
        full_thinking_text = ''
        full_sql_text = ''
        token_usage = {}
        res = self.llm.stream(self.sql_message)
        for chunk in res:
            print(chunk)
            reasoning_content_chunk = ''
            if 'reasoning_content' in chunk.additional_kwargs:
                reasoning_content_chunk = chunk.additional_kwargs.get('reasoning_content', '')
            # else:
            #     reasoning_content_chunk = chunk.get('reasoning_content')
            if reasoning_content_chunk is None:
                reasoning_content_chunk = ''
            full_thinking_text += reasoning_content_chunk

            full_sql_text += chunk.content
            yield {'content': chunk.content, 'reasoning_content': reasoning_content_chunk}
            get_token_usage(chunk, token_usage)

        self.sql_message.append(AIMessage(full_sql_text))
        self.record = save_full_sql_message_and_answer(session=self.session, record_id=self.record.id,
                                                       token_usage=token_usage,
                                                       answer=orjson.dumps({'content': full_sql_text,
                                                                            'reasoning_content': full_thinking_text}).decode(),
                                                       full_message=orjson.dumps(
                                                           [{'type': msg.type, 'content': msg.content} for msg in
                                                            self.sql_message]).decode())

    def generate_filter(self, sql: str, tables: List):
        table_list = self.session.query(CoreTable).filter(
            and_(CoreTable.ds_id == self.ds.id, CoreTable.table_name.in_(tables))
        ).all()

        filters = []
        for table in table_list:
            row_permissions = self.session.query(DsPermission).filter(
                and_(DsPermission.table_id == table.id, DsPermission.type == 'row')).all()
            res: List[PermissionDTO] = []
            if row_permissions is not None:
                for permission in row_permissions:
                    # check permission and user in same rules
                    obj = self.session.query(DsRules).filter(
                        and_(DsRules.permission_list.op('@>')(cast([permission.id], JSONB)),
                             or_(DsRules.user_list.op('@>')(cast([f'{self.current_user.id}'], JSONB)),
                             DsRules.user_list.op('@>')(cast([self.current_user.id], JSONB))))
                    ).first()
                    if obj is not None:
                        res.append(transRecord2DTO(self.session, permission))
            wheres = transFilterTree(self.session, res, self.ds)
            filters.append({"table": table.table_name, "filter": wheres})

        filter = json.dumps(filters, ensure_ascii=False)

        self.chat_question.sql = sql
        self.chat_question.filter = filter
        msg: List[Union[BaseMessage, dict[str, Any]]] = []
        msg.append(SystemMessage(content=self.chat_question.filter_sys_question()))
        msg.append(HumanMessage(content=self.chat_question.filter_user_question()))

        history_msg = []
        # if self.record.full_analysis_message and self.record.full_analysis_message.strip() != '':
        #     history_msg = orjson.loads(self.record.full_analysis_message)

        # self.record = save_full_analysis_message_and_answer(session=self.session, record_id=self.record.id, answer='',
        #                                                     full_message=orjson.dumps(history_msg +
        #                                                                               [{'type': msg.type,
        #                                                                                 'content': msg.content} for msg
        #                                                                                in
        #                                                                                msg]).decode())
        full_thinking_text = ''
        full_filter_text = ''
        res = self.llm.stream(msg)
        token_usage = {}
        for chunk in res:
            print(chunk)
            reasoning_content_chunk = ''
            if 'reasoning_content' in chunk.additional_kwargs:
                reasoning_content_chunk = chunk.additional_kwargs.get('reasoning_content', '')
            # else:
            #     reasoning_content_chunk = chunk.get('reasoning_content')
            if reasoning_content_chunk is None:
                reasoning_content_chunk = ''
            full_thinking_text += reasoning_content_chunk

            full_filter_text += chunk.content
            # yield {'content': chunk.content, 'reasoning_content': reasoning_content_chunk}
            get_token_usage(chunk, token_usage)

        msg.append(AIMessage(full_filter_text))
        # self.record = save_full_analysis_message_and_answer(session=self.session, record_id=self.record.id,
        #                                                     token_usage=token_usage,
        #                                                     answer=orjson.dumps({'content': full_analysis_text,
        #                                                                          'reasoning_content': full_thinking_text}).decode(),
        #                                                     full_message=orjson.dumps(history_msg +
        #                                                                               [{'type': msg.type,
        #                                                                                 'content': msg.content} for msg
        #                                                                                in
        #                                                                                analysis_msg]).decode())
        print(full_filter_text)
        return full_filter_text

    def generate_chart(self):
        # append current question
        self.chart_message.append(HumanMessage(self.chat_question.chart_user_question()))
        self.record = save_full_chart_message(session=self.session, record_id=self.record.id,
                                              full_message=orjson.dumps(
                                                  [{'type': msg.type, 'content': msg.content} for msg in
                                                   self.chart_message]).decode())
        full_thinking_text = ''
        full_chart_text = ''
        token_usage = {}
        res = self.llm.stream(self.chart_message)
        for chunk in res:
            print(chunk)
            reasoning_content_chunk = ''
            if 'reasoning_content' in chunk.additional_kwargs:
                reasoning_content_chunk = chunk.additional_kwargs.get('reasoning_content', '')
            # else:
            #     reasoning_content_chunk = chunk.get('reasoning_content')
            if reasoning_content_chunk is None:
                reasoning_content_chunk = ''
            full_thinking_text += reasoning_content_chunk

            full_chart_text += chunk.content
            yield {'content': chunk.content, 'reasoning_content': reasoning_content_chunk}
            get_token_usage(chunk, token_usage)

        self.chart_message.append(AIMessage(full_chart_text))
        self.record = save_full_chart_message_and_answer(session=self.session, record_id=self.record.id,
                                                         token_usage=token_usage,
                                                         answer=orjson.dumps({'content': full_chart_text,
                                                                              'reasoning_content': full_thinking_text}).decode(),
                                                         full_message=orjson.dumps(
                                                             [{'type': msg.type, 'content': msg.content} for msg in
                                                              self.chart_message]).decode())

    def check_save_sql(self, res: str) -> str:

        json_str = extract_nested_json(res)
        data = orjson.loads(json_str)

        sql = ''
        message = ''
        error = False

        if data['success']:
            sql = data['sql']
        else:
            message = data['message']
            error = True

        if error:
            raise Exception(message)
        if sql.strip() == '':
            raise Exception("SQL query is empty")

        save_sql(session=self.session, sql=sql, record_id=self.record.id)

        self.chat_question.sql = sql

        return sql

    def check_save_chart(self, res: str) -> Dict[str, Any]:

        json_str = extract_nested_json(res)
        data = orjson.loads(json_str)

        chart: Dict[str, Any] = {}
        message = ''
        error = False

        if data['type'] and data['type'] != 'error':
            # todo type check
            chart = data
        elif data['type'] == 'error':
            message = data['reason']
            error = True
        else:
            message = 'Chart is empty'
            error = True

        if error:
            raise Exception(message)

        save_chart(session=self.session, chart=orjson.dumps(chart).decode(), record_id=self.record.id)

        return chart

    def check_save_predict_data(self, res: str) -> bool:

        json_str = extract_nested_json(res)

        if not json_str:
            json_str = ''

        save_predict_data(session=self.session, record_id=self.record.id, data=json_str)

        if json_str == '':
            return False

        return True

    def save_error(self, message: str):
        return save_error_message(session=self.session, record_id=self.record.id, message=message)

    def save_sql_data(self, data_obj: Dict[str, Any]):
        return save_sql_exec_data(session=self.session, record_id=self.record.id,
                                  data=orjson.dumps(data_obj).decode())

    def finish(self):
        return finish_record(session=self.session, record_id=self.record.id)

    def execute_sql(self, sql: str):
        """Execute SQL query

        Args:
            ds: Data source instance
            sql: SQL query statement

        Returns:
            Query results
        """
        print(f"Executing SQL on ds_id {self.ds.id}: {sql}")
        return exec_sql(self.ds, sql)


def execute_sql_with_db(db: SQLDatabase, sql: str) -> str:
    """Execute SQL query using SQLDatabase

    Args:
        db: SQLDatabase instance
        sql: SQL query statement

    Returns:
        str: Query results formatted as string
    """
    try:
        # Execute query
        result = db.run(sql)

        if not result:
            return "Query executed successfully but returned no results."

        # Format results
        return str(result)

    except Exception as e:
        error_msg = f"SQL execution failed: {str(e)}"
        logging.error(error_msg)
        raise RuntimeError(error_msg)


def run_task(llm_service: LLMService, in_chat: bool = True):
    try:
        # return id
        if in_chat:
            yield orjson.dumps({'type': 'id', 'id': llm_service.get_record().id}).decode() + '\n\n'

        # return title
        if llm_service.change_title:
            if llm_service.chat_question.question or llm_service.chat_question.question.strip() != '':
                brief = rename_chat(session=llm_service.session,
                                    rename_object=RenameChat(id=llm_service.get_record().chat_id,
                                                             brief=llm_service.chat_question.question.strip()[:20]))
                if in_chat:
                    yield orjson.dumps({'type': 'brief', 'brief': brief}).decode() + '\n\n'

        # select datasource if datasource is none
        if not llm_service.ds:
            ds_res = llm_service.select_datasource()

            for chunk in ds_res:
                print(chunk)
                if in_chat:
                    yield orjson.dumps(
                        {'content': chunk.get('content'), 'reasoning_content': chunk.get('reasoning_content'),
                         'type': 'datasource-result'}).decode() + '\n\n'
            if in_chat:
                yield orjson.dumps({'id': llm_service.ds.id, 'datasource_name': llm_service.ds.name,
                                    'engine_type': llm_service.ds.type_name or llm_service.ds.type, 'type': 'datasource'}).decode() + '\n\n'

            llm_service.chat_question.db_schema = llm_service.out_ds_instance.get_db_schema() if llm_service.out_ds_instance else get_table_schema(session=llm_service.session, current_user=llm_service.current_user, ds=llm_service.ds)

        # generate sql
        sql_res = llm_service.generate_sql()
        full_sql_text = ''
        for chunk in sql_res:
            full_sql_text += chunk.get('content')
            if in_chat:
                yield orjson.dumps(
                    {'content': chunk.get('content'), 'reasoning_content': chunk.get('reasoning_content'),
                     'type': 'sql-result'}).decode() + '\n\n'
        if in_chat:
            yield orjson.dumps({'type': 'info', 'msg': 'sql generated'}).decode() + '\n\n'

        # filter sql
        print(full_sql_text)

        # todo row permission
        sql_json_str = extract_nested_json(full_sql_text)
        data = orjson.loads(sql_json_str)

        sql = ''
        message = ''
        error = False
        if data['success']:
            sql = data['sql']
        else:
            message = data['message']
            error = True
        if error:
            raise Exception(message)
        if sql.strip() == '':
            raise Exception("SQL query is empty")

        sql_result = llm_service.generate_filter(data.get('sql'), data.get('tables'))  # maybe no sql and tables
        print(sql_result)
        sql = llm_service.check_save_sql(res=sql_result)
        # sql = llm_service.check_save_sql(res=full_sql_text)

        print(sql)
        format_sql = sqlparse.format(sql, reindent=True)
        if in_chat:
            yield orjson.dumps({'content': format_sql, 'type': 'sql'}).decode() + '\n\n'
        else:
            yield f'```sql\n{format_sql}\n```\n\n'

        # execute sql
        result = llm_service.execute_sql(sql=sql)
        llm_service.save_sql_data(data_obj=result)
        if in_chat:
            yield orjson.dumps({'content': 'execute-success', 'type': 'sql-data'}).decode() + '\n\n'

        # generate chart
        chart_res = llm_service.generate_chart()
        full_chart_text = ''
        for chunk in chart_res:
            full_chart_text += chunk.get('content')
            if in_chat:
                yield orjson.dumps(
                    {'content': chunk.get('content'), 'reasoning_content': chunk.get('reasoning_content'),
                     'type': 'chart-result'}).decode() + '\n\n'
        if in_chat:
            yield orjson.dumps({'type': 'info', 'msg': 'chart generated'}).decode() + '\n\n'

        # filter chart
        print(full_chart_text)
        chart = llm_service.check_save_chart(res=full_chart_text)
        print(chart)
        if in_chat:
            yield orjson.dumps({'content': orjson.dumps(chart).decode(), 'type': 'chart'}).decode() + '\n\n'
        else:
            data = []
            _fields = {}
            if chart.get('columns'):
                for _column in chart.get('columns'):
                    if _column:
                        _fields[_column.get('value')] = _column.get('name')
            if chart.get('axis'):
                if chart.get('axis').get('x'):
                    _fields[chart.get('axis').get('x').get('value')] = chart.get('axis').get('x').get('name')
                if chart.get('axis').get('y'):
                    _fields[chart.get('axis').get('y').get('value')] = chart.get('axis').get('y').get('name')
                if chart.get('axis').get('series'):
                    _fields[chart.get('axis').get('series').get('value')] = chart.get('axis').get('series').get('name')
            _fields_list = []
            _fields_skip = False
            for _data in result.get('data'):
                _row = []
                for field in result.get('fields'):
                    _row.append(_data.get(field))
                    if not _fields_skip:
                        _fields_list.append(field if not _fields.get(field) else _fields.get(field))
                data.append(_row)
                _fields_skip = True
            df = pd.DataFrame(np.array(data), columns=_fields_list)
            markdown_table = df.to_markdown(index=False)
            yield markdown_table + '\n\n'

        record = llm_service.finish()
        if in_chat:
            yield orjson.dumps({'type': 'finish'}).decode() + '\n\n'
        else:
            # todo generate picture
            if chart['type'] != 'table':
                yield '### generated chart picture\n\n'
                image_url = request_picture(llm_service.record.chat_id, llm_service.record.id, chart, result)
                print(image_url)
                yield f'![{chart["type"]}]({image_url})'
    except Exception as e:
        traceback.print_exc()
        llm_service.save_error(message=str(e))
        if in_chat:
            yield orjson.dumps({'content': str(e), 'type': 'error'}).decode() + '\n\n'
        else:
            yield f'> &#x274c; **ERROR**\n\n> \n\n> {str(e)}。'


def run_analysis_or_predict_task(llm_service: LLMService, action_type: str, base_record: ChatRecord):
    try:
        llm_service.set_record(save_analysis_predict_record(llm_service.session, base_record, action_type))

        yield orjson.dumps({'type': 'id', 'id': llm_service.get_record().id}).decode() + '\n\n'

        if action_type == 'analysis':
            # generate analysis
            analysis_res = llm_service.generate_analysis()
            for chunk in analysis_res:
                yield orjson.dumps(
                    {'content': chunk.get('content'), 'reasoning_content': chunk.get('reasoning_content'),
                     'type': 'analysis-result'}).decode() + '\n\n'
            yield orjson.dumps({'type': 'info', 'msg': 'analysis generated'}).decode() + '\n\n'

            yield orjson.dumps({'type': 'analysis_finish'}).decode() + '\n\n'

        elif action_type == 'predict':
            # generate predict
            analysis_res = llm_service.generate_predict()
            full_text = ''
            for chunk in analysis_res:
                yield orjson.dumps(
                    {'content': chunk.get('content'), 'reasoning_content': chunk.get('reasoning_content'),
                     'type': 'predict-result'}).decode() + '\n\n'
                full_text += chunk.get('content')
            yield orjson.dumps({'type': 'info', 'msg': 'predict generated'}).decode() + '\n\n'

            _data = llm_service.check_save_predict_data(res=full_text)
            if _data:
                yield orjson.dumps({'type': 'predict-success'}).decode() + '\n\n'
            else:
                yield orjson.dumps({'type': 'predict-failed'}).decode() + '\n\n'

            yield orjson.dumps({'type': 'predict_finish'}).decode() + '\n\n'

        llm_service.finish()
    except Exception as e:
        traceback.print_exc()
        llm_service.save_error(message=str(e))
        yield orjson.dumps({'content': str(e), 'type': 'error'}).decode() + '\n\n'
    finally:
        # end
        pass


def run_recommend_questions_task(llm_service: LLMService):
    res = llm_service.generate_recommend_questions_task()

    for chunk in res:
        if chunk.get('recommended_question'):
            yield orjson.dumps(
                {'content': chunk.get('recommended_question'), 'type': 'recommended_question'}).decode() + '\n\n'
        else:
            yield orjson.dumps(
                {'content': chunk.get('content'), 'reasoning_content': chunk.get('reasoning_content'),
                 'type': 'recommended_question_result'}).decode() + '\n\n'


def request_picture(chat_id: int, record_id: int, chart: dict, data: dict):
    file_name = f'c_{chat_id}_r_{record_id}'

    columns = chart.get('columns') if chart.get('columns') else []
    x = None
    y = None
    series = None
    if chart.get('axis'):
        x = chart.get('axis').get('x')
        y = chart.get('axis').get('y')
        series = chart.get('axis').get('series')

    axis = []
    for v in columns:
        axis.append({'name': v.get('name'), 'value': v.get('value')})
    if x:
        axis.append({'name': x.get('name'), 'value': x.get('value'), 'type': 'x'})
    if y:
        axis.append({'name': y.get('name'), 'value': y.get('value'), 'type': 'y'})
    if series:
        axis.append({'name': series.get('name'), 'value': series.get('value'), 'type': 'series'})

    request_obj = {
        "path": (settings.MCP_IMAGE_PATH if settings.MCP_IMAGE_PATH[-1] == '/' else (
                settings.MCP_IMAGE_PATH + '/')) + file_name,
        "type": chart['type'],
        "data": orjson.dumps(data.get('data') if data.get('data') else []).decode(),
        "axis": orjson.dumps(axis).decode(),
    }

    requests.post(url=settings.MCP_IMAGE_HOST, json=request_obj)

    return f'{(settings.SERVER_IMAGE_HOST if settings.SERVER_IMAGE_HOST[-1] == "/" else (settings.SERVER_IMAGE_HOST + "/"))}{file_name}.png'


def get_token_usage(chunk: BaseMessageChunk, token_usage: dict = {}):
    try:
        if chunk.usage_metadata:
            token_usage['input_tokens'] = chunk.usage_metadata.get('input_tokens')
            token_usage['output_tokens'] = chunk.usage_metadata.get('output_tokens')
            token_usage['total_tokens'] = chunk.usage_metadata.get('total_tokens')
    except Exception:
        pass
