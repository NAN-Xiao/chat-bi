import logging
import warnings
from typing import Any, List, Union, Dict

import orjson
from langchain_community.utilities import SQLDatabase
from langchain_core.language_models import BaseLLM
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, AIMessageChunk

from apps.ai_model.model_factory import LLMConfig, LLMFactory, get_llm_config
from apps.chat.curd.chat import save_question, save_full_sql_message, save_full_sql_message_and_answer, save_sql, \
    save_error_message, save_sql_exec_data, save_full_chart_message, save_full_chart_message_and_answer, save_chart, \
    finish_record, save_full_analysis_message_and_answer, save_full_predict_message_and_answer, save_predict_data
from apps.chat.models.chat_model import ChatQuestion, ChatRecord
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import exec_sql
from apps.system.models.system_model import AiModelDetail
from common.core.deps import SessionDep, CurrentUser

warnings.filterwarnings("ignore")

base_message_count_limit = 5


class LLMService:
    ds: CoreDatasource
    chat_question: ChatQuestion
    record: ChatRecord
    config: LLMConfig
    llm: BaseLLM
    sql_message: List[Union[BaseMessage, dict[str, Any]]] = []
    chart_message: List[Union[BaseMessage, dict[str, Any]]] = []

    def __init__(self, chat_question: ChatQuestion, aimodel: AiModelDetail, history_records: List[ChatRecord] = [],
                 ds: CoreDatasource = None):
        self.ds = ds
        self.chat_question = chat_question
        self.config = get_llm_config(aimodel)

        # Create LLM instance through factory
        llm_instance = LLMFactory.create_llm(self.config)
        self.llm = llm_instance.llm

        # self.agent_executor = create_react_agent(self.llm)
        last_sql_messages = list(
            filter(lambda r: True if r.full_sql_message is not None and r.full_sql_message.strip() != '' else False,
                   history_records))
        last_sql_message_str = "[]" if last_sql_messages is None or len(last_sql_messages) == 0 else last_sql_messages[
            -1].full_sql_message

        last_chart_messages = list(
            filter(
                lambda r: True if r.full_chart_message is not None and r.full_chart_message.strip() != '' else False,
                history_records))
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

    def init_record(self, session: SessionDep, current_user: CurrentUser) -> ChatRecord:
        self.record = save_question(session=session, current_user=current_user, question=self.chat_question)
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

    def generate_analysis(self, session: SessionDep):
        fields = self.get_fields_from_chart()

        self.chat_question.fields = orjson.dumps(fields).decode()
        self.chat_question.data = orjson.dumps(orjson.loads(self.record.data).get('data')).decode()
        analysis_msg: List[Union[BaseMessage, dict[str, Any]]] = []
        analysis_msg.append(SystemMessage(content=self.chat_question.analysis_sys_question()))
        analysis_msg.append(HumanMessage(content=self.chat_question.analysis_user_question()))

        history_msg = []
        if self.record.full_analysis_message and self.record.full_analysis_message.strip() != '':
            history_msg = orjson.loads(self.record.full_analysis_message)

        self.record = save_full_analysis_message_and_answer(session=session, record_id=self.record.id, answer='',
                                                            full_message=orjson.dumps(history_msg +
                                                                                      [{'type': msg.type,
                                                                                        'content': msg.content} for msg
                                                                                       in
                                                                                       analysis_msg]).decode())

        full_analysis_text = ''
        res = self.llm.stream(analysis_msg)
        for chunk in res:
            print(chunk)
            if isinstance(chunk, dict):
                full_analysis_text += chunk['content']
                yield chunk['content']
                continue
            if isinstance(chunk, AIMessageChunk):
                full_analysis_text += chunk.content
                yield chunk.content
                continue

        analysis_msg.append(AIMessage(full_analysis_text))
        self.record = save_full_analysis_message_and_answer(session=session, record_id=self.record.id,
                                                            answer=full_analysis_text,
                                                            full_message=orjson.dumps(history_msg +
                                                                                      [{'type': msg.type,
                                                                                        'content': msg.content} for msg
                                                                                       in
                                                                                       analysis_msg]).decode())

    def generate_predict(self, session: SessionDep):
        fields = self.get_fields_from_chart()

        self.chat_question.fields = orjson.dumps(fields).decode()
        self.chat_question.data = orjson.dumps(orjson.loads(self.record.data).get('data')).decode()
        predict_msg: List[Union[BaseMessage, dict[str, Any]]] = []
        predict_msg.append(SystemMessage(content=self.chat_question.predict_sys_question()))
        predict_msg.append(HumanMessage(content=self.chat_question.predict_user_question()))

        history_msg = []
        if self.record.full_predict_message and self.record.full_predict_message.strip() != '':
            history_msg = orjson.loads(self.record.full_predict_message)

        self.record = save_full_predict_message_and_answer(session=session, record_id=self.record.id, answer='',
                                                           data='',
                                                           full_message=orjson.dumps(history_msg +
                                                                                     [{'type': msg.type,
                                                                                       'content': msg.content} for msg
                                                                                      in
                                                                                      predict_msg]).decode())

        full_predict_text = ''
        res = self.llm.stream(predict_msg)
        for chunk in res:
            print(chunk)
            if isinstance(chunk, dict):
                full_predict_text += chunk['content']
                yield chunk['content']
                continue
            if isinstance(chunk, AIMessageChunk):
                full_predict_text += chunk.content
                yield chunk.content
                continue

        predict_msg.append(AIMessage(full_predict_text))
        self.record = save_full_predict_message_and_answer(session=session, record_id=self.record.id,
                                                           answer=full_predict_text, data='',
                                                           full_message=orjson.dumps(history_msg +
                                                                                     [{'type': msg.type,
                                                                                       'content': msg.content} for msg
                                                                                      in
                                                                                      predict_msg]).decode())

    def generate_sql(self, session: SessionDep):
        # append current question
        self.sql_message.append(HumanMessage(self.chat_question.sql_user_question()))
        self.record = save_full_sql_message(session=session, record_id=self.record.id,
                                            full_message=orjson.dumps(
                                                [{'type': msg.type, 'content': msg.content} for msg in
                                                 self.sql_message]).decode())
        full_sql_text = ''
        res = self.llm.stream(self.sql_message)
        for chunk in res:
            print(chunk)
            if isinstance(chunk, dict):
                full_sql_text += chunk['content']
                yield chunk['content']
                continue
            if isinstance(chunk, AIMessageChunk):
                full_sql_text += chunk.content
                yield chunk.content
                continue

        self.sql_message.append(AIMessage(full_sql_text))
        self.record = save_full_sql_message_and_answer(session=session, record_id=self.record.id,
                                                       answer=full_sql_text,
                                                       full_message=orjson.dumps(
                                                           [{'type': msg.type, 'content': msg.content} for msg in
                                                            self.sql_message]).decode())

    def generate_chart(self, session: SessionDep):
        # append current question
        self.chart_message.append(HumanMessage(self.chat_question.chart_user_question()))
        self.record = save_full_chart_message(session=session, record_id=self.record.id,
                                              full_message=orjson.dumps(
                                                  [{'type': msg.type, 'content': msg.content} for msg in
                                                   self.chart_message]).decode())
        full_chart_text = ''
        res = self.llm.stream(self.chart_message)
        for chunk in res:
            if isinstance(chunk, dict):
                full_chart_text += chunk['content']
                yield chunk['content']
                continue
            if isinstance(chunk, AIMessageChunk):
                full_chart_text += chunk.content
                yield chunk.content
                continue

        self.chart_message.append(AIMessage(full_chart_text))
        self.record = save_full_chart_message_and_answer(session=session, record_id=self.record.id,
                                                         answer=full_chart_text,
                                                         full_message=orjson.dumps(
                                                             [{'type': msg.type, 'content': msg.content} for msg in
                                                              self.chart_message]).decode())

    def check_save_sql(self, session: SessionDep, res: str) -> str:

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

        save_sql(session=session, sql=sql, record_id=self.record.id)

        self.chat_question.sql = sql

        return sql

    def check_save_chart(self, session: SessionDep, res: str) -> Dict[str, Any]:

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

        save_chart(session=session, chart=orjson.dumps(chart).decode(), record_id=self.record.id)

        return chart

    def check_save_predict_data(self, session: SessionDep, res: str) -> Dict[str, Any]:

        json_str = extract_nested_json(res)

        if not json_str:
            json_str = ''

        save_predict_data(session=session, record_id=self.record.id, data=json_str)

        return json_str

    def save_error(self, session: SessionDep, message: str):
        return save_error_message(session=session, record_id=self.record.id, message=message)

    def save_sql_data(self, session: SessionDep, data_obj: Dict[str, Any]):
        return save_sql_exec_data(session=session, record_id=self.record.id,
                                  data=orjson.dumps(data_obj).decode())

    def finish(self, session: SessionDep):
        return finish_record(session=session, record_id=self.record.id)

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


def extract_nested_json(text):
    stack = []
    start_index = -1
    results = []

    for i, char in enumerate(text):
        if char in '{[':
            if not stack:  # 记录起始位置
                start_index = i
            stack.append(char)
        elif char in '}]':
            if stack and ((char == '}' and stack[-1] == '{') or (char == ']' and stack[-1] == '[')):
                stack.pop()
                if not stack:  # 栈空时截取完整JSON
                    json_str = text[start_index:i + 1]
                    try:
                        orjson.loads(json_str)  # 验证有效性
                        results.append(json_str)
                    except:
                        pass
            else:
                stack = []  # 括号不匹配则重置
    if len(results) > 0 and results[0]:
        return results[0]
    return None


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
