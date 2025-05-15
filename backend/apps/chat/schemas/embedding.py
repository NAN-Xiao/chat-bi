import os
from typing import List, Dict, Tuple, Optional
from sqlalchemy import inspect, text
from sqlmodel import SQLModel, create_engine, Session
from langchain_openai import OpenAIEmbeddings
from langchain.vectorstores import PGVector
from langchain.schema import Document
import logging
from apps.chat.schemas.chat_base_schema import LLMConfig
from common.core.config import settings
from common.core.db import engine

class SchemaEmbeddingManager:
    def __init__(self, config: LLMConfig):
        """Initialize SchemaEmbeddingManager
        
        Args:
            db_uri: Database connection URI in format postgresql://user:password@host:port/database
            embedding_model: Embedding model to use
        """
        # self.db_uri = db_uri
        self.embedding_model = OpenAIEmbeddings(
            model=config.model_name,
            openai_api_base=config.api_base_url,
            api_key=config.api_key
        )
        # self.engine = self._create_engine()
        self.engine = engine
        self._setup_vector_extension()
        
    
    def _setup_vector_extension(self):
        """Set up PgVector extension using SQLModel"""
        try:
            with Session(self.engine) as session:
                # Enable vector extension
                session.exec(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                session.commit()
                
                # Create vector type if needed
                session.exec(text("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vector') THEN
                            CREATE TYPE vector AS (x float8[]);
                        END IF;
                    END
                    $$;
                """))
                session.commit()
                logging.info("Vector extension setup completed successfully")
        except Exception as e:
            logging.error(f"Failed to setup vector extension: {str(e)}")
            raise

    def get_session(self) -> Session:
        """Get a new database session"""
        return Session(self.engine)
    
    def extract_schema_info(self, schema_name: str = "public") -> List[Dict]:
        """
        Extract database schema information and structure it
        
        Args:
            schema_name: Schema name to extract, defaults to public
            
        Returns:
            List of dictionaries containing schema information
        """
        metadata = SQLModel.metadata
        metadata.reflect(bind=self.engine, schema=schema_name)
        
        schema_info = []
        inspector = inspect(self.engine)
        
        for table_name in inspector.get_table_names(schema=schema_name):
            table = metadata.tables[f"{schema_name}.{table_name}"]
            table_comment = inspector.get_table_comment(table_name, schema=schema_name)
            
            # Table-level information
            table_info = {
                "type": "table",
                "schema": schema_name,
                "name": table_name,
                "description": table_comment.get('text') if table_comment else f"Table {table_name} in schema {schema_name}",
                "columns": []
            }
            
            # Column-level information
            for column in inspector.get_columns(table_name, schema=schema_name):
                col_name = column['name']
                # Get column comment directly from column info
                col_comment = column.get('comment', f"Column {col_name} in table {table_name}")
                
                column_info = {
                    "type": "column",
                    "schema": schema_name,
                    "table": table_name,
                    "name": col_name,
                    "data_type": str(column['type']),
                    "description": col_comment,
                    "is_primary_key": col_name in [pk['name'] for pk in inspector.get_pk_constraint(table_name, schema=schema_name).get('constrained_columns', [])],
                    "foreign_key": None  # Will be updated below
                }
                
                # Get foreign key information
                for fk in inspector.get_foreign_keys(table_name, schema=schema_name):
                    if col_name in fk['constrained_columns']:
                        column_info["foreign_key"] = f"{fk['referred_table']}.{fk['referred_columns'][0]}"
                        break
                        
                table_info["columns"].append(column_info)
            
            schema_info.append(table_info)
        
        return schema_info
    
    def generate_schema_documents(self, schema_info: List[Dict]) -> List[Document]:
        """
        Convert schema information into LangChain Document objects
        
        Args:
            schema_info: Schema information from extract_schema_info
            
        Returns:
            List of LangChain Document objects
        """
        documents = []
        
        for table in schema_info:
            # Table-level document
            table_content = f"Table {table['schema']}.{table['name']}: {table['description']}. "
            table_content += f"Contains columns: {', '.join(col['name'] for col in table['columns'])}"
            
            table_doc = Document(
                page_content=table_content,
                metadata={
                    "type": "table",
                    "schema": table["schema"],
                    "name": table["name"],
                    "description": table["description"],
                    "full_name": f"{table['schema']}.{table['name']}"
                }
            )
            documents.append(table_doc)
            
            # Column-level documents
            for column in table["columns"]:
                column_content = f"Column {table['schema']}.{table['name']}.{column['name']}: {column['description']}. "
                column_content += f"Data type: {column['data_type']}. "
                if column["is_primary_key"]:
                    column_content += "This is a primary key. "
                if column["foreign_key"]:
                    column_content += f"Foreign key to {column['foreign_key']}."
                
                column_doc = Document(
                    page_content=column_content,
                    metadata={
                        "type": "column",
                        "schema": table["schema"],
                        "table": table["name"],
                        "name": column["name"],
                        "description": column["description"],
                        "data_type": column["data_type"],
                        "full_name": f"{table['schema']}.{table['name']}.{column['name']}"
                    }
                )
                documents.append(column_doc)
        
        return documents
    
    def store_embeddings(self, documents: List[Document], collection_name: str = "schema_embeddings"):
        """Store schema document embeddings in PgVector
        
        Args:
            documents: Documents from generate_schema_documents
            collection_name: Vector collection name
        """
        try:
            PGVector.from_documents(
                embedding=self.embedding_model,
                documents=documents,
                collection_name=collection_name,
                connection_string=self.db_uri,
                pre_delete_collection=True  # Optionally recreate collection
            )
            logging.info(f"Successfully stored {len(documents)} embeddings in collection {collection_name}")
        except Exception as e:
            logging.error(f"Failed to store embeddings: {str(e)}")
            raise
    
    def get_relevant_schema(
        self, 
        query: str, 
        collection_name: str = "schema_embeddings", 
        top_k: int = 5
    ) -> Tuple[List[Dict], List[Dict]]:
        """Get relevant schema information based on user query
        
        Args:
            query: User query text
            collection_name: Vector collection name
            top_k: Number of most relevant items to return
            
        Returns:
            Tuple containing (relevant_tables_list, relevant_columns_list)
        """
        try:
            store = PGVector(
                collection_name=collection_name,
                connection_string=self.db_uri,
                embedding_function=self.embedding_model,
            )
            
            # Execute similarity search
            docs = store.similarity_search_with_score(query, k=top_k)
            
            relevant_tables = []
            relevant_columns = []
            seen_tables = set()
            
            for doc, score in docs:
                metadata = doc.metadata
                item = {
                    "name": metadata["full_name"],
                    "description": metadata["description"],
                    "type": metadata["type"],
                    "score": float(score)
                }
                
                if metadata["type"] == "table" and metadata["full_name"] not in seen_tables:
                    relevant_tables.append(item)
                    seen_tables.add(metadata["full_name"])
                elif metadata["type"] == "column":
                    relevant_columns.append(item)
                    # Ensure associated table is also included
                    table_name = f"{metadata['schema']}.{metadata['table']}"
                    if table_name not in seen_tables:
                        relevant_tables.append({
                            "name": table_name,
                            "description": f"Table containing column {metadata['name']}",
                            "type": "table",
                            "score": float(score) * 0.9  # Slightly lower table score
                        })
                        seen_tables.add(table_name)
            
            return relevant_tables, relevant_columns
            
        except Exception as e:
            logging.error(f"Error during schema search: {str(e)}")
            raise
    
    def generate_schema_context(self, relevant_tables: List[Dict], relevant_columns: List[Dict]) -> str:
        """
        Generate concise schema context for LLM usage
        
        Args:
            relevant_tables: List of relevant tables
            relevant_columns: List of relevant columns
            
        Returns:
            Formatted schema context string
        """
        context = "## Relevant Database Schema Information:\n\n"
        
        if relevant_tables:
            context += "### Tables:\n"
            for table in sorted(relevant_tables, key=lambda x: -x["score"]):
                context += f"- {table['name']}: {table['description']} (relevance score: {table['score']:.2f})\n"
        
        if relevant_columns:
            context += "\n### Columns:\n"
            for column in sorted(relevant_columns, key=lambda x: -x["score"]):
                context += f"- {column['name']}: {column['description']} (relevance score: {column['score']:.2f})\n"
        
        return context
