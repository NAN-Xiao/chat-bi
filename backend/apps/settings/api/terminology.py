from fastapi import APIRouter    
from apps.settings.models.setting_models import term_model
from common.core.deps import SessionDep
from common.core.pagination import Paginator
from common.core.schemas import PaginatedResponse, PaginationParams
router = APIRouter(tags=["Settings"], prefix="/settings/terminology")


@router.get("/pager/{pageNum}/{pageSize}", response_model=PaginatedResponse[term_model])
async def pager(
    session: SessionDep,
    pageNum: int,
    pageSize: int
):
    pagination = PaginationParams(page=pageNum, size=pageSize)
    paginator = Paginator(session)
    filters = {}
    return await paginator.get_paginated_response(
        model=term_model,
        pagination=pagination,
        **filters)