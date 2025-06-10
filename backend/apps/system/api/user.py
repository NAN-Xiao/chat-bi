from fastapi import APIRouter, Depends, Request    
from apps.system.crud.user import get_user_info
from apps.system.models.user import user_grid
from apps.system.schemas.system_schema import UserLanguage
from common.core.deps import CurrentUser, SessionDep
from common.core.pagination import Paginator
from common.core.schemas import PaginatedResponse, PaginationParams

router = APIRouter(tags=["user"], prefix="/user")


@router.get("/info")
async def user_info(session: SessionDep, current_user: CurrentUser):
    db_user = get_user_info(session=session, user_id=current_user.id)
    if not db_user:
        return {"message": "User not found"}
    db_user.password = None
    return db_user


@router.get("/pager/{pageNum}/{pageSize}", response_model=PaginatedResponse[user_grid])
async def pager(
    session: SessionDep,
    pageNum: int,
    pageSize: int
):
    pagination = PaginationParams(page=pageNum, size=pageSize)
    paginator = Paginator(session)
    filters = {}
    return await paginator.get_paginated_response(
        model=user_grid,
        pagination=pagination,
        **filters)
    
@router.put("/language")
async def langChange(session: SessionDep, current_user: CurrentUser, language: UserLanguage):
    lang = language.language
    if lang not in ["zh-CN", "en"]:
        return {"message": "Language not supported"}
    db_user = get_user_info(session=session, user_id=current_user.id)
    if not db_user:
        return {"message": "User not found"}
    db_user.language = lang
    session.add(db_user)
    session.commit()
    return {"message": "Language changed successfully", "language": lang}