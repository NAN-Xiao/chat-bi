from typing import Optional
from fastapi import APIRouter, Query
from sqlmodel import exists, or_, select    
from apps.system.models.system_model import UserWsModel, WorkspaceBase, WorkspaceEditor, WorkspaceModel
from apps.system.models.user import UserModel
from apps.system.schemas.system_schema import UserWsBase, UserWsDTO, UserWsOption, WorkspaceUser
from common.core.deps import CurrentUser, SessionDep, Trans
from common.core.pagination import Paginator
from common.core.schemas import PaginatedResponse, PaginationParams
from common.utils.time import get_timestamp

router = APIRouter(tags=["system/workspace"], prefix="/system/workspace")

@router.get("/uws/option/pager/{pageNum}/{pageSize}", response_model=PaginatedResponse[UserWsOption])
async def option_pager(
    session: SessionDep,
    current_user: CurrentUser,
    pageNum: int,
    pageSize: int,
    oid: int = Query(description="空间ID"),
    keyword: Optional[str] = Query(None, description="搜索关键字(可选)"),
):
    if not current_user.isAdmin:
        raise RuntimeError('only for admin')
    if not oid:
        raise RuntimeError('oid miss error')
    pagination = PaginationParams(page=pageNum, size=pageSize)
    paginator = Paginator(session)
    stmt = select(UserModel.id, UserModel.account, UserModel.name).where(
        ~exists().where(UserWsModel.uid == UserModel.id, UserWsModel.oid == oid)
    ).order_by(UserModel.create_time)
    
    if keyword:
        keyword_pattern = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                UserModel.account.ilike(keyword_pattern),
                UserModel.name.ilike(keyword_pattern),
            )
        )
    return await paginator.get_paginated_response(
        stmt=stmt,
        pagination=pagination,
    )

@router.get("/uws/pager/{pageNum}/{pageSize}", response_model=PaginatedResponse[WorkspaceUser])
async def pager(
    session: SessionDep,
    current_user: CurrentUser,
    pageNum: int,
    pageSize: int,
    keyword: Optional[str] = Query(None, description="搜索关键字(可选)"),
    oid: Optional[int] = Query(None, description="空间ID(仅admin用户生效)"),
):
    if current_user.isAdmin:
        if not oid:
            raise RuntimeError('oid miss error')
        workspace_id = oid
    else:
        workspace_id = current_user.oid
    pagination = PaginationParams(page=pageNum, size=pageSize)
    paginator = Paginator(session)
    stmt = select(UserModel.id, UserModel.account, UserModel.name, UserModel.email, UserModel.status, UserModel.create_time, UserModel.oid, UserWsModel.weight).join(
        UserWsModel, UserModel.id == UserWsModel.uid
    ).where(
        UserWsModel.oid == workspace_id,
    ).order_by(UserModel.create_time)
    
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
    )
    

@router.post("/uws")     
async def create(session: SessionDep, creator: UserWsDTO):
    # 判断uid_list以及oid合法性
    db_model_list = [
        UserWsModel.model_validate({
            "oid": creator.oid,
            "uid": uid,
            "weight": creator.weight
        })
        for uid in creator.uid_list
    ]
    session.add_all(db_model_list)
    session.commit()

@router.delete("/uws")     
async def delete(session: SessionDep, dto: UserWsBase):
    db_model_list: list[UserWsModel] = session.exec(select(UserWsModel).where(UserWsModel.uid.in_(dto.uid_list), UserWsModel.oid == dto.oid)).all()
    if not db_model_list:
        raise ValueError(f"UserWsModel not found")
    for db_model in db_model_list:
        session.delete(db_model)
    session.commit()

@router.get("", response_model=list[WorkspaceModel])
async def query(session: SessionDep, trans: Trans):
    list_result = session.exec(select(WorkspaceModel).order_by(WorkspaceModel.create_time)).all()
    for ws in list_result:
        if ws.name.startswith('i18n'):
            ws.name =  trans(ws.name)
    return list_result

@router.post("")
async def add(session: SessionDep, creator: WorkspaceBase):
    db_model = WorkspaceModel.model_validate(creator)
    db_model.create_time = get_timestamp()
    session.add(db_model)
    session.commit()
    
@router.put("")
async def update(session: SessionDep, editor: WorkspaceEditor):
    id = editor.id
    db_model = session.get(WorkspaceModel, id)
    if not db_model:
        raise ValueError(f"WorkspaceModel with id {id} not found")
    update_data = WorkspaceModel.model_validate(editor)
    db_model.sqlmodel_update(update_data)
    session.add(db_model)
    session.commit()

@router.get("/{id}", response_model=WorkspaceModel)    
async def get_one(session: SessionDep, trans: Trans, id: int):
    db_model = session.get(WorkspaceModel, id)
    if not db_model:
        raise ValueError(f"WorkspaceModel with id {id} not found")
    if db_model.name.startswith('i18n'):
        db_model.name = trans(db_model.name)
    return db_model

@router.delete("/{id}")  
async def delete(session: SessionDep, id: int):
    db_model = session.get(WorkspaceModel, id)
    if not db_model:
        raise ValueError(f"WorkspaceModel with id {id} not found")
    session.delete(db_model)
    session.commit()


