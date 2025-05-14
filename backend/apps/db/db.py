from sqlalchemy import create_engine, text, Result
from sqlalchemy.orm import sessionmaker
from apps.datasource.models.datasource import DatasourceConf, CoreDatasource, TableSchema, ColumnSchema
import urllib.parse
from typing import Any
import json
from apps.datasource.utils.utils import aes_decrypt
from common.core.deps import SessionDep


def get_uri(ds: CoreDatasource):
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration)))
    db_url: str
    if ds.type == "mysql":
        db_url = f"mysql+pymysql://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{urllib.parse.quote(conf.database)}"
    else:
        raise 'The datasource type not support.'
    return db_url

def get_session(ds: CoreDatasource):
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration)))
    db_url: str
    if ds.type == "mysql":
        db_url = f"mysql+pymysql://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{urllib.parse.quote(conf.database)}"
    else:
        raise 'The datasource type not support.'
    engine = create_engine(db_url)
    session_maker = sessionmaker(bind=engine)
    session = session_maker()
    return session


def get_tables(ds: CoreDatasource):
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration)))
    session = get_session(ds)
    result: Result[Any]
    try:
        if ds.type == "mysql":
            sql = f"""SELECT 
                            TABLE_NAME, 
                            TABLE_COMMENT
                        FROM 
                            information_schema.TABLES
                        WHERE 
                            TABLE_SCHEMA = '{conf.database}';"""
            result = session.execute(text(sql))

        res = result.fetchall()
        res_list = [TableSchema(*item) for item in res]
        return res_list
    finally:
        if result is not None:
            result.close()
        if session is not None:
            session.close()


def get_fields(ds: CoreDatasource, table_name: str):
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration)))
    session = get_session(ds)
    result: Result[Any]
    try:
        if ds.type == "mysql":
            sql = f"""SELECT 
                            COLUMN_NAME,
                            DATA_TYPE,
                            COLUMN_COMMENT
                        FROM 
                            INFORMATION_SCHEMA.COLUMNS
                        WHERE 
                            TABLE_SCHEMA = '{conf.database}' AND
                            TABLE_NAME = '{table_name}';"""
            result = session.execute(text(sql))

        res = result.fetchall()
        res_list = [ColumnSchema(*item) for item in res]
        return res_list
    finally:
        if result is not None:
            result.close()
        if session is not None:
            session.close()


def exec_sql(ds: CoreDatasource, sql: str):
    session = get_session(ds)
    result = session.execute(text(sql))
    try:
        columns = result.keys()._keys
        res = result.fetchall()
        result_list = [
            {columns[i]: value for i, value in enumerate(tuple_item)}
            for tuple_item in res
        ]
        return {"fields": columns, "data": result_list}
    finally:
        if result is not None:
            result.close()
        if session is not None:
            session.close()

def exec_sql(ds: CoreDatasource, sql: str):
    ds = session.get(CoreDatasource, id)
    session = get_session(ds)
    result = session.execute(text(sql))
    try:
        columns = result.keys()._keys
        res = result.fetchall()
        result_list = [
            {columns[i]: value for i, value in enumerate(tuple_item)}
            for tuple_item in res
        ]
        return {"fields": columns, "data": result_list}
    finally:
        if result is not None:
            result.close()
        if session is not None:
            session.close()