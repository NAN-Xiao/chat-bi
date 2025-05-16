import logging
from typing import Dict, List
from langchain.schema import Document
from langchain_openai import OpenAIEmbeddings
from langchain.vectorstores.pgvector import PGVector
from sqlalchemy import Tuple

from apps.chat.schemas.schema_engine import SchemaEngine
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import get_uri
from langchain_community.utilities import SQLDatabase
from sqlmodel import Session, select
from apps.system.models.system_model import AiModelDetail
from common.core.db import engine 
class DsEmbeddingManage:
    def __init__(self, ds: CoreDatasource):
        self.ds = ds
        db_uri = get_uri(ds)
        self.db = SQLDatabase.from_uri(db_uri)
        
        # Get AI model configuration from database
        with Session(engine) as session:
            aimodel = session.exec(select(AiModelDetail).where(
                AiModelDetail.status == True, 
                AiModelDetail.api_key.is_not(None)
            )).first()
            
            if not aimodel:
                raise RuntimeError("No available AI model configuration found")
        
        # Initialize embedding model with AI model config
        self.embedding_model = OpenAIEmbeddings(
            model=aimodel.name,
            openai_api_base=aimodel.endpoint if aimodel.endpoint else None,
            api_key=aimodel.api_key,
        )
    
    def getSchema(self):
        schema_engine = SchemaEngine(engine=self.db._engine)
        mschema = schema_engine.mschema
        mschema_str = mschema.to_mschema()
        return mschema_str

    def mschema_to_documents(self, mschema_str: str) -> List[Document]:
        """Convert M-Schema string to list of Documents
        
        Args:
            mschema_str: M-Schema format string
            
        Returns:
            List of Documents for vector storage
        """
        docs = []
        current_table = ""
        table_content = []
        table_line = ""
        current_table_col_docs = []
        # Split schema into lines
        lines = mschema_str.split('\n')
        
        for line in lines:
            # Skip empty lines and header sections
            if not line.strip() or line.startswith('【'):
                continue
                
            # Process table header
            if line.startswith('# Table:'):
                # Store previous table if exists
                if current_table and table_content:
                    doc_content = f"Table: {current_table}\n" + '\n'.join(table_content)
                    table_doc = Document(
                        page_content=doc_content,
                        metadata={
                            "type": "table",
                            "name": current_table,
                            "origin": table_line
                        }
                    )
                    docs.append(table_doc)
                    docs.extend(current_table_col_docs)
                   
                # Start new table
                current_table = line.split('# Table: ')[1].split(',')[0].strip()
                table_content = []
                current_table_col_docs = []
                table_line = line 
                # If there's a table comment, add it
                if ',' in line:
                    table_content.append(f"Description: {line.split(',')[1].strip()}. Contains columns: ")
                continue
            
            # Add column information to current table
            if line.strip() and not line.startswith('[') and not line.startswith(']') and line.startswith('('):
                # Clean up the line
                column_line = line.strip('(),')
                column_info_list = column_line.split(',')
                column_name = column_info_list[0].split(':')[0]
                table_content.append(column_name + ",\n")
                column_content = column_line
                
                column_doc = Document(
                    page_content=column_content,
                    metadata = {
                        "type": "column",
                        "name": column_name,
                        "table": current_table,
                        "origin": line
                    }
                )
                current_table_col_docs.append(column_doc)
                
        
        # Don't forget to add the last table
        if current_table and table_content:
            doc_content = f"Table: {current_table}\n" + '\n'.join(table_content)
            docs.append(Document(
                page_content=doc_content,
                metadata={
                    "type": "table",
                    "name": current_table,
                    "origin": table_line
                }
            ))
            docs.extend(current_table_col_docs)
        
        return docs

    def store_schema_embeddings(self):
        """Store schema embeddings in PGVector"""
        try:
            # Get schema string
            mschema_str = self.getSchema()
            
            # Convert to documents
            docs = self.mschema_to_documents(mschema_str)
            # print(docs)
            # Store in PGVector
            PGVector.from_documents(
                embedding=self.embedding_model,
                documents=docs,
                collection_name="schema_embeddings",
                connection_string=str(self.db._engine.url),
                pre_delete_collection=True
            )
            
            return f"Successfully stored {len(docs)} schema documents in vector store"
            
        except Exception as e:
            raise RuntimeError(f"Failed to store schema embeddings: {str(e)}")

    def get_relevant_schema(
        self, 
        query: str, 
        collection_name: str = "schema_embeddings", 
        top_k: int = 5
    ) -> List[Dict]:
        """Get relevant schema information based on user query
        
        Args:
            query: User query text
            collection_name: Vector collection name
            top_k: Number of most relevant items to return
            
        Returns:
            List of dictionaries containing relevant schema information
        """
        try:
            store = PGVector(
                collection_name=collection_name,
                connection_string=str(self.db._engine.url),
                embedding_function=self.embedding_model,
            )
            
            # Execute similarity search
            docs = store.similarity_search_with_score(query, k=top_k)
            
            relevant_tables = {}
            
            for doc, score in docs:
                metadata = doc.metadata
                item = {
                    "name": metadata["name"],
                    "type": metadata["type"],
                    "origin": metadata["origin"],
                    "score": float(score)
                }
                
                if metadata["type"] == "table":
                    table_name = metadata["name"]
                    item["columns"] = []
                    if table_name not in relevant_tables:
                        relevant_tables[table_name] = item
                    else:
                        relevant_tables[table_name]["score"] = max(relevant_tables[table_name]["score"], item["score"])
                        relevant_tables[table_name]["origin"] = item["origin"]

                elif metadata["type"] == "column":
                    table_name = f"{metadata['table']}"
                    if table_name not in relevant_tables:
                        relevant_tables[table_name] = {
                            "name": table_name,
                            "type": "table",
                            "score": float(score) * 0.9,
                            "columns": [item]
                        }
                    else:
                        relevant_tables[table_name]["columns"].append(item)
            
            # Convert dictionary to sorted list
            relevant_tables_list = list(relevant_tables.values())
            # Sort by score in descending order
            relevant_tables_list.sort(key=lambda x: x["score"], reverse=True)
            
            return relevant_tables_list
            
        except Exception as e:
            logging.error(f"Error during schema search: {str(e)}")
            raise
        
    def generate_schema_context(self, relevant_tables_list: List[Dict]) -> str:
       
        context = "## Relevant Database Schema Information:\n\n【Schema】\n"
        
        if relevant_tables_list:
            for table in sorted(relevant_tables_list, key=lambda x: -x["score"]):
                if table['origin'] is not None:
                    context += f"\n{table['origin']}"
                else:
                    context += f"# Table: {table['name']}"
                context += f" (relevance score: {table['score']:.2f})\n"
                
                columns: List[Dict] = table["columns"]
                # context += f"[\n{',\n'.join(f'({column["origin"].strip('(),')} , relevance score: {column["score"]:.2f})' for column in columns)}]\n"
                context += "\n[\n" + ",\n".join(column["origin"] for column in columns) + "\n]\n"
        return context
    
    def get_schema_with_query(self, 
        query: str, 
        collection_name: str = "schema_embeddings", 
        top_k: int = 5):
        list = self.get_relevant_schema(query, collection_name, top_k)
        context = self.generate_schema_context(list)
        print(context)
        return context
    
    def execute(self):
        """Main execution method"""
        return self.store_schema_embeddings()


