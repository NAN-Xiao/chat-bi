"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from sqlalchemy import Row, Select
from sqlmodel import Session, select, func, SQLModel
from typing import Dict, Type, TypeVar, Sequence, Optional
from common.core.schemas import PaginationParams, PaginatedResponse
from sqlmodel.sql.expression import SelectOfScalar
from typing import Union, Any

ModelT = TypeVar('ModelT', bound=SQLModel)

class Paginator:
    """
    类说明：Paginator 把后端基础能力相关的数据和行为放在一起，便于其他代码直接复用。
    """
    def __init__(self, session: Session):
        """
        是什么：Paginator.__init__ 是 Paginator 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：创建 Paginator 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.session = session
    def _process_result_row(self, row: Row) -> Dict[str, Any]:
        """
        是什么：Paginator._process_result_row 是 Paginator 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：拿到 Paginator 对象的代码，需要完成这个动作时会调用它。
        做了什么：把后端基础能力的主要流程跑起来，一步步调用需要的处理。
        """
        result_dict = {}
        if isinstance(row, int):
            return {'id': row}
        if isinstance(row, SQLModel) and not hasattr(row, '_fields'):
            return row.model_dump()
        for item, key in zip(row, row._fields):
            if isinstance(item, SQLModel):
                result_dict.update(item.model_dump())
            else:
                result_dict[key] = item
                
        return result_dict
    async def paginate(
        self,
        stmt: Union[Select, SelectOfScalar, Type[ModelT]],
        page: int = 1,
        size: int = 20,
        order_by: Optional[str] = None,
        desc: bool = False,
        **filters
    ) -> tuple[Sequence[Any], int]:
        """
        是什么：Paginator.paginate 是 Paginator 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：拿到 Paginator 对象的代码，需要完成这个动作时会调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        offset = (page - 1) * size
        single_model: bool = False
        if isinstance(stmt, type) and issubclass(stmt, SQLModel):
            stmt = select(stmt)
            single_model = True
        
        # 应用过滤条件
        for field, value in filters.items():
            if value is not None:
                # 处理关联模型的字段 (如 user.name)
                if '.' in field:
                    related_model, related_field = field.split('.')
                    # 这里需要根据实际关联关系调整
                    stmt = stmt.where(getattr(getattr(stmt.selected_columns, related_model), related_field) == value)
                else:
                    stmt = stmt.where(getattr(stmt.selected_columns, field) == value)
        
        # 应用排序
        if order_by:
            if '.' in order_by:
                related_model, related_field = order_by.split('.')
                column = getattr(getattr(stmt.selected_columns, related_model), related_field)
            else:
                column = getattr(stmt.selected_columns, order_by)
            stmt = stmt.order_by(column.desc() if desc else column.asc())
        
        # 计算总数
        """ count_stmt = stmt.with_only_columns(func.count(), maintain_column_froms=True)
        result = self.session.exec(count_stmt)
        total: int = result.first() """
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = self.session.exec(count_stmt)
        total: int = total_result.first()
        
        # 应用分页
        stmt = stmt.offset(offset).limit(size)
        
        # 执行查询
        result = self.session.exec(stmt)
        if not single_model:
            items = [self._process_result_row(row) for row in result]
        else:
            items = result.all()
        return items, total

    async def get_paginated_response(
        self,
        stmt: Union[Select, SelectOfScalar, Type[ModelT]],
        pagination: PaginationParams,
        **filters
    ) -> PaginatedResponse[Any]:
        """
        是什么：Paginator.get_paginated_response 是 Paginator 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：拿到 Paginator 对象的代码，需要完成这个动作时会调用它。
        做了什么：把后端基础能力需要的数据找出来，整理成后面好用的样子。
        """
        items, total = await self.paginate(
            stmt=stmt,
            page=pagination.page,
            size=pagination.size,
            order_by=pagination.order_by,
            desc=pagination.desc,
            **filters
        )
        
        total_pages = (total + pagination.size - 1) // pagination.size
        
        return PaginatedResponse[Any](
            items=items,
            total=total,
            page=pagination.page,
            size=pagination.size,
            total_pages=total_pages
        )