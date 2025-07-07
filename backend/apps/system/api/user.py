from fastapi import APIRouter
from apps.system.crud.user import get_db_user, get_user_info
from apps.system.models.user import UserModel
from apps.system.schemas.system_schema import UserCreator, UserEditor, UserGrid, UserLanguage
from common.core.deps import CurrentUser, SessionDep
from common.core.pagination import Paginator
from common.core.schemas import PaginatedResponse, PaginationParams
from common.utils.time import get_timestamp

router = APIRouter(tags=["user"], prefix="/user")


@router.get("/info")
async def user_info(session: SessionDep, current_user: CurrentUser):
    db_user = get_user_info(session=session, user_id=current_user.id)
    if not db_user:
        return {"message": "User not found"}
    db_user.password = None
    return db_user


@router.get("/pager/{pageNum}/{pageSize}", response_model=PaginatedResponse[UserGrid])
async def pager(
    session: SessionDep,
    pageNum: int,
    pageSize: int
):
    pagination = PaginationParams(page=pageNum, size=pageSize)
    paginator = Paginator(session)
    filters = {}
    return await paginator.get_paginated_response(
        model=UserModel,
        pagination=pagination,
        **filters)

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
async def update(session: SessionDep, editor: UserEditor):
    user_model: UserModel = get_db_user(session = session, user_id = editor.id)
    data = editor.model_dump(exclude_unset=True)
    user_model.sqlmodel_update(data)
    session.add(user_model)
    session.commit()
    
@router.delete("/{id}") 
async def delete(session: SessionDep, id: int):
    user_model: UserModel = get_db_user(session = session, user_id = id)
    session.delete(user_model)
    session.commit()
    
@router.put("/language")
async def langChange(session: SessionDep, current_user: CurrentUser, language: UserLanguage):
    lang = language.language
    if lang not in ["zh-CN", "en"]:
        return {"message": "Language not supported"}
    db_user = session.get(UserModel, current_user.id)
    if not db_user:
        return {"message": "User not found"}
    db_user.language = lang
    session.add(db_user)
    session.commit()
    return {"message": "Language changed successfully", "language": lang}