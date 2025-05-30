import asyncio
import json
import logging
import warnings
from typing import Any, List, Union, AsyncGenerator

from langchain_community.utilities import SQLDatabase
from langchain_core.language_models import BaseLLM
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, AIMessageChunk

from apps.ai_model.model_factory import LLMConfig, LLMFactory, get_llm_config
from apps.chat.curd.chat import save_question, save_full_sql_message, save_full_sql_message_and_answer
from apps.chat.models.chat_model import ChatQuestion, ChatRecord
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import exec_sql
from apps.system.models.system_model import AiModelDetail
from common.core.deps import SessionDep, CurrentUser

warnings.filterwarnings("ignore")


class LLMService:
    ds: CoreDatasource
    chat_question: ChatQuestion
    record: ChatRecord
    config: LLMConfig
    llm: BaseLLM
    sql_message: List[Union[BaseMessage, dict[str, Any]]] = []
    chart_message: List[Union[BaseMessage, dict[str, Any]]] = []

    def __init__(self, chat_question: ChatQuestion, history_records: List[ChatRecord],
                 ds: CoreDatasource, aimodel: AiModelDetail):
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

        last_sql_messages: List[dict[str, Any]] = json.loads(last_sql_message_str)
        if last_sql_messages is None or len(last_sql_messages) == 0:
            # add sys prompt
            self.sql_message.append(SystemMessage(content=self.chat_question.sql_sys_question()))
        else:
            for last_sql_message in last_sql_messages:
                _msg: BaseMessage
                if last_sql_message['type'] == 'human':
                    _msg = HumanMessage(content=last_sql_message['content'])
                elif last_sql_message['type'] == 'ai':
                    _msg = AIMessage(content=last_sql_message['content'])
                else:
                    _msg = SystemMessage(content=last_sql_message['content'])
                self.sql_message.append(_msg)

        last_chart_messages: List[dict[str, Any]] = json.loads(last_chart_message_str)
        if last_chart_messages is None or len(last_chart_messages) == 0:
            # add sys prompt
            self.chart_message.append(SystemMessage(content=self.chat_question.chart_sys_question()))
        else:
            for last_chart_message in last_chart_messages:
                _msg: BaseMessage
                if last_chart_message['type'] == 'human':
                    _msg = HumanMessage(content=last_chart_message['content'])
                elif last_chart_message['type'] == 'ai':
                    _msg = AIMessage(content=last_chart_message['content'])
                else:
                    _msg = SystemMessage(content=last_chart_message['content'])
                self.chart_message.append(_msg)

    def init_record(self, session: SessionDep, current_user: CurrentUser) -> ChatRecord:
        self.record = save_question(session=session, current_user=current_user, question=self.chat_question)
        return self.record

    def generate_sql(self, session: SessionDep):
        # append current question
        self.sql_message.append(HumanMessage(self.chat_question.sql_user_question()))
        self.record = save_full_sql_message(session=session, record_id=self.record.id,
                                            full_message=json.dumps(
                                                [{'type': msg.type, 'content': msg.content} for msg in
                                                 self.sql_message], ensure_ascii=False))
        full_text = ''
        res = self.llm.stream(self.sql_message)
        for chunk in res:
            if isinstance(chunk, dict):
                full_text += chunk['content']
                yield chunk['content']
                continue
            if isinstance(chunk, AIMessageChunk):
                full_text += chunk.content
                yield chunk.content
                continue

        print(full_text)
        self.sql_message.append(AIMessage(full_text))
        self.record = save_full_sql_message_and_answer(session=session, record_id=self.record.id,
                                                       answer=full_text,
                                                       full_message=json.dumps(
                                                           [{'type': msg.type, 'content': msg.content} for msg in
                                                            self.sql_message], ensure_ascii=False))

    async def async_generate(self, question: str, schema: str) -> AsyncGenerator[str, None]:

        chain = self.prompt | self.agent_executor
        # schema = self.db.get_table_info()

        # schema_engine = SchemaEngine(engine=self.db._engine)
        # mschema = schema_engine.mschema
        # mschema_str = mschema.to_mschema()

        # async for chunk in chain.astream({"schema": mschema_str, "question": question}):
        for chunk in chain.stream({"schema": schema, "question": question}):
            if not isinstance(chunk, dict):
                continue

            if "agent" in chunk:
                messages = chunk["agent"].get("messages", [])
                for msg in messages:
                    if tool_calls := msg.additional_kwargs.get("tool_calls"):
                        for tool_call in tool_calls:
                            response = {
                                "type": "tool_call",
                                "tool": tool_call["function"]["name"],
                                "args": tool_call["function"]["arguments"]
                            }
                            yield f"data: {json.dumps(response, ensure_ascii=False)}\n\n"

                    if content := msg.content:
                        html_start = content.find("```html")
                        html_end = content.find("```", html_start + 6)
                        if html_start != -1 and html_end != -1:
                            html_content = content[html_start + 7:html_end].strip()
                            response = {
                                "type": "final",
                                "content": content.split("```html")[0].strip(),
                                "html": html_content
                            }
                        else:
                            response = {
                                "type": "final",
                                "content": content
                            }
                        yield f"data: {json.dumps(response, ensure_ascii=False)}\n\n"

            if "tools" in chunk:
                messages = chunk["tools"].get("messages", [])
                for msg in messages:
                    response = {
                        "type": "tool_result",
                        "tool": msg.name,
                        "content": msg.content
                    }
                    yield f"data: {json.dumps(response, ensure_ascii=False)}\n\n"

            await asyncio.sleep(0.1)

        yield f"data: {json.dumps({'type': 'complete'})}\n\n"


def execute_sql(ds: CoreDatasource, sql: str) -> str:
    """Execute SQL query

    Args:
        ds: Data source instance
        sql: SQL query statement

    Returns:
        Query results
    """
    print(f"Executing SQL on ds_id {ds.id}: {sql}")
    return exec_sql(ds, sql)


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
