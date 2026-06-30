"""
脚本说明：这个脚本封装系统管理的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""


from fastapi import FastAPI, Request
from sqlmodel import Session, select
from starlette.middleware.cors import CORSMiddleware
from apps.system.schemas.system_schema import AssistantBase
from apps.system.schemas.access_context import require_tenant_id
from common.core.config import settings
from apps.system.models.system_model import AssistantModel
from common.utils.time import get_timestamp
from common.utils.utils import get_domain_list
from common.core.response_middleware import ResponseMiddleware


def dynamic_upgrade_cors(request: Request, session: Session):
    """
    是什么：dynamic_upgrade_cors 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
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
    app: FastAPI = request.app
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

async def save(request: Request, session: Session, creator: AssistantBase, tenant_id: int | None = None):
    """
    是什么：save 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    db_model = AssistantModel.model_validate(creator.model_dump(exclude_unset=True))
    db_model.tenant_id = require_tenant_id(tenant_id)
    db_model.create_time = get_timestamp()
    session.add(db_model)
    session.commit()
    dynamic_upgrade_cors(request=request, session=session)
    return db_model
