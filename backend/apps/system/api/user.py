from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from sqlmodel import func, or_, select, delete as sqlmodel_delete
from apps.system.crud.user import clean_user_cache, get_db_user, single_delete, user_ws_options
from apps.system.models.system_model import UserWsModel
from apps.system.models.user import UserModel
from apps.system.schemas.auth import CacheName, CacheNamespace
from apps.system.schemas.system_schema import PwdEditor, UserCreator, UserEditor, UserGrid, UserLanguage, UserWs
from common.core.deps import CurrentUser, SessionDep, Trans
from common.core.pagination import Paginator
from common.core.schemas import PaginatedResponse, PaginationParams
from common.core.security import default_md5_pwd, md5pwd, verify_md5pwd
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
            func.coalesce(
                func.array_remove(
                    func.array_agg(UserWsModel.oid),
                    None
                ),
                []
            ).label("oid_list")
            #func.coalesce(func.string_agg(WorkspaceModel.name, ','), '').label("space_name")
        )
        .join(UserWsModel, UserModel.id == UserWsModel.uid, isouter=True)
        #.join(WorkspaceModel, UserWsModel.oid == WorkspaceModel.id, isouter=True)
        .where(UserModel.id != 1)
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
        
    user_page = await paginator.get_paginated_response(
        stmt=stmt,
        pagination=pagination,
        **filters)
    
    """ for item in user_page.items:
        space_name: str = item['space_name']
        if space_name and 'i18n_default_workspace' in space_name:
            parts = list(map(
                lambda x: trans(x) if x == "i18n_default_workspace" else x,
                space_name.split(',')
            ))
            output_str = ','.join(parts)
            item['space_name'] = output_str """
    return user_page

@router.get("/ws")
async def ws_options(session: SessionDep, current_user: CurrentUser, trans: Trans) -> list[UserWs]:
    return await user_ws_options(session, current_user.id, trans)

@router.put("/ws/{oid}")
# @clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="current_user.id")
async def ws_change(session: SessionDep, current_user: CurrentUser, oid: int):
    ws_list: list[UserWs] = await user_ws_options(session, current_user.id)
    if not any(x.id == oid for x in ws_list):
        raise HTTPException(f"oid [{oid}] is invalid!")
    user_model: UserModel = get_db_user(session = session, user_id = current_user.id)
    user_model.oid = oid
    await clean_user_cache(user_model.id)
    session.add(user_model)
    session.commit()

@router.get("/{id}", response_model=UserEditor)
async def query(session: SessionDep, trans: Trans, id: int) -> UserEditor:
    db_user: UserModel = get_db_user(session = session, user_id = id)
    u_ws_options = await user_ws_options(session, id, trans)
    result = UserEditor.model_validate(db_user.model_dump())
    if u_ws_options:
        result.oid_list = [item.id for item in u_ws_options]
    return result

@router.post("")
async def create(session: SessionDep, creator: UserCreator):
    data = creator.model_dump(exclude_unset=True)
    user_model = UserModel.model_validate(data)
    #user_model.create_time = get_timestamp()
    user_model.language = "zh-CN"
    user_model.oid = 0
    if creator.oid_list:
        # need to validate oid_list
        db_model_list = [
            UserWsModel.model_validate({
                "oid": oid,
                "uid": user_model.id,
                "weight": 0
            })
            for oid in creator.oid_list
        ]
        session.add_all(db_model_list)
        user_model.oid = creator.oid_list[0]   
    session.add(user_model)
    session.commit()
    
@router.put("")
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="editor.id")
async def update(session: SessionDep, editor: UserEditor):
    user_model: UserModel = get_db_user(session = session, user_id = editor.id)
    origin_oid: int = user_model.oid
    del_stmt = sqlmodel_delete(UserWsModel).where(UserWsModel.uid == editor.id)
    session.exec(del_stmt)
    
    data = editor.model_dump(exclude_unset=True)
    user_model.sqlmodel_update(data)
    
    user_model.oid = 0
    if editor.oid_list:
        # need to validate oid_list
        db_model_list = [
            UserWsModel.model_validate({
                "oid": oid,
                "uid": user_model.id,
                "weight": 0
            })
            for oid in editor.oid_list
        ]
        session.add_all(db_model_list)
        user_model.oid = origin_oid if origin_oid in editor.oid_list else  editor.oid_list[0]
    session.add(user_model)
    session.commit()
    
@router.delete("/{id}")
async def delete(session: SessionDep, id: int):
    await single_delete(session, id)

@router.delete("")    
async def batch_del(session: SessionDep, id_list: list[int]):
    for id in id_list:
        await single_delete(session, id)
    
@router.put("/language")
#@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="current_user.id")
async def langChange(session: SessionDep, current_user: CurrentUser, language: UserLanguage):
    lang = language.language
    if lang not in ["zh-CN", "en"]:
        return {"message": "Language not supported"}
    db_user: UserModel = get_db_user(session=session, user_id=current_user.id)
    db_user.language = lang
    await clean_user_cache(db_user.id)
    session.add(db_user)
    session.commit()
    
@router.patch("/pwd/{id}")
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="id")
async def pwdReset(session: SessionDep, current_user: CurrentUser, id: int):
    if not current_user.isAdmin:
        raise HTTPException('only for admin')
    db_user: UserModel = get_db_user(session=session, user_id=id)
    db_user.password = default_md5_pwd()
    session.add(db_user)
    session.commit()

@router.put("/pwd")
#@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="current_user.id")
async def pwdUpdate(session: SessionDep, current_user: CurrentUser, editor: PwdEditor):
    db_user: UserModel = get_db_user(session=session, user_id=current_user.id)
    if not verify_md5pwd(editor.pwd, db_user.password):
        raise HTTPException("pwd error")
    db_user.password = md5pwd(editor.new_pwd)
    await clean_user_cache(db_user.id)
    session.add(db_user)
    session.commit()