# 作者：Junjun
# 日期：2025/5/19
import urllib.parse
from typing import List

from sqlalchemy import create_engine, text, MetaData, Table
from sqlalchemy.orm import sessionmaker

from apps.datasource.models.datasource import DatasourceConf
from common.core.config import settings


def get_engine_config():
    """
    是什么：get_engine_config 是 backend/apps/db/engine.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询数据库访问相关数据，整理后返回给调用方。
    """
    return DatasourceConf(username=settings.core_db_user, password=settings.core_db_password,
                          host=settings.core_db_host, port=settings.core_db_port, database=settings.core_db_name,
                          dbSchema="public", timeout=30) # 读取引擎配置


def get_engine_uri(conf: DatasourceConf):
    """
    是什么：get_engine_uri 是 backend/apps/db/engine.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询数据库访问相关数据，整理后返回给调用方。
    """
    return f"postgresql+psycopg2://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{urllib.parse.quote(conf.database)}"


def get_engine_conn():
    """
    是什么：get_engine_conn 是 backend/apps/db/engine.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询数据库访问相关数据，整理后返回给调用方。
    """
    conf = get_engine_config()
    db_url = get_engine_uri(conf)
    engine = create_engine(db_url,
                           connect_args={"options": f"-c search_path={conf.dbSchema}", "connect_timeout": conf.timeout},
                           pool_timeout=conf.timeout)
    return engine


def get_data_engine():
    """
    是什么：get_data_engine 是 backend/apps/db/engine.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询数据库访问相关数据，整理后返回给调用方。
    """
    engine = get_engine_conn()
    session_maker = sessionmaker(bind=engine)
    session = session_maker()
    return session


def create_table(session, table_name: str, fields: List[any]):
    # 字段类型映射关系
    """
    是什么：create_table 是 backend/apps/db/engine.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装数据库访问相关对象和数据，并返回或写入对应状态。
    """
    list = []
    for f in fields:
        if "object" in f["type"]:
            f["relType"] = "text"
        elif "int" in f["type"]:
            f["relType"] = "bigint"
        elif "float" in f["type"]:
            f["relType"] = "numeric"
        elif "datetime" in f["type"]:
            f["relType"] = "timestamp"
        else:
            f["relType"] = "text"
        list.append(f'"{f["name"]}" {f["relType"]}')

    sql = f"""
            CREATE TABLE "{table_name}" (
                {", ".join(list)}
            );
            """
    session.execute(text(sql))
    session.commit()


def insert_data(session, table_name: str, fields: List[any], data: List[any]):
    """
    是什么：insert_data 是 backend/apps/db/engine.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装数据库访问相关对象和数据，并返回或写入对应状态。
    """
    engine = get_engine_conn()
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    with engine.connect() as conn:
        stmt = table.insert().values(data)
        conn.execute(stmt)
        conn.commit()
