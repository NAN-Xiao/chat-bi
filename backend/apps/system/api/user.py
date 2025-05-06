from fastapi import APIRouter, Depends, Request    
from apps.system.models.user import user_grid
from common.core.deps import CurrentUser, SessionDep
from common.core.pagination import Paginator
from common.core.schemas import PaginatedResponse, PaginationParams

router = APIRouter(tags=["user"], prefix="/user")


@router.get("/info")
async def user_info(current_user: CurrentUser):
    return current_user.to_dict()


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