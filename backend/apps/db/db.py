"""
脚本说明：这个脚本放数据库连接相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import base64
import json
import os
import platform
import re
import urllib.parse
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from typing import Optional, List

import oracledb
import psycopg2
import pymssql

from apps.db.db_sql import get_table_sql, get_field_sql, get_version_sql
from common.error import ParseSQLResultError

if platform.system() != "Darwin":
    import dmPython
import pymysql
import redshift_connector
from sqlalchemy import create_engine, text, Engine
from sqlalchemy.orm import sessionmaker

from apps.datasource.models.datasource import DatasourceConf, CoreDatasource, TableSchema, ColumnSchema
from apps.datasource.utils.utils import aes_decrypt
from apps.db.constant import DB, ConnectType
from apps.db.engine import get_engine_config
from apps.system.crud.assistant import get_out_ds_conf
from apps.system.schemas.system_schema import AssistantOutDsSchema
from common.core.deps import Trans
from common.utils.utils import AppLogUtil, equals_ignore_case
from fastapi import HTTPException
from apps.db.es_engine import get_es_connect, get_es_index, get_es_fields, get_es_data_by_http
from common.core.config import settings
import sqlglot
from sqlglot import expressions as exp
from sqlalchemy.pool import NullPool
from pyhive import hive

_ORACLE_CLIENT_INIT_ATTEMPTED = False
_ORACLE_CLIENT_READY = False


def _ensure_oracle_client_initialized() -> bool:
    global _ORACLE_CLIENT_INIT_ATTEMPTED, _ORACLE_CLIENT_READY

    if not settings.ORACLE_THICK_MODE_ENABLED:
        return False

    if _ORACLE_CLIENT_INIT_ATTEMPTED:
        return _ORACLE_CLIENT_READY

    _ORACLE_CLIENT_INIT_ATTEMPTED = True
    if not os.path.exists(settings.ORACLE_CLIENT_PATH):
        AppLogUtil.info("oracle thick mode enabled, but client not found, use thin mode")
        return False

    try:
        oracledb.init_oracle_client(lib_dir=settings.ORACLE_CLIENT_PATH)
        _ORACLE_CLIENT_READY = True
        AppLogUtil.info("init oracle client success, use thick mode")
    except Exception as e:
        _ORACLE_CLIENT_READY = False
        AppLogUtil.error(f"init oracle client failed, use thin mode: {e}")

    return _ORACLE_CLIENT_READY


def get_uri(ds: CoreDatasource) -> str:
    """
    是什么：get_uri 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration))) if not equals_ignore_case(ds.type,
                                                                                                 "excel") else get_engine_config()
    return get_uri_from_config(ds.type, conf)


def get_uri_from_config(type: str, conf: DatasourceConf) -> str:
    """
    是什么：get_uri_from_config 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    db_url: str
    if equals_ignore_case(type, "mysql"):
        checkParams(conf.extraJdbc, DB.mysql.illegalParams)
        if conf.extraJdbc is not None and conf.extraJdbc != '':
            db_url = f"mysql+pymysql://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{conf.database}?{conf.extraJdbc}"
        else:
            db_url = f"mysql+pymysql://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{conf.database}"
    elif equals_ignore_case(type, "sqlServer"):
        if conf.extraJdbc is not None and conf.extraJdbc != '':
            db_url = f"mssql+pymssql://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{conf.database}?{conf.extraJdbc}"
        else:
            db_url = f"mssql+pymssql://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{conf.database}"
    elif equals_ignore_case(type, "pg", "excel"):
        if conf.extraJdbc is not None and conf.extraJdbc != '':
            db_url = f"postgresql+psycopg2://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{conf.database}?{conf.extraJdbc}"
        else:
            db_url = f"postgresql+psycopg2://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{conf.database}"
    elif equals_ignore_case(type, "oracle"):
        _ensure_oracle_client_initialized()
        if equals_ignore_case(conf.mode, "service_name", "serviceName"):
            if conf.extraJdbc is not None and conf.extraJdbc != '':
                db_url = f"oracle+oracledb://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}?service_name={conf.database}&{conf.extraJdbc}"
            else:
                db_url = f"oracle+oracledb://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}?service_name={conf.database}"
        else:
            if conf.extraJdbc is not None and conf.extraJdbc != '':
                db_url = f"oracle+oracledb://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{conf.database}?{conf.extraJdbc}"
            else:
                db_url = f"oracle+oracledb://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{conf.database}"
    elif equals_ignore_case(type, "ck"):
        if conf.extraJdbc is not None and conf.extraJdbc != '':
            db_url = f"clickhouse+http://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{conf.database}?{conf.extraJdbc}"
        else:
            db_url = f"clickhouse+http://{urllib.parse.quote(conf.username)}:{urllib.parse.quote(conf.password)}@{conf.host}:{conf.port}/{conf.database}"
    else:
        raise 'The datasource type not support.'
    return db_url


def get_extra_config(conf: DatasourceConf):
    """
    是什么：get_extra_config 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    config_dict = {}
    if conf.extraJdbc:
        config_arr = conf.extraJdbc.split("&")
        for config in config_arr:
            kv = config.split("=")
            if len(kv) == 2 and kv[0] and kv[1]:
                config_dict[kv[0]] = kv[1]
            else:
                raise Exception(f'param: {config} is error')
    return config_dict


def get_origin_connect(type: str, conf: DatasourceConf):
    """
    是什么：get_origin_connect 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    extra_config_dict = get_extra_config(conf)
    if equals_ignore_case(type, "sqlServer"):
        # 为空或 true 时，将 tds_version 设置为 7.0。
        if conf.lowVersion is None or conf.lowVersion:
            return pymssql.connect(
                server=conf.host,
                port=str(conf.port),
                user=conf.username,
                password=conf.password,
                database=conf.database,
                timeout=conf.timeout,
                tds_version='7.0',  # 可选值：'4.2'、'7.0'、'8.0' 等。
                **extra_config_dict
            )
        else:
            return pymssql.connect(
                server=conf.host,
                port=str(conf.port),
                user=conf.username,
                password=conf.password,
                database=conf.database,
                timeout=conf.timeout,
                **extra_config_dict
            )


# 使用 SQLAlchemy
def get_engine(ds: CoreDatasource, timeout: int = 0) -> Engine:
    """
    是什么：get_engine 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration))) if not equals_ignore_case(ds.type,
                                                                                                 "excel") else get_engine_config()
    if conf.timeout is None:
        conf.timeout = timeout
    if timeout > 0:
        conf.timeout = timeout

    if equals_ignore_case(ds.type, "pg"):
        if conf.dbSchema is not None and conf.dbSchema != "":
            engine = create_engine(get_uri(ds),
                                   connect_args={"options": f"-c search_path={urllib.parse.quote(conf.dbSchema)}",
                                                 "connect_timeout": conf.timeout}, poolclass=NullPool)
        else:
            engine = create_engine(get_uri(ds), connect_args={"connect_timeout": conf.timeout}, poolclass=NullPool)
    elif equals_ignore_case(ds.type, 'sqlServer'):
        engine = create_engine('mssql+pymssql://', creator=lambda: get_origin_connect(ds.type, conf),
                               poolclass=NullPool)
    elif equals_ignore_case(ds.type, 'oracle'):
        engine = create_engine(get_uri(ds), poolclass=NullPool)
    elif equals_ignore_case(ds.type, 'mysql'):  # MySQL
        ssl_mode = {"require": True} if conf.ssl else None
        connect_args = {"connect_timeout": conf.timeout, "read_timeout": conf.timeout, "write_timeout": conf.timeout}
        if ssl_mode:
            connect_args["ssl"] = ssl_mode
        engine = create_engine(get_uri(ds), connect_args=connect_args, poolclass=NullPool)
    else:  # ClickHouse
        engine = create_engine(get_uri(ds), connect_args={"connect_timeout": conf.timeout}, poolclass=NullPool)
    return engine


def get_session(ds: CoreDatasource | AssistantOutDsSchema, timeout: int = 0):
    # engine = get_engine(ds) if isinstance(ds, CoreDatasource) else get_ds_engine(ds)
    """
    是什么：get_session 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    if isinstance(ds, AssistantOutDsSchema):
        out_conf = get_out_ds_conf(ds, 30)
        ds.configuration = out_conf

    engine = get_engine(ds, timeout=timeout)
    session_maker = sessionmaker(bind=engine)
    session = session_maker()
    return session


def check_connection(trans: Optional[Trans], ds: CoreDatasource | AssistantOutDsSchema, is_raise: bool = False):
    """
    是什么：check_connection 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据库连接里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if isinstance(ds, AssistantOutDsSchema):
        out_conf = get_out_ds_conf(ds, 10)
        ds.configuration = out_conf

    db = DB.get_db(ds.type)
    if db.connect_type == ConnectType.sqlalchemy:
        conn = get_engine(ds, 10)
        try:
            with conn.connect() as connection:
                AppLogUtil.info("success")
                return True
        except Exception as e:
            AppLogUtil.error(f"Datasource {ds.id} connection failed: {e}")
            if is_raise:
                raise HTTPException(status_code=500, detail=trans('i18n_ds_invalid') + f': {e.args}')
            return False
    else:
        conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration)))
        extra_config_dict = get_extra_config(conf)
        if equals_ignore_case(ds.type, 'dm'):
            with dmPython.connect(user=conf.username, password=conf.password, server=conf.host,
                                  port=conf.port, **extra_config_dict) as conn, conn.cursor() as cursor:
                try:
                    cursor.execute('select 1', timeout=10).fetchall()
                    AppLogUtil.info("success")
                    return True
                except Exception as e:
                    AppLogUtil.error(f"Datasource {ds.id} connection failed: {e}")
                    if is_raise:
                        raise HTTPException(status_code=500, detail=trans('i18n_ds_invalid') + f': {e.args}')
                    return False
        elif equals_ignore_case(ds.type, 'doris', 'starrocks'):
            ssl_args = {'ssl': {'ssl_mode': 'REQUIRE'}} if conf.ssl else {}
            with pymysql.connect(user=conf.username, passwd=conf.password, host=conf.host,
                                 port=conf.port, db=conf.database, connect_timeout=10,
                                 read_timeout=10, **extra_config_dict, **ssl_args) as conn, conn.cursor() as cursor:
                try:
                    cursor.execute('select 1')
                    AppLogUtil.info("success")
                    return True
                except Exception as e:
                    AppLogUtil.error(f"Datasource {ds.id} connection failed: {e}")
                    if is_raise:
                        raise HTTPException(status_code=500, detail=trans('i18n_ds_invalid') + f': {e.args}')
                    return False
        elif equals_ignore_case(ds.type, 'redshift'):
            with redshift_connector.connect(host=conf.host, port=conf.port, database=conf.database,
                                            user=conf.username,
                                            password=conf.password,
                                            timeout=10, **extra_config_dict) as conn, conn.cursor() as cursor:
                try:
                    cursor.execute('select 1')
                    AppLogUtil.info("success")
                    return True
                except Exception as e:
                    AppLogUtil.error(f"Datasource {ds.id} connection failed: {e}")
                    if is_raise:
                        raise HTTPException(status_code=500, detail=trans('i18n_ds_invalid') + f': {e.args}')
                    return False
        elif equals_ignore_case(ds.type, 'kingbase'):
            with psycopg2.connect(host=conf.host, port=conf.port, database=conf.database,
                                  user=conf.username,
                                  password=conf.password,
                                  connect_timeout=10, **extra_config_dict) as conn, conn.cursor() as cursor:
                try:
                    cursor.execute('select 1')
                    AppLogUtil.info("success")
                    return True
                except Exception as e:
                    AppLogUtil.error(f"Datasource {ds.id} connection failed: {e}")
                    if is_raise:
                        raise HTTPException(status_code=500, detail=trans('i18n_ds_invalid') + f': {e.args}')
                    return False
        elif equals_ignore_case(ds.type, 'hive'):
            with hive.connect(host=conf.host, port=conf.port, username=conf.username,
                              database=conf.database, **extra_config_dict) as conn, conn.cursor() as cursor:
                try:
                    cursor.execute('select 1')
                    AppLogUtil.info("success")
                    return True
                except Exception as e:
                    AppLogUtil.error(f"Datasource {ds.id} connection failed: {e}")
                    if is_raise:
                        raise HTTPException(status_code=500, detail=trans('i18n_ds_invalid') + f': {e.args}')
                    return False

        elif equals_ignore_case(ds.type, 'es'):
            es_conn = get_es_connect(conf)
            if es_conn.ping():
                AppLogUtil.info("success")
                return True
            else:
                AppLogUtil.info("failed")
                return False
    # else:
    #     conn = get_ds_engine(ds)
    #     try:
    #         with conn.connect() as connection:
    #             AppLogUtil.info("success")
    #             return True
    #     except Exception as e:
    #         AppLogUtil.error(f"Datasource {ds.id} connection failed: {e}")
    #         if is_raise:
    #             raise HTTPException(status_code=500, detail=trans('i18n_ds_invalid') + f': {e.args}')
    #         return False

    return False


def get_version(ds: CoreDatasource | AssistantOutDsSchema):
    """
    是什么：get_version 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    version = ''
    if isinstance(ds, CoreDatasource):
        conf = DatasourceConf(
            **json.loads(aes_decrypt(ds.configuration))) if not equals_ignore_case(ds.type,
                                                                                   "excel") else get_engine_config()
    else:
        conf = DatasourceConf(**json.loads(aes_decrypt(get_out_ds_conf(ds, 10))))
    # if isinstance(ds, AssistantOutDsSchema):
    #     conf = DatasourceConf()
    #     conf.host = ds.host
    #     conf.port = ds.port
    #     conf.username = ds.user
    #     conf.password = ds.password
    #     conf.database = ds.dataBase
    #     conf.dbSchema = ds.db_schema
    #     conf.timeout = 10
    db = DB.get_db(ds.type)
    sql = get_version_sql(ds, conf)
    if not sql:
        return ''
    try:
        if db.connect_type == ConnectType.sqlalchemy:
            with get_session(ds) as session:
                with session.execute(text(sql)) as result:
                    res = result.fetchall()
                    version = res[0][0]
        else:
            extra_config_dict = get_extra_config(conf)
            if equals_ignore_case(ds.type, 'dm'):
                with dmPython.connect(user=conf.username, password=conf.password, server=conf.host,
                                      port=conf.port) as conn, conn.cursor() as cursor:
                    cursor.execute(sql, timeout=10, **extra_config_dict)
                    res = cursor.fetchall()
                    version = res[0][0]
            elif equals_ignore_case(ds.type, 'doris', 'starrocks'):
                ssl_args = {'ssl': {'ssl_mode': 'REQUIRE'}} if conf.ssl else {}
                with pymysql.connect(user=conf.username, passwd=conf.password, host=conf.host,
                                     port=conf.port, db=conf.database, connect_timeout=10,
                                     read_timeout=10, **extra_config_dict, **ssl_args) as conn, conn.cursor() as cursor:
                    cursor.execute(sql)
                    res = cursor.fetchall()
                    version = res[0][0]
            elif equals_ignore_case(ds.type, 'redshift', 'es', 'hive'):
                version = ''
    except Exception as e:
        print(e)
        version = ''
    return version.decode() if isinstance(version, bytes) else version


def get_schema(ds: CoreDatasource):
    """
    是什么：get_schema 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration))) if ds.type != "excel" else get_engine_config()
    db = DB.get_db(ds.type)
    if db.connect_type == ConnectType.sqlalchemy:
        with get_session(ds) as session:
            sql: str = ''
            if equals_ignore_case(ds.type, "sqlServer"):
                sql = """select name
                         from sys.schemas"""
            elif equals_ignore_case(ds.type, "pg", "excel"):
                sql = """SELECT nspname
                         FROM pg_namespace"""
            elif equals_ignore_case(ds.type, "oracle"):
                sql = """select *
                         from all_users"""
            with session.execute(text(sql)) as result:
                res = result.fetchall()
                res_list = [item[0] for item in res]
                return res_list
    else:
        extra_config_dict = get_extra_config(conf)
        if equals_ignore_case(ds.type, 'dm'):
            with dmPython.connect(user=conf.username, password=conf.password, server=conf.host,
                                  port=conf.port, **extra_config_dict) as conn, conn.cursor() as cursor:
                cursor.execute("""select OBJECT_NAME
                                  from all_objects
                                  where object_type = 'SCH'""", timeout=conf.timeout)
                res = cursor.fetchall()
                res_list = [item[0] for item in res]
                return res_list
        elif equals_ignore_case(ds.type, 'redshift'):
            with redshift_connector.connect(host=conf.host, port=conf.port, database=conf.database, user=conf.username,
                                            password=conf.password,
                                            timeout=conf.timeout, **extra_config_dict) as conn, conn.cursor() as cursor:
                cursor.execute("""SELECT nspname
                                  FROM pg_namespace""")
                res = cursor.fetchall()
                res_list = [item[0] for item in res]
                return res_list
        elif equals_ignore_case(ds.type, 'kingbase'):
            with psycopg2.connect(host=conf.host, port=conf.port, database=conf.database, user=conf.username,
                                  password=conf.password,
                                  options=f"-c statement_timeout={conf.timeout * 1000}",
                                  **extra_config_dict) as conn, conn.cursor() as cursor:
                cursor.execute("""SELECT nspname
                                  FROM pg_namespace""")
                res = cursor.fetchall()
                res_list = [item[0] for item in res]
                return res_list


def get_tables(ds: CoreDatasource):
    """
    是什么：get_tables 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration))) if not equals_ignore_case(ds.type,
                                                                                                 "excel") else get_engine_config()
    db = DB.get_db(ds.type)
    sql, sql_param = get_table_sql(ds, conf, get_version(ds))
    if db.connect_type == ConnectType.sqlalchemy:
        with get_session(ds) as session:
            with session.execute(text(sql), {"param": sql_param}) as result:
                res = result.fetchall()
                res_list = [TableSchema(*item) for item in res]
                return res_list
    else:
        extra_config_dict = get_extra_config(conf)
        if equals_ignore_case(ds.type, 'dm'):
            with dmPython.connect(user=conf.username, password=conf.password, server=conf.host,
                                  port=conf.port, **extra_config_dict) as conn, conn.cursor() as cursor:
                cursor.execute(sql, {"param": sql_param}, timeout=conf.timeout)
                res = cursor.fetchall()
                res_list = [TableSchema(*item) for item in res]
                return res_list
        elif equals_ignore_case(ds.type, 'doris', 'starrocks'):
            ssl_args = {'ssl': {'ssl_mode': 'REQUIRE'}} if conf.ssl else {}
            with pymysql.connect(user=conf.username, passwd=conf.password, host=conf.host,
                                 port=conf.port, db=conf.database, connect_timeout=conf.timeout,
                                 read_timeout=conf.timeout, **extra_config_dict,
                                 **ssl_args) as conn, conn.cursor() as cursor:
                cursor.execute(sql, (sql_param,))
                res = cursor.fetchall()
                res_list = [TableSchema(*item) for item in res]
                return res_list
        elif equals_ignore_case(ds.type, 'redshift'):
            with redshift_connector.connect(host=conf.host, port=conf.port, database=conf.database, user=conf.username,
                                            password=conf.password,
                                            timeout=conf.timeout, **extra_config_dict) as conn, conn.cursor() as cursor:
                cursor.execute(sql, (sql_param,))
                res = cursor.fetchall()
                res_list = [TableSchema(*item) for item in res]
                return res_list
        elif equals_ignore_case(ds.type, 'kingbase'):
            with psycopg2.connect(host=conf.host, port=conf.port, database=conf.database, user=conf.username,
                                  password=conf.password,
                                  options=f"-c statement_timeout={conf.timeout * 1000}",
                                  **extra_config_dict) as conn, conn.cursor() as cursor:
                cursor.execute(sql.format(sql_param))
                res = cursor.fetchall()
                res_list = [TableSchema(*item) for item in res]
                return res_list
        elif equals_ignore_case(ds.type, 'es'):
            res = get_es_index(conf)
            res_list = [TableSchema(*item) for item in res]
            return res_list
        elif equals_ignore_case(ds.type, 'hive'):
            with hive.connect(host=conf.host, port=conf.port, username=conf.username,
                              database=conf.database, **extra_config_dict) as conn, conn.cursor() as cursor:
                cursor.execute(sql)
                res = cursor.fetchall()
                res_list = [TableSchema(*item) for item in res]
                return res_list


def get_fields(ds: CoreDatasource, table_name: str = None):
    """
    是什么：get_fields 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration))) if not equals_ignore_case(ds.type,
                                                                                                 "excel") else get_engine_config()
    db = DB.get_db(ds.type)
    sql, p1, p2 = get_field_sql(ds, conf, table_name)
    if db.connect_type == ConnectType.sqlalchemy:
        with get_session(ds) as session:
            with session.execute(text(sql), {"param1": p1, "param2": p2}) as result:
                res = result.fetchall()
                res_list = [ColumnSchema(*item) for item in res]
                return res_list
    else:
        extra_config_dict = get_extra_config(conf)
        if equals_ignore_case(ds.type, 'dm'):
            with dmPython.connect(user=conf.username, password=conf.password, server=conf.host,
                                  port=conf.port, **extra_config_dict) as conn, conn.cursor() as cursor:
                cursor.execute(sql, {"param1": p1, "param2": p2}, timeout=conf.timeout)
                res = cursor.fetchall()
                res_list = [ColumnSchema(*item) for item in res]
                return res_list
        elif equals_ignore_case(ds.type, 'doris', 'starrocks'):
            ssl_args = {'ssl': {'ssl_mode': 'REQUIRE'}} if conf.ssl else {}
            with pymysql.connect(user=conf.username, passwd=conf.password, host=conf.host,
                                 port=conf.port, db=conf.database, connect_timeout=conf.timeout,
                                 read_timeout=conf.timeout, **extra_config_dict,
                                 **ssl_args) as conn, conn.cursor() as cursor:
                cursor.execute(sql, (p1, p2))
                res = cursor.fetchall()
                res_list = [ColumnSchema(*item) for item in res]
                return res_list
        elif equals_ignore_case(ds.type, 'redshift'):
            with redshift_connector.connect(host=conf.host, port=conf.port, database=conf.database, user=conf.username,
                                            password=conf.password,
                                            timeout=conf.timeout, **extra_config_dict) as conn, conn.cursor() as cursor:
                cursor.execute(sql, (p1, p2))
                res = cursor.fetchall()
                res_list = [ColumnSchema(*item) for item in res]
                return res_list
        elif equals_ignore_case(ds.type, 'kingbase'):
            with psycopg2.connect(host=conf.host, port=conf.port, database=conf.database, user=conf.username,
                                  password=conf.password,
                                  options=f"-c statement_timeout={conf.timeout * 1000}",
                                  **extra_config_dict) as conn, conn.cursor() as cursor:
                cursor.execute(sql.format(p1, p2))
                res = cursor.fetchall()
                res_list = [ColumnSchema(*item) for item in res]
                return res_list
        elif equals_ignore_case(ds.type, 'es'):
            res = get_es_fields(conf, table_name)
            res_list = [ColumnSchema(*item) for item in res]
            return res_list
        elif equals_ignore_case(ds.type, 'hive'):
            with hive.connect(host=conf.host, port=conf.port, username=conf.username,
                              database=conf.database, **extra_config_dict) as conn, conn.cursor() as cursor:
                cursor.execute(sql)
                res = cursor.fetchall()
                res_list = [ColumnSchema(*item) for item in res]
                return res_list


def convert_value(value, datetime_format='space'):
    """
    是什么：convert_value 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if value is None:
        return None
        # 处理 bytes 类型（包括 BIT 字段）
    if isinstance(value, bytes):
        # 1. 尝试判断是否是 BIT 类型
        if len(value) <= 8:  # BIT 类型通常不会很长
            try:
                # 转换为整数
                int_val = int.from_bytes(value, 'big')

                # 如果是 0 或 1，返回布尔值更直观
                if int_val in (0, 1):
                    return bool(int_val)
                else:
                    return int_val
            except:
                # 如果转换失败，尝试解码为字符串
                pass

        # 2. 尝试解码为 UTF-8 字符串
        try:
            return value.decode('utf-8')
        except UnicodeDecodeError:
            # 3. 如果包含非打印字符，返回十六进制
            if any(b < 32 and b not in (9, 10, 13) for b in value):  # 非打印字符
                return f"0x{value.hex()}"
            else:
                # 4. 尝试 Latin-1 解码（不会失败）
                return value.decode('latin-1')

    elif isinstance(value, bytearray):
        # 处理 bytearray
        return convert_value(bytes(value))

    if isinstance(value, timedelta):
        # 将 timedelta 转换为秒数（整数）或字符串
        return str(value)  # 或 value.total_seconds()
    elif isinstance(value, Decimal):
        return float(value)
    # 4. 处理 datetime
    elif isinstance(value, datetime):
        if datetime_format == 'iso':
            return value.isoformat()
        elif datetime_format == 'space':
            return value.strftime('%Y-%m-%d %H:%M:%S')
        else:  # 'auto' 或其他
            # 自动判断：没有时间部分只显示日期
            if value.hour == 0 and value.minute == 0 and value.second == 0 and value.microsecond == 0:
                return value.strftime('%Y-%m-%d')
            else:
                return value.strftime('%Y-%m-%d %H:%M:%S')

    # 5. 处理 date
    elif isinstance(value, date):
        return value.isoformat()  # 总是 YYYY-MM-DD

    # 6. 处理 time
    elif isinstance(value, time):
        return str(value)
    else:
        return value


def _effective_query_timeout(ds: CoreDatasource | AssistantOutDsSchema, query_timeout: int | None) -> int:
    if query_timeout and query_timeout > 0:
        return int(query_timeout)
    try:
        conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration)))
        return int(conf.timeout or 0)
    except Exception:
        return 0


def _query_result_max_rows() -> int:
    try:
        return max(1, int(settings.SHUZHI_QUERY_RESULT_MAX_ROWS))
    except Exception:
        return 10000


def _limited_fetchmany(cursor_or_result):
    fetchmany = getattr(cursor_or_result, "fetchmany", None)
    if callable(fetchmany):
        return fetchmany(_query_result_max_rows())
    return cursor_or_result.fetchall()


def _build_query_result(columns: list, rows: list, sql: str) -> dict:
    result_list = [
        {str(columns[i]): convert_value(value) for i, value in enumerate(tuple_item)}
        for tuple_item in rows
    ]
    return {
        "fields": columns,
        "data": result_list,
        "sql": bytes.decode(base64.b64encode(bytes(sql, 'utf-8'))),
    }


def _apply_sqlalchemy_statement_timeout(session, ds_type: str, timeout_seconds: int) -> None:
    if timeout_seconds <= 0:
        return
    timeout_ms = max(1, timeout_seconds) * 1000
    try:
        if equals_ignore_case(ds_type, "pg", "excel"):
            session.execute(text("SET LOCAL statement_timeout = :timeout_ms"), {"timeout_ms": timeout_ms})
        elif equals_ignore_case(ds_type, "mysql"):
            session.execute(text("SET SESSION MAX_EXECUTION_TIME = :timeout_ms"), {"timeout_ms": timeout_ms})
    except Exception as exc:
        AppLogUtil.warning(f"Failed to apply datasource query timeout: type={ds_type}, timeout={timeout_seconds}s, error={exc}")


def _apply_sqlalchemy_read_only_guard(session, ds_type: str) -> None:
    ds_key = normalize_sql_safety_ds_type(ds_type)
    guard_sql = {
        "pg": "SET TRANSACTION READ ONLY",
        "excel": "SET TRANSACTION READ ONLY",
        "mysql": "START TRANSACTION READ ONLY",
        "oracle": "SET TRANSACTION READ ONLY",
        "ck": "SET readonly = 1",
    }.get(ds_key)
    if guard_sql:
        session.execute(text(guard_sql))


def _apply_dbapi_read_only_guard(conn, cursor, ds_type: str) -> None:
    ds_key = normalize_sql_safety_ds_type(ds_type)
    if ds_key == "kingbase" and hasattr(conn, "set_session"):
        conn.set_session(readonly=True)
        return
    guard_sql = {
        "redshift": "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY",
        "doris": "START TRANSACTION READ ONLY",
        "starrocks": "START TRANSACTION READ ONLY",
        "oracle": "SET TRANSACTION READ ONLY",
    }.get(ds_key)
    if guard_sql:
        cursor.execute(guard_sql)


def _unsafe_exec_sql_after_validation(
        ds: CoreDatasource | AssistantOutDsSchema,
        sql: str,
        origin_column=False,
        query_timeout: int | None = None,
):
    """底层数据源执行适配器。

    面向用户的分析入口不要直接调用这里，应通过
    apps.datasource.crud.query_executor 先完成数据源、表、字段、行权限与审计友好的 SQL 标准化。
    """
    while sql.endswith(';'):
        sql = sql[:-1]
    # 检查待执行 SQL 是否只包含读取操作
    is_safe, error_reason = check_sql_read(sql, ds)
    if not is_safe:
        raise ValueError(f"SQL can only contain read operations: {error_reason}")

    db = DB.get_db(ds.type)
    if db.connect_type == ConnectType.sqlalchemy:
        timeout_seconds = _effective_query_timeout(ds, query_timeout)
        session = get_session(ds, timeout=timeout_seconds)
        try:
            if normalize_sql_safety_ds_type(ds.type) == "mysql":
                _apply_sqlalchemy_statement_timeout(session, ds.type, timeout_seconds)
                _apply_sqlalchemy_read_only_guard(session, ds.type)
            else:
                _apply_sqlalchemy_read_only_guard(session, ds.type)
                _apply_sqlalchemy_statement_timeout(session, ds.type, timeout_seconds)
            with session.execute(text(sql)) as result:
                try:
                    columns = result.keys()._keys if origin_column else [item.lower() for item in result.keys()._keys]
                    res = _limited_fetchmany(result)
                    return _build_query_result(columns, res, sql)
                except Exception as ex:
                    raise ParseSQLResultError(str(ex))
        except Exception:
            session.rollback()
            raise
        finally:
            session.rollback()
            session.close()
    else:
        conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration)))
        extra_config_dict = get_extra_config(conf)
        if equals_ignore_case(ds.type, 'dm'):
            with dmPython.connect(user=conf.username, password=conf.password, server=conf.host,
                                  port=conf.port, **extra_config_dict) as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(sql, timeout=conf.timeout)
                    res = _limited_fetchmany(cursor)
                    columns = [field[0] for field in cursor.description] if origin_column else [field[0].lower() for
                                                                                                field in
                                                                                                cursor.description]
                    return _build_query_result(columns, res, sql)
                except Exception as ex:
                    raise ParseSQLResultError(str(ex))
        elif equals_ignore_case(ds.type, 'doris', 'starrocks'):
            ssl_args = {'ssl': {'ssl_mode': 'REQUIRE'}} if conf.ssl else {}
            with pymysql.connect(user=conf.username, passwd=conf.password, host=conf.host,
                                 port=conf.port, db=conf.database, connect_timeout=conf.timeout,
                                 read_timeout=conf.timeout, **extra_config_dict,
                                  **ssl_args) as conn, conn.cursor() as cursor:
                try:
                    _apply_dbapi_read_only_guard(conn, cursor, ds.type)
                    cursor.execute(sql)
                    res = _limited_fetchmany(cursor)
                    columns = [field[0] for field in cursor.description] if origin_column else [field[0].lower() for
                                                                                                field in
                                                                                                cursor.description]
                    return _build_query_result(columns, res, sql)
                except Exception as ex:
                    raise ParseSQLResultError(str(ex))
        elif equals_ignore_case(ds.type, 'redshift'):
            with redshift_connector.connect(host=conf.host, port=conf.port, database=conf.database, user=conf.username,
                                             password=conf.password,
                                             timeout=conf.timeout, **extra_config_dict) as conn, conn.cursor() as cursor:
                try:
                    _apply_dbapi_read_only_guard(conn, cursor, ds.type)
                    cursor.execute(sql)
                    res = _limited_fetchmany(cursor)
                    columns = [field[0] for field in cursor.description] if origin_column else [field[0].lower() for
                                                                                                field in
                                                                                                cursor.description]
                    return _build_query_result(columns, res, sql)
                except Exception as ex:
                    raise ParseSQLResultError(str(ex))
        elif equals_ignore_case(ds.type, 'kingbase'):
            with psycopg2.connect(host=conf.host, port=conf.port, database=conf.database, user=conf.username,
                                  password=conf.password,
                                  options=f"-c statement_timeout={conf.timeout * 1000}",
                                  **extra_config_dict) as conn, conn.cursor() as cursor:
                try:
                    _apply_dbapi_read_only_guard(conn, cursor, ds.type)
                    cursor.execute(sql)
                    res = _limited_fetchmany(cursor)
                    columns = [field[0] for field in cursor.description] if origin_column else [field[0].lower() for
                                                                                                field in
                                                                                                cursor.description]
                    return _build_query_result(columns, res, sql)
                except Exception as ex:
                    raise ParseSQLResultError(str(ex))
        elif equals_ignore_case(ds.type, 'es'):
            try:
                res, columns = get_es_data_by_http(conf, sql)
                columns = [field.get('name') for field in columns] if origin_column else [field.get('name').lower() for
                                                                                          field in
                                                                                          columns]
                return _build_query_result(columns, res[:_query_result_max_rows()], sql)
            except Exception as ex:
                raise Exception(str(ex))
        elif equals_ignore_case(ds.type, 'hive'):
            with hive.connect(host=conf.host, port=conf.port, username=conf.username,
                              database=conf.database, **extra_config_dict) as conn, conn.cursor() as cursor:
                try:
                    # Hive 使用反引号标识符；这里规范化带引号标识符作为兼容兜底。
                    hive_sql = re.sub(r'"([A-Za-z_][A-Za-z0-9_]*)"', r'`\1`', sql)
                    cursor.execute(hive_sql)
                    res = _limited_fetchmany(cursor)
                    columns = [field[0] for field in cursor.description] if origin_column else [field[0].lower() for
                                                                                                field in
                                                                                                cursor.description]
                    return _build_query_result(columns, res, hive_sql)
                except Exception as ex:
                    raise ParseSQLResultError(str(ex))


def normalize_sql_safety_ds_type(ds_type: str | None) -> str:
    ds_key = str(ds_type or '').strip().casefold()
    return {
        'postgres': 'pg',
        'postgresql': 'pg',
        'pgsql': 'pg',
        'clickhouse': 'ck',
        'sql server': 'sqlserver',
        'sqlserver': 'sqlserver',
        'mssql': 'sqlserver',
        'aws_redshift': 'redshift',
    }.get(ds_key, ds_key)


def get_sqlglot_dialect(ds_type: str) -> str:
    """
    是什么：get_sqlglot_dialect 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    ds_key = normalize_sql_safety_ds_type(ds_type)
    if ds_key in {'mysql', 'doris', 'starrocks'}:
        return 'mysql'
    elif ds_key == 'sqlserver':
        return 'tsql'
    elif ds_key in {'pg', 'kingbase', 'excel'}:
        return 'postgres'
    elif ds_key == 'redshift':
        return 'redshift'
    elif ds_key == 'ck':
        return 'clickhouse'
    elif ds_key == 'oracle':
        return 'oracle'
    elif ds_key == 'hive':
        return 'hive'
    return None


# 通用危险函数（适用于所有数据库）
COMMON_DANGEROUS_FUNCTIONS = {'version', 'current_user', 'user', 'database'}

POSTGRES_COMPAT_DANGEROUS_FUNCTIONS = {
    'pg_read_file',
    'pg_read_binary_file',
    'pg_ls_dir',
    'pg_ls_logdir',
    'pg_ls_waldir',
    'pg_ls_tmpdir',
    'pg_ls_archive_statusdir',
    'pg_stat_file',
    'pg_write_file',
    'lo_import',
    'lo_export',
}

CLICKHOUSE_DANGEROUS_FUNCTIONS = {
    'file',
    'fileCluster',
    'url',
    's3',
    's3Cluster',
    'hdfs',
    'hdfsCluster',
    'azureBlobStorage',
    'gcs',
    'oss',
    'cosn',
    'executable',
    'executablePool',
    'remote',
    'remoteSecure',
    'mysql',
    'postgresql',
    'mongodb',
    'jdbc',
    'odbc',
}

# 特定数据库的危险函数
DS_SPECIFIC_DANGEROUS_FUNCTIONS = {
    'mysql': {'LOAD_FILE', 'INTO OUTFILE', 'INTO DUMPFILE'},
    'doris': {'LOAD_FILE', 'INTO OUTFILE', 'INTO DUMPFILE'},
    'starrocks': {'LOAD_FILE', 'INTO OUTFILE', 'INTO DUMPFILE'},
    'pg': POSTGRES_COMPAT_DANGEROUS_FUNCTIONS,
    'kingbase': POSTGRES_COMPAT_DANGEROUS_FUNCTIONS,
    'redshift': POSTGRES_COMPAT_DANGEROUS_FUNCTIONS,
    'ck': CLICKHOUSE_DANGEROUS_FUNCTIONS,
    'sqlserver': {'EXEC', 'xp_cmdshell', 'sp_executesql'},
    'oracle': {'UTL_FILE', 'DBMS_PIPE', 'DBMS_LOCK'},
    'hive': {'ADD FILE', 'ADD JAR'},
}

# 危险模式正则表达式（用于检查特殊语法）
import re
DANGEROUS_PATTERNS = [
    r'\bINTO\s+OUTFILE\b',
    r'\bINTO\s+DUMPFILE\b',
    r'\bEXEC\s*\(',
    r'\bCOPY\s+.*\bTO\s+PROGRAM\b',
]


def get_dangerous_functions(ds_type: str) -> set:
    """
    是什么：get_dangerous_functions 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    functions = COMMON_DANGEROUS_FUNCTIONS.copy()
    ds_key = normalize_sql_safety_ds_type(ds_type)
    if ds_key in DS_SPECIFIC_DANGEROUS_FUNCTIONS:
        functions.update(DS_SPECIFIC_DANGEROUS_FUNCTIONS[ds_key])
    return functions


def normalize_sql_function_name(name: str | None) -> str:
    return str(name or '').strip('`"[]').casefold()


def iter_sql_function_names(stmt) -> list[str]:
    function_names: list[str] = []
    for func in stmt.find_all(exp.Func):
        function_names.append(normalize_sql_function_name(getattr(func, 'name', '')))

    for table in stmt.find_all(exp.Table):
        expressions = table.args.get('expressions') or []
        table_name = normalize_sql_function_name(getattr(table, 'name', ''))
        if table_name and expressions:
            function_names.append(table_name)

    return function_names


def check_dangerous_functions(statements: list, ds_type: str) -> bool:
    """
    是什么：check_dangerous_functions 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据库连接里的数据、权限或配置是否合法，不对就及时拦住。
    """
    dangerous_functions = get_dangerous_functions(ds_type)
    dangerous_function_names = {normalize_sql_function_name(f) for f in dangerous_functions}

    for stmt in statements:
        if stmt:
            for func_name in iter_sql_function_names(stmt):
                if func_name in dangerous_function_names:
                    return False
    return True


def check_sql_read(sql: str, ds: CoreDatasource | AssistantOutDsSchema) -> tuple[bool, str]:
    """
    是什么：check_sql_read 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据库连接里的数据、权限或配置是否合法，不对就及时拦住。
    """
    try:
        normalized_sql = sql.strip().lstrip("(").strip()
        first_keyword = normalized_sql.split(None, 1)[0].upper() if normalized_sql else ""

        # 根据配置决定是否允许元数据查询
        if settings.SHUZHI_ALLOW_METADATA_QUERIES:
            allowed_read_commands = {"SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"}
        else:
            allowed_read_commands = {"SELECT", "WITH"}

        denied_write_commands = {
            "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER",
            "TRUNCATE", "MERGE", "COPY", "REPLACE", "GRANT", "REVOKE",
            "USE", "SET", "CALL"
        }

        if not first_keyword:
            raise ValueError("Parse SQL Error")
        if first_keyword in denied_write_commands:
            return False, f"Write operation '{first_keyword}' is not allowed"

        # 1. 使用正则检查特殊模式
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, sql, re.IGNORECASE):
                return False, f"SQL contains dangerous pattern: {pattern}"

        dialect = get_sqlglot_dialect(ds.type)
        statements = sqlglot.parse(sql, dialect=dialect)

        if not statements:
            raise ValueError("Parse SQL Error")
        executable_statements = [stmt for stmt in statements if stmt is not None]
        if len(executable_statements) != 1:
            return False, "SQL must contain exactly one statement"

        # 2. 使用 sqlglot 检查函数调用
        dangerous_functions = get_dangerous_functions(ds.type)
        dangerous_function_names = {normalize_sql_function_name(f) for f in dangerous_functions}
        for stmt in executable_statements:
            if stmt:
                for func_name in iter_sql_function_names(stmt):
                    if func_name in dangerous_function_names:
                        return False, f"SQL contains dangerous function: {func_name}"

        # 3. 检查写操作类型
        write_types = (
            exp.Insert, exp.Update, exp.Delete,
            exp.Create, exp.Drop, exp.Alter,
            exp.Merge, exp.Copy
        )

        for stmt in executable_statements:
            if isinstance(stmt, write_types):
                return False, f"SQL contains write operation: {type(stmt).__name__}"

        if first_keyword not in allowed_read_commands:
            return False, f"SQL command '{first_keyword}' is not allowed. Only SELECT and WITH are permitted"

        return True, ""

    except Exception as e:
        raise ValueError(f"Parse SQL Error: {e}")


def checkParams(extraParams: str, illegalParams: List[str]):
    """
    是什么：checkParams 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据库连接里的数据、权限或配置是否合法，不对就及时拦住。
    """
    kvs = extraParams.split('&')
    for kv in kvs:
        if kv and '=' in kv:
            k, v = kv.split('=')
            if k in illegalParams:
                raise HTTPException(status_code=500, detail=f'Illegal Parameter: {k}')
