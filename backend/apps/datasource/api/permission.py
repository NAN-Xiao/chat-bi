from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from apps.datasource.crud.permission_rules import (
    DEFAULT_RULE_TENANT_ID,
    RULE_SCOPE_PLATFORM,
    RULE_SCOPE_TENANT,
    delete_rule_dto,
    get_rule_dto,
    list_rule_dtos,
    normalize_rule_scope,
    save_rule_dto,
)
from apps.datasource.crud.permission import has_datasource_access
from apps.system.schemas.business_access import require_chatbi_business_or_platform_admin
from apps.system.schemas.permission import AppPermission, require_permissions
from apps.system.schemas.access_context import current_tenant_id, is_global_platform_context
from apps.datasource.models.datasource import CoreDatasource, CoreTable
from common.core.deps import CurrentUser, SessionDep


router = APIRouter(
    tags=["permission"],
    dependencies=[Depends(require_chatbi_business_or_platform_admin)],
)


def _permission_belongs_to_current_tenant(session: SessionDep, user: CurrentUser, permission: dict[str, Any]) -> bool:
    try:
        datasource_id = int(permission.get("ds_id"))
    except (TypeError, ValueError):
        return False
    return _datasource_visible_in_current_context(session, user, datasource_id) is not None


def _datasource_visible_in_current_context(
        session: SessionDep,
        user: CurrentUser,
        datasource_id: int,
) -> CoreDatasource | None:
    datasource = session.get(CoreDatasource, datasource_id)
    if datasource is None:
        return None
    if is_global_platform_context(user):
        return datasource
    if not has_datasource_access(session, user, datasource_id):
        return None
    return datasource


def _rule_scope(rule: dict[str, Any]) -> str:
    return normalize_rule_scope(rule.get("scope"))


def _rule_tenant_id(rule: dict[str, Any]) -> int:
    try:
        return int(rule.get("tenant_id") or DEFAULT_RULE_TENANT_ID)
    except (TypeError, ValueError):
        return DEFAULT_RULE_TENANT_ID


def _rule_visible_to_current_context(user: CurrentUser, rule: dict[str, Any]) -> bool:
    scope = _rule_scope(rule)
    if is_global_platform_context(user):
        return scope == RULE_SCOPE_PLATFORM
    if scope == RULE_SCOPE_PLATFORM:
        return True
    tenant_id = current_tenant_id(user)
    return tenant_id is not None and _rule_tenant_id(rule) == int(tenant_id)


def _can_manage_rule(user: CurrentUser, rule: dict[str, Any]) -> bool:
    scope = _rule_scope(rule)
    if scope == RULE_SCOPE_PLATFORM:
        return is_global_platform_context(user)
    if is_global_platform_context(user):
        return False
    tenant_id = current_tenant_id(user)
    return tenant_id is not None and _rule_tenant_id(rule) == int(tenant_id)


def _filter_rule_for_current_context(session: SessionDep, user: CurrentUser, rule: dict[str, Any]) -> dict[str, Any] | None:
    if not _rule_visible_to_current_context(user, rule):
        return None
    permissions = [
        permission for permission in rule.get("permissions", [])
        if _permission_belongs_to_current_tenant(session, user, permission)
    ]
    if not permissions:
        return None
    filtered = dict(rule)
    filtered["permissions"] = permissions
    filtered["permission_list"] = [permission["id"] for permission in permissions]
    filtered["scope"] = _rule_scope(rule)
    filtered["tenant_id"] = _rule_tenant_id(rule)
    filtered["can_edit"] = _can_manage_rule(user, filtered)
    filtered["can_delete"] = filtered["can_edit"]
    filtered["readonly"] = not filtered["can_edit"]
    return filtered


def _validate_permission_rule_scope(session: SessionDep, user: CurrentUser, rule_data: dict[str, Any]) -> None:
    permissions = rule_data.get("permissions") or []
    if not permissions:
        raise HTTPException(status_code=400, detail="Permission rule must contain at least one datasource-scoped permission")

    for permission in permissions:
        try:
            table_id = int(permission.get("table_id"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Permission rule must bind table")

        table = session.get(CoreTable, table_id)
        if table is None:
            raise HTTPException(status_code=400, detail="Permission table does not belong to datasource")

        try:
            datasource_id = int(permission.get("ds_id"))
        except (TypeError, ValueError):
            datasource_id = int(table.ds_id)
            permission["ds_id"] = datasource_id

        datasource = _datasource_visible_in_current_context(session, user, datasource_id)
        if datasource is None:
            raise HTTPException(status_code=404, detail="Datasource not found")
        if table is None or int(table.ds_id) != datasource_id:
            raise HTTPException(status_code=400, detail="Permission table does not belong to datasource")


@router.post("/ds_permission/list")
@require_permissions(permission=AppPermission(role=["admin"]))
async def p_list(session: SessionDep, user: CurrentUser):
    filtered_rules = []
    for rule in list_rule_dtos(session):
        filtered = _filter_rule_for_current_context(session, user, rule)
        if filtered:
            filtered_rules.append(filtered)
    return filtered_rules


@router.post("/ds_permission/get/{id}")
@require_permissions(permission=AppPermission(role=["admin"]))
async def get(session: SessionDep, user: CurrentUser, id: int):
    rule = get_rule_dto(session, id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Permission rule not found")
    filtered = _filter_rule_for_current_context(session, user, rule)
    if filtered is None:
        raise HTTPException(status_code=404, detail="Permission rule not found")
    return filtered


@router.post("/ds_permission/save")
@require_permissions(permission=AppPermission(role=["admin"]))
async def save_rule(session: SessionDep, user: CurrentUser, ruleDTO: dict[str, Any]):
    rule_payload = dict(ruleDTO)
    rule_id = rule_payload.get("id")
    if rule_id:
        existing_rule = get_rule_dto(session, int(rule_id))
        if existing_rule is None or _filter_rule_for_current_context(session, user, existing_rule) is None:
            raise HTTPException(status_code=404, detail="Permission rule not found")
        if not _can_manage_rule(user, existing_rule):
            raise HTTPException(status_code=403, detail="Permission rule is read-only in this workspace")
        rule_payload["tenant_id"] = _rule_tenant_id(existing_rule)
        rule_payload["scope"] = _rule_scope(existing_rule)
    elif is_global_platform_context(user):
        rule_payload["tenant_id"] = DEFAULT_RULE_TENANT_ID
        rule_payload["scope"] = RULE_SCOPE_PLATFORM
    else:
        tenant_id = current_tenant_id(user)
        if tenant_id is None:
            raise HTTPException(status_code=403, detail="Workspace context is required")
        rule_payload["tenant_id"] = int(tenant_id)
        rule_payload["scope"] = RULE_SCOPE_TENANT

    _validate_permission_rule_scope(session, user, rule_payload)
    saved = save_rule_dto(session, rule_payload)
    return _filter_rule_for_current_context(session, user, saved)


@router.post("/ds_permission/delete/{id}")
@require_permissions(permission=AppPermission(role=["admin"]))
async def delete(session: SessionDep, user: CurrentUser, id: int):
    rule = get_rule_dto(session, id)
    if rule is None or _filter_rule_for_current_context(session, user, rule) is None:
        raise HTTPException(status_code=404, detail="Permission rule not found")
    if not _can_manage_rule(user, rule):
        raise HTTPException(status_code=403, detail="Permission rule is read-only in this workspace")
    delete_rule_dto(session, id)
    return True
