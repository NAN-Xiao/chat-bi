from typing import Optional
from fastapi import APIRouter, Query
from sqlmodel import func, or_, select
from apps.system.crud.user import get_db_user, user_ws_options
from apps.system.models.system_model import UserWsModel, WorkspaceModel
from apps.system.models.user import UserModel
from apps.system.schemas.auth import CacheName, CacheNamespace
from apps.system.schemas.system_schema import PwdEditor, UserCreator, UserEditor, UserGrid, UserLanguage, UserWs
from common.core.deps import CurrentUser, SessionDep, Trans
from common.core.pagination import Paginator
from common.core.schemas import PaginatedResponse, PaginationParams
from common.core.security import md5pwd, verify_md5pwd
from common.core.sqlbot_cache import clear_cache
router = APIRouter(tags=["user"], prefix="/user")

@router.get("/info")
async def user_info(current_user: CurrentUser):
    return current_user

@router.get("/pager/{pageNum}/{pageSize}", response_model=PaginatedResponse[UserGrid])
async def pager(
    session: SessionDep,
    pageNum: int,
    pageSize: int,
    keyword: Optional[str] = Query(None, description="搜索关键字(可选)"),
    status: Optional[int] = Query(None, description="状态"),
    origins: Optional[list[int]] = Query(None, description="来源"),
    oidlist: Optional[list[int]] = Query(None, description="空间ID集合(可选)"),
):
    pagination = PaginationParams(page=pageNum, size=pageSize)
    paginator = Paginator(session)
    filters = {}
        
    stmt = (
        select(
            UserModel,
            func.coalesce(func.string_agg(WorkspaceModel.name, ','), '').label("space_name")
        )
        .join(UserWsModel, UserModel.id == UserWsModel.uid, isouter=True)
        .join(WorkspaceModel, UserWsModel.oid == WorkspaceModel.id, isouter=True)
        .group_by(UserModel.id)
        .order_by(UserModel.create_time)
    )
    
    if status is not None:
        stmt = stmt.where(UserModel.status == status)
    
    if oidlist:
        user_filter = (
            select(UserModel.id)
            .join(UserWsModel, UserModel.id == UserWsModel.uid)
            .where(UserWsModel.oid.in_(oidlist))
            .distinct()
        )
        stmt = stmt.where(UserModel.id.in_(user_filter))
    
    """ if origins is not None:
        stmt = stmt.where(UserModel.origin == origins) """
    
    if keyword:
        keyword_pattern = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                UserModel.account.ilike(keyword_pattern),
                UserModel.name.ilike(keyword_pattern),
                UserModel.email.ilike(keyword_pattern)
            )
        )
        
    return await paginator.get_paginated_response(
        stmt=stmt,
        pagination=pagination,
        **filters)

@router.get("/ws")
async def ws_options(session: SessionDep, current_user: CurrentUser, trans: Trans) -> list[UserWs]:
    return await user_ws_options(session, current_user.id, trans)

@router.put("/ws/{oid}")
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="current_user.id")
async def ws_change(session: SessionDep, current_user: CurrentUser, oid: int):
    ws_list: list[UserWs] = await user_ws_options(session, current_user.id)
    if not any(x.id == oid for x in ws_list):
        raise RuntimeError(f"oid [{oid}] is invalid!")
    user_model: UserModel = get_db_user(session = session, user_id = current_user.id)
    user_model.oid = oid
    session.add(user_model)
    session.commit()

@router.get("/{id}", response_model=UserEditor)
async def query(session: SessionDep, id: int) -> UserEditor:
    db_user: UserModel = get_db_user(session = session, user_id = id)
    return db_user

@router.post("")
async def create(session: SessionDep, creator: UserCreator):
    data = creator.model_dump(exclude_unset=True)
    user_model = UserModel.model_validate(data)
    #user_model.create_time = get_timestamp()
    user_model.language = "zh-CN"
    session.add(user_model)
    session.commit()
    
@router.put("")
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="editor.id")
async def update(session: SessionDep, editor: UserEditor):
    user_model: UserModel = get_db_user(session = session, user_id = editor.id)
    data = editor.model_dump(exclude_unset=True)
    user_model.sqlmodel_update(data)
    session.add(user_model)
    session.commit()
    
@router.delete("/{id}")
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="id")
async def delete(session: SessionDep, id: int):
    user_model: UserModel = get_db_user(session = session, user_id = id)
    session.delete(user_model)
    session.commit()

@router.delete("")    
async def batch_del(session: SessionDep, id_list: list[int]):
    for id in id_list:
        delete(session, id)
    
@router.put("/language")
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="current_user.id")
async def langChange(session: SessionDep, current_user: CurrentUser, language: UserLanguage):
    lang = language.language
    if lang not in ["zh-CN", "en"]:
        return {"message": "Language not supported"}
    db_user: UserModel = get_db_user(session=session, user_id=current_user.id)
    db_user.language = lang
    session.add(db_user)
    session.commit()

@router.put("/pwd")
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="current_user.id")
async def pwdUpdate(session: SessionDep, current_user: CurrentUser, editor: PwdEditor):
    db_user: UserModel = get_db_user(session=session, user_id=current_user.id)
    if not verify_md5pwd(editor.pwd, db_user.password):
        raise RuntimeError("pwd error")
    db_user.password = md5pwd(editor.new_pwd)
    session.add(db_user)
    session.commit()