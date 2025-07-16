

import json
from fastapi import FastAPI
from sqlmodel import Session, select
from apps.datasource.models.datasource import CoreDatasource
from apps.system.models.system_model import AssistantModel
from apps.system.schemas.auth import CacheName, CacheNamespace
from apps.system.schemas.system_schema import UserInfoDTO
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

def get_assistant_ds(*, session: Session, assistant: AssistantModel):
    type = assistant.type
    if type == 0:
        stmt = select(CoreDatasource.id, CoreDatasource.name, CoreDatasource.description)
        configuration = assistant.configuration
        if configuration:
            config = json.loads(configuration)
            private_list:list[int] = config['private_list']
            if not private_list:
                stmt.where(~CoreDatasource.id.in_(private_list))
        db_ds_list = session.exec(stmt).all()
        # filter private ds if offline
        return db_ds_list
    out_ds_instance: AssistantOutDs = AssistantOutDsFactory.get_instance(assistant)
    dslist = out_ds_instance.get_ds_list()
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
    def get_ds_list(self):
        config: dict[any] = json.loads(self.assistant.configuration)
        url: str = config['url']
        return None
    
class AssistantOutDsFactory:
    _instance: AssistantOutDs = None
    @staticmethod
    def get_instance(cls, assistant: AssistantModel) -> AssistantOutDs:
        if not cls._instance:
            cls._instance = AssistantOutDs(assistant)
        return cls._instance
    