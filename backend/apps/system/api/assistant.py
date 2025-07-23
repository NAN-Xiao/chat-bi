from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, FastAPI, Query, Request, Response
from sqlmodel import Session, select
from apps.system.crud.assistant import get_assistant_info
from apps.system.models.system_model import AssistantModel
from apps.system.schemas.auth import CacheName, CacheNamespace
from apps.system.schemas.system_schema import AssistantBase, AssistantDTO, AssistantValidator
from common.core.deps import SessionDep
from common.core.security import create_access_token
from common.core.sqlbot_cache import clear_cache
from common.utils.time import get_timestamp
from starlette.middleware.cors import CORSMiddleware
from common.core.config import settings
router = APIRouter(tags=["system/assistant"], prefix="/system/assistant")

@router.get("/info/{id}") 
async def info(request: Request, response: Response, session: SessionDep, id: int) -> dict:
    db_model = await get_assistant_info(session=session, assistant_id=id)
    if not db_model:
        raise RuntimeError(f"assistant application not exist")
    db_model = AssistantModel.model_validate(db_model)
    response.headers["Access-Control-Allow-Origin"] = db_model.domain
    origin = request.headers.get("origin") or request.headers.get("referer")
    origin = origin.rstrip('/')
    """ if origin != db_model.domain:
        raise RuntimeError("invalid domain [{origin}]") """
    return db_model.model_dump()

@router.get("/validator", response_model=AssistantValidator) 
async def info(session: SessionDep, id: str, virtual: Optional[int] = Query(None), online: Optional[bool] = Query(default=False)):
    db_model = await get_assistant_info(session=session, assistant_id=id)
    if not db_model:
        return AssistantValidator()
    db_model = AssistantModel.model_validate(db_model)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    assistantDict = {
        "id": virtual, "account": 'sqlbot-inner-assistant', "oid": 1, "assistant_id": id
    }
    access_token = create_access_token(
        assistantDict, expires_delta=access_token_expires
    )
    return AssistantValidator(True, True, True, access_token)
        

@router.get("", response_model=list[AssistantModel])
async def query(session: SessionDep):
    list_result = session.exec(select(AssistantModel).order_by(AssistantModel.create_time.asc())).all()
    return list_result

@router.post("")
async def add(request: Request, session: SessionDep, creator: AssistantBase):
    db_model = AssistantModel.model_validate(creator)
    db_model.create_time = get_timestamp()
    session.add(db_model)
    session.commit()
    dynamic_upgrade_cors(request=request, session=session)

    
@router.put("")
@clear_cache(namespace=CacheNamespace.EMBEDDED_INFO, cacheName=CacheName.ASSISTANT_INFO, keyExpression="editor.id")  
async def update(request: Request, session: SessionDep, editor: AssistantDTO):
    id = editor.id
    db_model = session.get(AssistantModel, id)
    if not db_model:
        raise ValueError(f"AssistantModel with id {id} not found")
    update_data = AssistantModel.model_validate(editor)
    db_model.sqlmodel_update(update_data)
    session.add(db_model)
    session.commit()
    dynamic_upgrade_cors(request=request, session=session)

@router.get("/{id}", response_model=AssistantModel)    
async def get_one(session: SessionDep, id: int):
    db_model = await get_assistant_info(session=session, assistant_id=id)
    if not db_model:
        raise ValueError(f"AssistantModel with id {id} not found")
    db_model = AssistantModel.model_validate(db_model)
    return db_model

@router.delete("/{id}")
@clear_cache(namespace=CacheNamespace.EMBEDDED_INFO, cacheName=CacheName.ASSISTANT_INFO, keyExpression="id")  
async def delete(request: Request, session: SessionDep, id: int):
    db_model = session.get(AssistantModel, id)
    if not db_model:
        raise ValueError(f"AssistantModel with id {id} not found")
    session.delete(db_model)
    session.commit()
    dynamic_upgrade_cors(request=request, session=session)

def dynamic_upgrade_cors(request: Request, session: Session):
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
    app: FastAPI = request.app
    cors_middleware = None
    for middleware in app.user_middleware:
        if middleware.cls == CORSMiddleware:
            cors_middleware = middleware
            break
    if cors_middleware:
        updated_origins = list(set(settings.all_cors_origins + unique_domains))
        cors_middleware.kwargs['allow_origins'] = updated_origins


        

    
