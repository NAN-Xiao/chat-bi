from typing import Any

from fastapi import APIRouter, HTTPException

from apps.datasource.crud.permission_rules import (
    delete_rule_dto,
    get_rule_dto,
    list_rule_dtos,
    save_rule_dto,
)
from apps.system.schemas.permission import AppPermission, require_permissions
from apps.datasource.models.datasource import CoreDatasource, CoreTable
from common.core.deps import CurrentUser, SessionDep


router = APIRouter(tags=["permission"])


def _validate_permission_rule_scope(session: SessionDep, rule_data: dict[str, Any]) -> None:
    permissions = rule_data.get("permissions") or []
    if not permissions:
        raise HTTPException(status_code=400, detail="Permission rule must contain at least one datasource-scoped permission")

    for permission in permissions:
        try:
            datasource_id = int(permission.get("ds_id"))
            table_id = int(permission.get("table_id"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Permission rule must bind datasource and table")

        if session.get(CoreDatasource, datasource_id) is None:
            raise HTTPException(status_code=404, detail="Datasource not found")
        table = session.get(CoreTable, table_id)
        if table is None or int(table.ds_id) != datasource_id:
            raise HTTPException(status_code=400, detail="Permission table does not belong to datasource")


@router.post("/ds_permission/list")
@require_permissions(permission=AppPermission(role=["admin"]))
async def p_list(session: SessionDep, user: CurrentUser):
    return list_rule_dtos(session)


@router.post("/ds_permission/get/{id}")
@require_permissions(permission=AppPermission(role=["admin"]))
async def get(session: SessionDep, id: int):
    rule = get_rule_dto(session, id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Permission rule not found")
    return rule


@router.post("/ds_permission/save")
@require_permissions(permission=AppPermission(role=["admin"]))
async def save_rule(session: SessionDep, user: CurrentUser, ruleDTO: dict[str, Any]):
    _validate_permission_rule_scope(session, ruleDTO)
    return save_rule_dto(session, ruleDTO)


@router.post("/ds_permission/delete/{id}")
@require_permissions(permission=AppPermission(role=["admin"]))
async def delete(session: SessionDep, id: int):
    delete_rule_dto(session, id)
    return True
