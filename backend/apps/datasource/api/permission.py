from typing import Any

from fastapi import APIRouter, HTTPException

from apps.datasource.crud.permission_rules import (
    delete_rule_dto,
    get_rule_dto,
    list_rule_dtos,
    save_rule_dto,
)
from apps.system.schemas.permission import SqlbotPermission, require_permissions
from common.core.deps import CurrentUser, SessionDep


router = APIRouter(tags=["permission"])


@router.post("/ds_permission/list")
@require_permissions(permission=SqlbotPermission(role=["admin"]))
async def p_list(session: SessionDep, user: CurrentUser):
    return list_rule_dtos(session)


@router.post("/ds_permission/get/{id}")
@require_permissions(permission=SqlbotPermission(role=["admin"]))
async def get(session: SessionDep, id: int):
    rule = get_rule_dto(session, id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Permission rule not found")
    return rule


@router.post("/ds_permission/save")
@require_permissions(permission=SqlbotPermission(role=["admin"]))
async def save_rule(session: SessionDep, user: CurrentUser, ruleDTO: dict[str, Any]):
    return save_rule_dto(session, ruleDTO)


@router.post("/ds_permission/delete/{id}")
@require_permissions(permission=SqlbotPermission(role=["admin"]))
async def delete(session: SessionDep, id: int):
    delete_rule_dto(session, id)
    return True
