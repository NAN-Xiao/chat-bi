

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
    是什么：dynamic_upgrade_cors 是 backend/apps/system/crud/assistant_manage.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 dynamic_upgrade_cors 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
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
    是什么：save 是 backend/apps/system/crud/assistant_manage.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装系统管理相关对象和数据，并返回或写入对应状态。
    """
    db_model = AssistantModel.model_validate(creator.model_dump(exclude_unset=True))
    db_model.tenant_id = require_tenant_id(tenant_id)
    db_model.create_time = get_timestamp()
    session.add(db_model)
    session.commit()
    dynamic_upgrade_cors(request=request, session=session)
    return db_model
