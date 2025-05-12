from sqlalchemy import create_engine, text, Result
from sqlalchemy.orm import sessionmaker
from apps.datasource.models.datasource import DatasourceConf, CoreDatasource, TableSchema
import urllib.parse
from typing import Any


def get_session(conf: DatasourceConf, ds: CoreDatasource):
    db_url: str
    if ds.type == "mysql":
        db_url = f"mysql+pymysql://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{urllib.parse.quote(conf.database)}"
    else:
        raise 'The datasource type not support.'
    engine = create_engine(db_url)
    session_maker = sessionmaker(bind=engine)
    session = session_maker()
    return session


def get_tables(conf: DatasourceConf, ds: CoreDatasource):
    session = get_session(conf, ds)
    result: Result[Any]
    if ds.type == "mysql":
        sql = f"""SELECT 
                        TABLE_NAME AS `Table Name`, 
                        TABLE_COMMENT AS `Table Comment`
                    FROM 
                        information_schema.TABLES
                    WHERE 
                        TABLE_SCHEMA = '{conf.database}';"""
        result = session.execute(text(sql))

    res = result.fetchall()
    res_list = [TableSchema(*item) for item in res]
    return res_list


def get_fields(conf: DatasourceConf, ds: CoreDatasource):
    session = get_session(conf, ds)
    result: Result[Any]
    pass
