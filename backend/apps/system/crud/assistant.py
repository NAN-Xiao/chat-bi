

import json
from typing import Optional
from fastapi import FastAPI
import requests
from sqlmodel import Session, select
from apps.datasource.models.datasource import CoreDatasource
from apps.system.models.system_model import AssistantModel
from apps.system.schemas.auth import CacheName, CacheNamespace
from apps.system.schemas.system_schema import AssistantOutDsSchema, UserInfoDTO
from common.core.sqlbot_cache import cache
from common.core.db import engine
from starlette.middleware.cors import CORSMiddleware
from common.core.config import settings

@cache(namespace=CacheNamespace.EMBEDDED_INFO, cacheName=CacheName.ASSISTANT_INFO, keyExpression="assistant_id")
async def get_assistant_info(*, session: Session, assistant_id: int) -> AssistantModel | None:
    db_model = session.get(AssistantModel, assistant_id)
    return db_model

def get_assistant_user(*, id: int):
    return UserInfoDTO(id=id, account="sqlbot-inner-assistant", oid=1, name="sqlbot-inner-assistant", email="sqlbot-inner-assistant@sqlbot.com")

# def get_assistant_ds(*, session: Session, assistant: AssistantModel):
def get_assistant_ds(llm_service) -> list[dict]:
    assistant: AssistantModel = llm_service.current_assistant
    session: Session = llm_service.session
    type = assistant.type
    if type == 0:
        configuration = assistant.configuration
        if configuration:
            config: dict[any] = json.loads(configuration)
            oid: str = config['oid']
            stmt = select(CoreDatasource.id, CoreDatasource.name, CoreDatasource.description).where(CoreDatasource.oid == oid)
            private_list:list[int] = config.get('private_list') or None
            if private_list:
                stmt.where(~CoreDatasource.id.in_(private_list))
        db_ds_list = session.exec(stmt)
        
        result_list = [
            {
                "id": ds.id,
                "name": ds.name,
                "description": ds.description
            }
            for ds in db_ds_list
        ]
    
        # filter private ds if offline
        return result_list
    out_ds_instance: AssistantOutDs = AssistantOutDsFactory.get_instance(assistant, llm_service.assistant_certificate)
    llm_service.out_ds_instance = out_ds_instance
    dslist = out_ds_instance.get_simple_ds_list()
    # format?
    return dslist

def init_dynamic_cors(app: FastAPI):
    try: 
        with Session(engine) as session:
            list_result = session.exec(select(AssistantModel).order_by(AssistantModel.create_time)).all()
            seen = set()
            unique_domains = []
            for item in list_result:
                if item.domain:
                    for domain in item.domain.split(','):
                        domain = domain.strip()
                        if domain and domain not in seen:
                            seen.add(domain)
                            unique_domains.append(domain)
            cors_middleware = None
            for middleware in app.user_middleware:
                if middleware.cls == CORSMiddleware:
                    cors_middleware = middleware
                    break
            if cors_middleware:
                updated_origins = list(set(settings.all_cors_origins + unique_domains))
                cors_middleware.kwargs['allow_origins'] = updated_origins
    except Exception as e:
        return False, e
    
    

class AssistantOutDs:
    assistant: AssistantModel
    ds_list: Optional[list[AssistantOutDsSchema]] = None
    certificate: Optional[str] = None
    def __init__(self, assistant: AssistantModel, certificate: Optional[str] = None):
        self.assistant = assistant
        self.ds_list = None
        self.certificate = certificate
        self.get_ds_from_api(certificate)
        
    #@cache(namespace=CacheNamespace.EMBEDDED_INFO, cacheName=CacheName.ASSISTANT_DS, keyExpression="current_user.id")    
    async def get_ds_from_api(self, certificate: Optional[str] = None):
        config: dict[any] = json.loads(self.assistant.configuration)
        endpoint: str = config['endpoint']
        certificateList: list[any] = json.loads(certificate)
        header = {}
        cookies = {}
        for item in certificateList:
            if item['target'] == 'head':
                header[item['key']] = item['value']
            if item['target'] == 'cookie':
                cookies[item['key']] = item['value']
        
        res = requests.get(url=endpoint, headers=header, cookies=cookies, timeout=10)
        if res.status_code == 200:
            result_json: dict[any] = json.loads(res.json())
            if result_json.get('code') == 0:
                temp_list = result_json.get('data', [])
                self.ds_list = [
                    AssistantOutDsSchema(**{**item, "id": idx})
                    for idx, item in enumerate(temp_list, start=1)
                ]
                
                return self.ds_list
            else:
                raise Exception(f"Failed to get datasource list from {endpoint}, error: {result_json.get('message')}")
        else:
            raise Exception(f"Failed to get datasource list from {endpoint}, status code: {res.status_code}")
    
    def get_simple_ds_list(self):
        if self.ds_list:
            return [{'id': ds.id, 'name': ds.name, 'description': ds.comment} for ds in self.ds_list]
        else:
            raise Exception("Datasource list is not found.")
       
    def get_db_schema(self, ds_id: int) -> str:
        ds = self.get_ds(ds_id)
        schema_str = ""
        db_name = ds.schema
        schema_str += f"【DB_ID】 {db_name}\n【Schema】\n"
        for table in ds.tables:
            schema_str += f"# Table: {db_name}.{table.name}"
            schema_str += f", {table.comment}\n[\n"
            field_list = []
            for field in table.fields:
                field_list.append(f"({field.name}:{field.type}, {field.comment})")
            schema_str += ",\n".join(field_list)
            schema_str += '\n]\n'
        return schema_str
    
    def get_ds(self, ds_id: int):
        if self.ds_list:
            for ds in self.ds_list:
                if ds['id'] == ds_id:
                    return ds
        else:
            raise Exception("Datasource list is not found.")
        raise Exception(f"Datasource with id {ds_id} not found.")
    def get_ds_engine(self, ds_id: int):
        ds = self.get_ds(ds_id)
        ds_type =  ds.get('type') if ds else None
        if not ds_type:
            raise Exception(f"Datasource with id {ds_id} not found or type is not defined.")
        return ds_type
    
class AssistantOutDsFactory:
    @staticmethod
    def get_instance(assistant: AssistantModel, certificate: Optional[str] = None) -> AssistantOutDs:
        return AssistantOutDs(assistant, certificate)
    