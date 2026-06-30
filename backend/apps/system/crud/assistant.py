"""
脚本说明：这个脚本封装系统管理的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
import json
import re
import urllib
from typing import Optional

import requests
from fastapi import FastAPI
from sqlmodel import Session, select
from starlette.middleware.cors import CORSMiddleware

from apps.datasource.crud.binding import get_bound_datasource_id_for_tenant
from apps.datasource.models.datasource import CoreDatasource
from apps.datasource.utils.utils import aes_encrypt
from apps.system.models.system_model import AssistantModel
from apps.system.schemas.auth import CacheName, CacheNamespace
from apps.system.schemas.access_context import require_tenant_id
from apps.system.schemas.system_schema import AssistantHeader, AssistantOutDsSchema, UserInfoDTO
from common.core.config import settings
from common.core.db import engine
from common.core.app_cache import cache
from common.utils.utils import AppLogUtil, get_domain_list, string_to_numeric_hash
from common.core.deps import Trans
from common.core.response_middleware import ResponseMiddleware


@cache(namespace=CacheNamespace.EMBEDDED_INFO, cacheName=CacheName.ASSISTANT_INFO, keyExpression="assistant_id")
async def get_assistant_info(*, session: Session, assistant_id: int) -> AssistantModel | None:
    """
    是什么：get_assistant_info 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    db_model = session.get(AssistantModel, assistant_id)
    return db_model


def get_assistant_user(*, id: int):
    """
    是什么：get_assistant_user 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    return UserInfoDTO(id=id, account="shuzhi-inner-assistant", name="shuzhi-inner-assistant",
                       email="shuzhi-inner-assistant@shuzhi.com")


def get_assistant_ds(session: Session, llm_service) -> list[dict]:
    """
    是什么：get_assistant_ds 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    assistant: AssistantHeader = llm_service.current_assistant
    type = assistant.type
    if type == 0 or type == 2:
        configuration = assistant.configuration
        tenant_id = require_tenant_id(getattr(assistant, "tenant_id", None))
        datasource_id = get_bound_datasource_id_for_tenant(session, tenant_id)
        if datasource_id is None:
            return []
        stmt = (
            select(CoreDatasource.id, CoreDatasource.name, CoreDatasource.description)
            .where(CoreDatasource.id == datasource_id)
        )
        if configuration:
            config: dict[any] = json.loads(configuration)
            if not assistant.online:
                public_list: list[int] = config.get('public_list') or None
                if public_list:
                    stmt = stmt.where(CoreDatasource.id.in_(public_list))
                else:
                    return []
                """ private_list: list[int] = config.get('private_list') or None
                if private_list:
                    stmt = stmt.where(~CoreDatasource.id.in_(private_list)) """
        db_ds_list = session.exec(stmt)

        result_list = [
            {
                "id": ds.id,
                "name": ds.name,
                "description": ds.description
            }
            for ds in db_ds_list
        ]

        # 离线时过滤私有数据源
        return result_list
    out_ds_instance: AssistantOutDs = AssistantOutDsFactory.get_instance(assistant)
    llm_service.out_ds_instance = out_ds_instance
    dslist = out_ds_instance.get_simple_ds_list()
    # 是否需要格式化？
    return dslist


def init_dynamic_cors(app: FastAPI):
    """
    是什么：init_dynamic_cors 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    try:
        with Session(engine) as session:
            list_result = session.exec(select(AssistantModel).order_by(AssistantModel.create_time)).all()
            seen = set()
            unique_domains = []
            for item in list_result:
                if item.domain:
                    for domain in get_domain_list(item.domain):
                        domain = domain.strip()
                        if domain and domain not in seen:
                            seen.add(domain)
                            unique_domains.append(domain)
            cors_middleware = None
            response_middleware = None
            for middleware in app.user_middleware:
                if not cors_middleware and middleware.cls == CORSMiddleware:
                    cors_middleware = middleware
                if not response_middleware and middleware.cls == ResponseMiddleware:
                    response_middleware = middleware
                if cors_middleware and response_middleware:
                    break

            updated_origins = list(set(settings.all_cors_origins + unique_domains))
            if cors_middleware:
                cors_middleware.kwargs['allow_origins'] = updated_origins
            if response_middleware:
                for instance in ResponseMiddleware.instances:
                    instance.update_allow_origins(updated_origins)

    except Exception as e:
        return False, e


class AssistantOutDs:
    """
    类说明：AssistantOutDs 把系统管理相关的数据和行为放在一起，便于其他代码直接复用。
    """
    assistant: AssistantHeader
    ds_list: Optional[list[AssistantOutDsSchema]] = None
    certificate: Optional[str] = None
    request_origin: Optional[str] = None

    def __init__(self, assistant: AssistantHeader):
        """
        是什么：AssistantOutDs.__init__ 是 AssistantOutDs 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：创建 AssistantOutDs 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.assistant = assistant
        self.ds_list = None
        self.certificate = assistant.certificate
        self.request_origin = assistant.request_origin
        self.get_ds_from_api()

    # @cache(namespace=CacheNamespace.EMBEDDED_INFO, cacheName=CacheName.ASSISTANT_DS, keyExpression="current_user.id")
    def get_ds_from_api(self):
        """
        是什么：AssistantOutDs.get_ds_from_api 是 AssistantOutDs 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：拿到 AssistantOutDs 对象的代码，需要完成这个动作时会调用它。
        做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
        """
        config: dict[any] = json.loads(self.assistant.configuration)
        endpoint: str = config['endpoint']
        endpoint = self.get_complete_endpoint(endpoint=endpoint)
        if not endpoint:
            raise Exception(
                f"Failed to get datasource list from {config['endpoint']}, error: [Assistant domain or endpoint miss]")
        certificateList: list[any] = json.loads(self.certificate)
        header = {}
        cookies = {}
        param = {}
        for item in certificateList:
            if item['target'] == 'header':
                header[item['key']] = item['value']
            if item['target'] == 'cookie':
                cookies[item['key']] = item['value']
            if item['target'] == 'param':
                param[item['key']] = item['value']
        timeout = int(config.get('timeout')) if config.get('timeout') else 10
        res = requests.get(url=endpoint, params=param, headers=header, cookies=cookies, timeout=timeout)
        if res.status_code == 200:
            result_json: dict[any] = json.loads(res.text)
            if result_json.get('code') == 0 or result_json.get('code') == 200:
                temp_list = result_json.get('data', [])
                temp_ds_list = [
                    self.convert2schema(item, config)
                    for item in temp_list
                ]
                self.ds_list = temp_ds_list
                return self.ds_list
            else:
                raise Exception(f"Failed to get datasource list from {endpoint}, error: {result_json.get('message')}")
        else:
            AppLogUtil.error(f"Failed to get datasource list from {endpoint}, response: {res}")
            raise Exception(f"Failed to get datasource list from {endpoint}, response: {res}")

    def get_first_element(self, text: str):
        """
        是什么：AssistantOutDs.get_first_element 是 AssistantOutDs 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：拿到 AssistantOutDs 对象的代码，需要完成这个动作时会调用它。
        做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
        """
        parts = re.split(r'[,;]', text.strip())
        first_domain = parts[0].strip()
        return first_domain

    def get_complete_endpoint(self, endpoint: str) -> str | None:
        """
        是什么：AssistantOutDs.get_complete_endpoint 是 AssistantOutDs 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：拿到 AssistantOutDs 对象的代码，需要完成这个动作时会调用它。
        做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
        """
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        domain_text = self.assistant.domain
        if not domain_text:
            return None
        if ',' in domain_text or ';' in domain_text:
            return (
                self.request_origin.strip('/') if self.request_origin else self.get_first_element(domain_text).strip(
                    '/')) + endpoint
        else:
            return f"{domain_text}{endpoint}"

    def get_simple_ds_list(self):
        """
        是什么：AssistantOutDs.get_simple_ds_list 是 AssistantOutDs 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：拿到 AssistantOutDs 对象的代码，需要完成这个动作时会调用它。
        做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
        """
        if self.ds_list:
            return [{'id': ds.id, 'name': ds.name, 'description': ds.comment} for ds in self.ds_list]
        else:
            raise Exception("Datasource list is not found.")

    def get_db_schema(self, ds_id: int, question: str = '', embedding: bool = True,
                      table_list: list[str] = None) -> tuple[str, list]:
        """
        是什么：AssistantOutDs.get_db_schema 是 AssistantOutDs 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：拿到 AssistantOutDs 对象的代码，需要完成这个动作时会调用它。
        做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
        """
        ds = self.get_ds(ds_id)
        schema_str = ""
        db_name = ds.db_schema if ds.db_schema is not None and ds.db_schema != "" else ds.dataBase
        schema_str += f"【DB_ID】 {db_name}\n【Schema】\n"
        tables = []
        table_name_list = []
        i = 0
        for table in ds.tables:
            # 如果传入了 table_list，则只处理在列表中的表
            if table_list is not None and table.name not in table_list:
                continue

            i += 1
            schema_table = ''
            schema_table += f"# Table: {db_name}.{table.name}" if ds.type != "mysql" and ds.type != "es" else f"# Table: {table.name}"
            table_comment = table.comment
            if table_comment == '':
                schema_table += '\n[\n'
            else:
                schema_table += f", {table_comment}\n[\n"

            field_list = []
            for field in table.fields:
                field_comment = field.comment
                if field_comment == '':
                    field_list.append(f"({field.name}:{field.type})")
                else:
                    field_list.append(f"({field.name}:{field.type}, {field_comment})")
            schema_table += ",\n".join(field_list)
            schema_table += '\n]\n'
            t_obj = {"id": i, "schema_table": schema_table}
            tables.append(t_obj)
            table_name_list.append(table.name)

        # 执行表向量化
        # if embedding and tables and settings.TABLE_EMBEDDING_ENABLED:
        #     tables = get_table_embedding(tables, question)

        if tables:
            for s in tables:
                schema_str += s.get('schema_table')

        return schema_str, table_name_list

    def get_ds(self, ds_id: int, trans: Trans = None):
        """
        是什么：AssistantOutDs.get_ds 是 AssistantOutDs 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：拿到 AssistantOutDs 对象的代码，需要完成这个动作时会调用它。
        做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
        """
        if self.ds_list:
            for ds in self.ds_list:
                if ds.id == ds_id:
                    return ds
        else:
            raise Exception("Datasource list is not found.")
        raise Exception(f"Datasource id {ds_id} is not found." if trans is None else trans(
            'i18n_common.datasource_id_not_found', key=ds_id))

    def convert2schema(self, ds_dict: dict, config: dict[any]) -> AssistantOutDsSchema:
        """
        是什么：AssistantOutDs.convert2schema 是 AssistantOutDs 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：拿到 AssistantOutDs 对象的代码，需要完成这个动作时会调用它。
        做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
        """
        id_marker: str = ''
        attr_list = ['name', 'type', 'host', 'port', 'user', 'dataBase', 'schema', 'mode']
        if config.get('encrypt', False):
            from common.utils.aes_crypto import simple_aes_decrypt

            key = config.get('aes_key', None)
            iv = config.get('aes_iv', None)
            aes_attrs = ['host', 'user', 'password', 'dataBase', 'db_schema', 'schema', 'mode']
            for attr in aes_attrs:
                if attr in ds_dict and ds_dict[attr]:
                    try:
                        ds_dict[attr] = simple_aes_decrypt(ds_dict[attr], key, iv)
                    except Exception as e:
                        raise Exception(
                            f"Failed to encrypt {attr} for datasource {ds_dict.get('name')}, error: {str(e)}")

        id = ds_dict.get('id', None)
        if not id:
            for attr in attr_list:
                if attr in ds_dict:
                    id_marker += str(ds_dict.get(attr, '')) + '--shuzhi--'
            id = string_to_numeric_hash(id_marker)
        db_schema = ds_dict.get('schema', ds_dict.get('db_schema', ''))
        ds_dict.pop("schema", None)
        return AssistantOutDsSchema(**{**ds_dict, "id": id, "db_schema": db_schema})


class AssistantOutDsFactory:
    """
    类说明：AssistantOutDsFactory 把系统管理相关的数据和行为放在一起，便于其他代码直接复用。
    """
    @staticmethod
    def get_instance(assistant: AssistantHeader) -> AssistantOutDs:
        """
        是什么：AssistantOutDsFactory.get_instance 是 AssistantOutDsFactory 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
        """
        return AssistantOutDs(assistant)


def get_out_ds_conf(ds: AssistantOutDsSchema, timeout: int = 30) -> str:
    """
    是什么：get_out_ds_conf 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    conf = {
        "host": ds.host or '',
        "port": ds.port or 0,
        "username": ds.user or '',
        "password": ds.password or '',
        "database": ds.dataBase or '',
        "driver": '',
        "extraJdbc": ds.extraParams or '',
        "dbSchema": ds.db_schema or '',
        "timeout": timeout or 30,
        "mode": ds.mode or ''
    }
    conf["extraJdbc"] = ''
    return aes_encrypt(json.dumps(conf))
