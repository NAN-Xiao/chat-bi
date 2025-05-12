from langchain_community.utilities import SQLDatabase
# from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.llms import Tongyi
from langchain_core.prompts import ChatPromptTemplate
from apps.chat.schemas.chat_base_schema import LLMConfig, LLMFactory
from common.core.config import settings
import warnings

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

