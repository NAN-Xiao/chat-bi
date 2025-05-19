import json
import urllib.parse
from typing import Any

from sqlalchemy import create_engine, text, Result
from sqlalchemy.orm import sessionmaker

from apps.datasource.models.datasource import DatasourceConf, CoreDatasource, TableSchema, ColumnSchema
from apps.datasource.utils.utils import aes_decrypt


def get_uri(ds: CoreDatasource):
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration)))
    db_url: str
    if ds.type == "mysql":
        if conf.extraJdbc is not None and conf.extraJdbc != '':
            db_url = f"mysql+pymysql://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{urllib.parse.quote(conf.database)}?{urllib.parse.quote(conf.extraJdbc)}"
        else:
            db_url = f"mysql+pymysql://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{urllib.parse.quote(conf.database)}"
    elif ds.type == "sqlServer":
        if conf.extraJdbc is not None and conf.extraJdbc != '':
            db_url = f"mssql+pymssql://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{urllib.parse.quote(conf.database)}?{urllib.parse.quote(conf.extraJdbc)}"
        else:
            db_url = f"mssql+pymssql://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{urllib.parse.quote(conf.database)}"
    else:
        raise 'The datasource type not support.'
    return db_url


def get_session(ds: CoreDatasource):
    engine = create_engine(get_uri(ds))
    session_maker = sessionmaker(bind=engine)
    session = session_maker()
    return session


def get_tables(ds: CoreDatasource):
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration)))
    session = get_session(ds)
    result: Result[Any]
    sql: str = ''
    try:
        if ds.type == "mysql":
            sql = f"""
                    SELECT 
                        TABLE_NAME, 
                        TABLE_COMMENT
                    FROM 
                        information_schema.TABLES
                    WHERE 
                        TABLE_SCHEMA = '{conf.database}';
                    """
        elif ds.type == "sqlServer":
            sql = f"""
                    SELECT 
                        TABLE_NAME AS [TABLE_NAME],
                        ISNULL(ep.value, '') AS [TABLE_COMMENT]
                    FROM 
                        INFORMATION_SCHEMA.TABLES t
                    LEFT JOIN 
                        sys.extended_properties ep 
                        ON ep.major_id = OBJECT_ID(t.TABLE_SCHEMA + '.' + t.TABLE_NAME)
                        AND ep.minor_id = 0 
                        AND ep.name = 'MS_Description' 
                    WHERE 
                        t.TABLE_TYPE IN ('BASE TABLE', 'VIEW')
                        AND t.TABLE_SCHEMA = '{conf.dbSchema}';
                    """

        result = session.execute(text(sql))
        res = result.fetchall()
        res_list = [TableSchema(*item) for item in res]
        return res_list
    finally:
        if result is not None:
            result.close()
        if session is not None:
            session.close()


def get_fields(ds: CoreDatasource, table_name: str = None):
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration)))
    session = get_session(ds)
    result: Result[Any]
    sql: str = ''
    try:
        if ds.type == "mysql":
            sql1 = f"""
                    SELECT 
                        COLUMN_NAME,
                        DATA_TYPE,
                        COLUMN_COMMENT
                    FROM 
                        INFORMATION_SCHEMA.COLUMNS
                    WHERE 
                        TABLE_SCHEMA = '{conf.database}'
                    """
            sql2 = f" AND TABLE_NAME = '{table_name}';" if table_name is not None and table_name != "" else ";"
            sql = sql1 + sql2
        elif ds.type == "sqlServer":
            sql1 = f"""
                    SELECT 
                        COLUMN_NAME AS [COLUMN_NAME],
                        DATA_TYPE AS [DATA_TYPE],
                        ISNULL(EP.value, '') AS [COLUMN_COMMENT]
                    FROM 
                        INFORMATION_SCHEMA.COLUMNS C
                    LEFT JOIN 
                        sys.extended_properties EP 
                        ON EP.major_id = OBJECT_ID(C.TABLE_SCHEMA + '.' + C.TABLE_NAME)
                        AND EP.minor_id = C.ORDINAL_POSITION
                        AND EP.name = 'MS_Description'
                    WHERE 
                        C.TABLE_SCHEMA = '{conf.dbSchema}'
                    """
            sql2 = f"AND C.TABLE_NAME = '{table_name}';" if table_name is not None and table_name != "" else ";"
            sql = sql1 + sql2

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
