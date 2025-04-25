from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, func, SQLModel
from typing import Type, TypeVar, Sequence, Optional
from common.core.schemas import PaginationParams, PaginatedResponse

ModelT = TypeVar('ModelT', bound=SQLModel)

class Paginator:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def paginate(
        self,
        model: Type[ModelT],
        page: int = 1,
        size: int = 20,
        order_by: Optional[str] = None,
        desc: bool = False,
        **filters
    ) -> tuple[Sequence[ModelT], int]:
        offset = (page - 1) * size
        stmt = select(model)
        
        for field, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(model, field) == value)
        
        if order_by:
            column = getattr(model, order_by)
            stmt = stmt.order_by(column.desc() if desc else column.asc())
        
        count_stmt = select(func.count()).select_from(model)
        for field, value in filters.items():
            if value is not None:
                count_stmt = count_stmt.where(getattr(model, field) == value)
        
        total = (await self.session.execute(count_stmt)).scalar_one()
        
        stmt = stmt.offset(offset).limit(size)
        
        result = await self.session.execute(stmt)
        items = result.scalars().all()
        
        return items, total

    async def get_paginated_response(
        self,
        model: Type[ModelT],
        pagination: PaginationParams,
        **filters
    ) -> PaginatedResponse[ModelT]:
        items, total = await self.paginate(
            model=model,
            page=pagination.page,
            size=pagination.size,
            order_by=pagination.order_by,
            desc=pagination.desc,
            **filters
        )
        
        total_pages = (total + pagination.size - 1) // pagination.size
        
        return PaginatedResponse[ModelT](
            items=items,
            total=total,
            page=pagination.page,
            size=pagination.size,
            total_pages=total_pages
        )