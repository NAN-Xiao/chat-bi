from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from apps.datasource.crud.permission_rules import (
    delete_rule_dto,
    get_rule_dto,
    list_rule_dtos,
    save_rule_dto,
)
from apps.datasource.crud.permission import has_datasource_access
from apps.system.schemas.business_access import require_chatbi_business_user
from apps.system.schemas.permission import AppPermission, require_permissions
from apps.datasource.models.datasource import CoreDatasource, CoreTable
from common.core.deps import CurrentUser, SessionDep


router = APIRouter(
    tags=["permission"],
    dependencies=[Depends(require_chatbi_business_user)],
)


def _permission_belongs_to_current_tenant(session: SessionDep, user: CurrentUser, permission: dict[str, Any]) -> bool:
    try:
        datasource_id = int(permission.get("ds_id"))
    except (TypeError, ValueError):
        return False
    return has_datasource_access(session, user, datasource_id)


def _filter_rule_for_current_tenant(session: SessionDep, user: CurrentUser, rule: dict[str, Any]) -> dict[str, Any] | None:
    permissions = [
        permission for permission in rule.get("permissions", [])
        if _permission_belongs_to_current_tenant(session, user, permission)
    ]
    if not permissions:
        return None
    filtered = dict(rule)
    filtered["permissions"] = permissions
    filtered["permission_list"] = [permission["id"] for permission in permissions]
    return filtered


def _validate_permission_rule_scope(session: SessionDep, user: CurrentUser, rule_data: dict[str, Any]) -> None:
    permissions = rule_data.get("permissions") or []
    if not permissions:
        raise HTTPException(status_code=400, detail="Permission rule must contain at least one datasource-scoped permission")

    for permission in permissions:
        try:
            datasource_id = int(permission.get("ds_id"))
            table_id = int(permission.get("table_id"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Permission rule must bind datasource and table")

        datasource = session.get(CoreDatasource, datasource_id)
        if datasource is None or not has_datasource_access(session, user, datasource_id):
            raise HTTPException(status_code=404, detail="Datasource not found")
        table = session.get(CoreTable, table_id)
        if table is None or int(table.ds_id) != datasource_id:
            raise HTTPException(status_code=400, detail="Permission table does not belong to datasource")


@router.post("/ds_permission/list")
@require_permissions(permission=AppPermission(role=["admin"]))
async def p_list(session: SessionDep, user: CurrentUser):
    filtered_rules = []
    for rule in list_rule_dtos(session):
        filtered = _filter_rule_for_current_tenant(session, user, rule)
        if filtered:
            filtered_rules.append(filtered)
    return filtered_rules


@router.post("/ds_permission/get/{id}")
@require_permissions(permission=AppPermission(role=["admin"]))
async def get(session: SessionDep, user: CurrentUser, id: int):
    rule = get_rule_dto(session, id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Permission rule not found")
    filtered = _filter_rule_for_current_tenant(session, user, rule)
    if filtered is None:
        raise HTTPException(status_code=404, detail="Permission rule not found")
    return filtered


@router.post("/ds_permission/save")
@require_permissions(permission=AppPermission(role=["admin"]))
async def save_rule(session: SessionDep, user: CurrentUser, ruleDTO: dict[str, Any]):
    _validate_permission_rule_scope(session, user, ruleDTO)
    return save_rule_dto(session, ruleDTO)


@router.post("/ds_permission/delete/{id}")
@require_permissions(permission=AppPermission(role=["admin"]))
async def delete(session: SessionDep, user: CurrentUser, id: int):
    rule = get_rule_dto(session, id)
    if rule is None or _filter_rule_for_current_tenant(session, user, rule) is None:
        raise HTTPException(status_code=404, detail="Permission rule not found")
    delete_rule_dto(session, id)
    return True
