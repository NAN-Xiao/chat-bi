# Author: Junjun
# Date: 2026/1/26
import datetime
from typing import List

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlmodel import select

from apps.system.models.system_variable_model import SystemVariable
from apps.system.crud.tenant import DEFAULT_TENANT_ID
from apps.system.crud.user import is_platform_admin, is_platform_workspace_delegate
from apps.system.schemas.access_context import require_current_tenant_id
from common.core.deps import SessionDep, CurrentUser, Trans
from common.core.pagination import Paginator
from common.core.schemas import PaginationParams

VARIABLE_TYPE_SYSTEM = "system"
VARIABLE_TYPE_PLATFORM = "platform"
VARIABLE_TYPE_CUSTOM = "custom"


def _current_tenant_id(user: CurrentUser | None) -> int:
    if _is_platform_operation(user):
        return DEFAULT_TENANT_ID
    return require_current_tenant_id(user)


def _is_platform_operation(user: CurrentUser) -> bool:
    return is_platform_admin(user) and not is_platform_workspace_delegate(user)


def _visible_variable_condition(user: CurrentUser):
    if _is_platform_operation(user):
        return or_(
            SystemVariable.type == VARIABLE_TYPE_SYSTEM,
            SystemVariable.type == VARIABLE_TYPE_PLATFORM,
        )
    tenant_id = _current_tenant_id(user)
    return or_(
        SystemVariable.type == VARIABLE_TYPE_SYSTEM,
        SystemVariable.type == VARIABLE_TYPE_PLATFORM,
        and_(
            SystemVariable.type != VARIABLE_TYPE_SYSTEM,
            SystemVariable.type != VARIABLE_TYPE_PLATFORM,
            SystemVariable.tenant_id == tenant_id,
        ),
    )


def _custom_variable_condition(user: CurrentUser):
    if _is_platform_operation(user):
        return SystemVariable.type == VARIABLE_TYPE_PLATFORM
    return and_(
        SystemVariable.type != VARIABLE_TYPE_SYSTEM,
        SystemVariable.type != VARIABLE_TYPE_PLATFORM,
        SystemVariable.tenant_id == _current_tenant_id(user),
    )


def _apply_scope(stmt, user: CurrentUser, include_system: bool = True):
    condition = _visible_variable_condition(user)
    if not include_system:
        condition = and_(condition, SystemVariable.type != VARIABLE_TYPE_SYSTEM)
    return stmt.where(condition) if condition is not None else stmt


def _assert_custom_variable_access(record: SystemVariable | None, user: CurrentUser) -> None:
    if record is None:
        raise HTTPException(status_code=404, detail="变量不存在")
    if record.type == VARIABLE_TYPE_SYSTEM:
        raise HTTPException(status_code=403, detail="内置变量不可编辑")
    if _is_platform_operation(user):
        if record.type != VARIABLE_TYPE_PLATFORM:
            raise HTTPException(status_code=404, detail="变量不存在")
        return
    if record.type == VARIABLE_TYPE_PLATFORM:
        raise HTTPException(status_code=403, detail="平台变量不可编辑")
    if record.tenant_id in (None, "") or int(record.tenant_id) != _current_tenant_id(user):
        raise HTTPException(status_code=404, detail="变量不存在")


def _variable_response(data: SystemVariable, user: CurrentUser) -> dict:
    editable = False
    if _is_platform_operation(user):
        editable = data.type == VARIABLE_TYPE_PLATFORM
    else:
        editable = (
            data.type not in (VARIABLE_TYPE_SYSTEM, VARIABLE_TYPE_PLATFORM)
            and data.tenant_id not in (None, "")
            and int(data.tenant_id) == _current_tenant_id(user)
        )
    result = data.model_dump()
    result["can_edit"] = editable
    result["can_delete"] = editable
    return result


def save(session: SessionDep, user: CurrentUser, trans: Trans, variable: SystemVariable):
    if variable.id is None:
        if _is_platform_operation(user):
            variable.type = VARIABLE_TYPE_PLATFORM
            variable.tenant_id = DEFAULT_TENANT_ID
        else:
            variable.type = VARIABLE_TYPE_CUSTOM
            variable.tenant_id = _current_tenant_id(user)
        checkName(session, trans, user, variable)
        variable.create_time = datetime.datetime.now()
        variable.create_by = user.id
        session.add(variable)
        session.commit()
    else:
        record = session.query(SystemVariable).filter(SystemVariable.id == variable.id).first()
        _assert_custom_variable_access(record, user)
        variable.type = record.type
        variable.tenant_id = int(record.tenant_id)
        checkName(session, trans, user, variable)
        update_data = variable.model_dump(exclude_unset=True)
        update_data.pop("id", None)
        update_data.pop("type", None)
        update_data.pop("tenant_id", None)
        update_data.pop("create_time", None)
        update_data.pop("create_by", None)
        for field, value in update_data.items():
            setattr(record, field, value)
        session.add(record)
        session.commit()
    return True


def delete(session: SessionDep, user: CurrentUser, ids: List[int]):
    if not ids:
        return True
    rows = session.query(SystemVariable).filter(SystemVariable.id.in_(ids)).all()
    for row in rows:
        _assert_custom_variable_access(row, user)
        session.delete(row)
    session.commit()
    return True


def list_all(session: SessionDep, trans: Trans, user: CurrentUser, variable: SystemVariable):
    search_name = getattr(variable, "name", None) if variable else None
    if search_name is None:
        stmt = select(SystemVariable).order_by(SystemVariable.type.desc(), SystemVariable.name.asc())
    else:
        stmt = select(SystemVariable).where(SystemVariable.name.ilike(f'%{search_name}%')).order_by(
            SystemVariable.type.desc(), SystemVariable.name.asc())
    records = session.exec(_apply_scope(stmt, user, include_system=search_name is None)).all()

    res = []
    for r in records:
        data = SystemVariable(**r.__dict__)
        if data.type == VARIABLE_TYPE_SYSTEM:
            data.name = trans(data.name)
        res.append(_variable_response(data, user))
    return res


async def list_page(session: SessionDep, trans: Trans, user: CurrentUser, pageNum: int, pageSize: int, variable: SystemVariable):
    pagination = PaginationParams(page=pageNum, size=pageSize)
    paginator = Paginator(session)
    filters = {}
    search_name = getattr(variable, "name", None) if variable else None

    if search_name is None:
        stmt = select(SystemVariable).order_by(SystemVariable.type.desc(), SystemVariable.name.asc())
    else:
        stmt = select(SystemVariable).where(SystemVariable.name.ilike(f'%{search_name}%')).order_by(
            SystemVariable.type.desc(), SystemVariable.name.asc())
    stmt = _apply_scope(stmt, user, include_system=search_name is None)

    variable_page = await paginator.get_paginated_response(
        stmt=stmt,
        pagination=pagination,
        **filters)

    res = []
    for r in variable_page.items:
        data = r if isinstance(r, SystemVariable) else SystemVariable(**r)
        if data.type == VARIABLE_TYPE_SYSTEM:
            data.name = trans(data.name)
        res.append(_variable_response(data, user))

    return {"items": res, "page": variable_page.page, "size": variable_page.size, "total": variable_page.total,
            "total_pages": variable_page.total_pages}


def checkName(session: SessionDep, trans: Trans, user: CurrentUser, variable: SystemVariable):
    tenant_id = (
        int(getattr(variable, "tenant_id"))
        if getattr(variable, "tenant_id", None) not in (None, "")
        else _current_tenant_id(user)
    )
    filters = [
        SystemVariable.name == variable.name,
        _custom_variable_condition(user),
        SystemVariable.tenant_id == tenant_id,
    ]
    if variable.id is None:
        records = session.query(SystemVariable).filter(and_(*filters)).all()
        if records and len(records) > 0:
            raise HTTPException(status_code=500, detail=trans('i18n_variable.name_exist'))
    else:
        filters.append(SystemVariable.id != variable.id)
        records = session.query(SystemVariable).filter(
            and_(*filters)).all()
        if records and len(records) > 0:
            raise HTTPException(status_code=500, detail=trans('i18n_variable.name_exist'))


def checkValue(session: SessionDep, trans: Trans, values: List):
    # values: [{"variableId":1,"variableValues":["a","b"]}]

    pass
