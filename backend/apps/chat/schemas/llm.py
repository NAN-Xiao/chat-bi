from langchain_community.utilities import SQLDatabase
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate
from apps.chat.schemas.chat_base_schema import LLMConfig, LLMFactory
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import exec_sql, get_uri
from common.core.config import settings
import warnings
from langchain.tools import Tool
from functools import partial
import logging
from typing import AsyncGenerator
import json
import asyncio

warnings.filterwarnings("ignore")

class LLMService:
    def __init__(self, config: LLMConfig):
        # Initialize database connection
        self.db = SQLDatabase.from_uri(str(settings.SQLALCHEMY_DATABASE_URI))
        
        # Create LLM instance through factory
        llm_instance = LLMFactory.create_llm(config)
        self.llm = llm_instance.llm
        
        # Define prompt template
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a professional SQL engineer. Generate PostgreSQL SELECT queries based on the database schema and user questions.
            Data modification or deletion is prohibited. Table structure is as follows:
            {schema}
            """),
            ("human", "{question}")
        ])
    
    def generate_sql(self, question: str) -> str:
        chain = self.prompt | self.llm
        schema = self.db.get_table_info()
        return chain.invoke({"schema": schema, "question": question})


class AgentService:
    def __init__(self, config: LLMConfig, ds: CoreDatasource):
        # Initialize database connection
        self.ds = ds
        db_uri = get_uri(ds)
        self.db = SQLDatabase.from_uri(db_uri)
        # self.db = SQLDatabase.from_uri(str(settings.SQLALCHEMY_DATABASE_URI))
        
        # Create LLM instance through factory
        llm_instance = LLMFactory.create_llm(config)
        self.llm = llm_instance.llm
        
        # Create a partial function of execute_sql with preset ds parameter
        # bound_execute_sql = partial(execute_sql, self.ds)
        bound_execute_sql = partial(execute_sql_with_db, self.db)
        
        # Wrap as Tool object
        tools = [
            Tool(
                name="execute_sql",
                func=bound_execute_sql,
                description="""A tool for executing SQL queries.
                Input: SQL query statement (string)
                Output: Query results
                Example: "SELECT * FROM table_name LIMIT 5"
                """
            )
        ]
        
        self.agent_executor = create_react_agent(self.llm, tools)
        
        system_prompt = """
            You are an intelligent agent capable of data analysis. When users input their data analysis requirements, 
            you need to first convert the requirements into executable SQL, then execute the SQL through tools to return results, 
            and finally summarize the SQL query results. When all tasks are completed, you need to generate an HTML format data analysis report.
            
            You can analyze requirements step by step to determine the final SQL query to generate.
            To improve SQL generation accuracy, please evaluate the accuracy of the SQL after generation, 
            if there are issues, regenerate the SQL.
            When SQL execution fails, you need to correct the SQL based on the error message and try to execute again.
            
            ### Tools ###
            execute_sql: Can execute SQL by passing in SQL statements and return execution results
            """
        user_prompt = """
            Below is the database information I need to query:
            {schema}
            
            My requirement is: {question}
        """
        # Define prompt template
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", user_prompt)
        ])
    
    def generate_sql(self, question: str) -> str:
        chain = self.prompt | self.agent_executor
        schema = self.db.get_table_info()
        return chain.invoke({"schema": schema, "question": question})
    
    async def async_generate(self, question: str) -> AsyncGenerator[str, None]:
       
        chain = self.prompt | self.agent_executor
        schema = self.db.get_table_info()
        
        async for chunk in chain.astream({"schema": schema, "question": question}):
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