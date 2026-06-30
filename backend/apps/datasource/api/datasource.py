"""
脚本说明：这个脚本放数据源的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
import asyncio
import hashlib
import io
import os
import traceback
import uuid
import re
from datetime import datetime
from io import StringIO
from typing import Any, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from psycopg2 import sql
from sqlalchemy import and_, inspect
from sqlmodel import select

from apps.db.db import get_schema
from apps.db.engine import get_engine_conn
from apps.datasource.crud.permission import (
    can_access_table,
    current_tenant_id,
    get_column_permission_fields,
    get_user_permission_rules,
    get_user_scoped_table_ids,
    is_normal_user,
    PROJECT_ROLE_EDITOR,
    PROJECT_ROLE_VIEWER,
    get_datasource_role,
    list_datasource_user_counts,
    list_project_assignable_user_ids,
    list_datasource_users,
    normalize_project_role,
    project_role_rank,
    update_datasource_users,
)
from apps.datasource.crud.binding import bind_datasource_to_tenant
from apps.datasource.crud.binding import datasource_bound_to_tenant
from apps.datasource.crud.binding import list_bound_tenant_ids_for_datasource
from apps.swagger.i18n import PLACEHOLDER_PREFIX
from apps.system.crud.schema_metadata import (
    SchemaFieldKey,
    field_comment_map,
    save_field_comment,
    save_table_comment,
    table_comment_map,
)
from apps.system.crud.schema_change_request import (
    SCHEMA_CHANGE_TYPE_ALTER_TABLE,
    SCHEMA_CHANGE_TYPE_CREATE_TABLE,
    create_schema_change_request,
    list_schema_change_requests,
    normalize_change_type,
    parse_schema_change_payload,
)
from apps.system.crud.tenant import DEFAULT_TENANT_ID
from apps.system.crud.tenant import TENANT_ADMIN_ROLES, normalize_tenant_role
from apps.system.crud.user import is_platform_admin, is_platform_workspace_delegate, is_system_admin
from apps.system.schemas.access_context import can_manage_workspace_scope, require_current_tenant_id
from apps.system.models.tenant import TenantModel
from apps.system.schemas.business_access import (
    ensure_chatbi_business_user,
    require_chatbi_business_or_platform_admin,
)
from apps.system.schemas.permission import AppPermission, require_permissions
from apps.system.models.user import UserModel
from common.audit.models.log_model import OperationType, OperationModules
from common.audit.schemas.logger_decorator import LogConfig, system_log
from common.core.config import settings
from common.core.deps import SessionDep, CurrentUser, Trans
from common.core.task_registry import register_builtin_tasks
from common.core.task_queue import enqueue_task
from common.utils.file_utils import AppFileUtils
from common.utils.embedding_threads import run_save_ds_embeddings, run_save_table_embeddings
from common.utils.utils import AppLogUtil
from ..utils.utils import decrypt_datasource_configuration_for_output
from ..crud.datasource import get_datasource_list, check_status, create_ds, update_ds, delete_ds, getTables, getFields, \
    update_table_and_fields, getTablesByDs, chooseTables, preview, updateTable, updateField, get_ds, fieldEnum, \
    check_status_by_id
from ..crud.field import get_fields_by_table_id
from ..crud.table import get_tables_by_ds_id
from ..models.datasource import CoreDatasource, CreateDatasource, TableObj, CoreTable, CoreField, FieldObj, \
    TableSchemaResponse, ColumnSchemaResponse, PreviewResponse, ImportRequest
from ..utils.excel import parse_excel_preview, USER_TYPE_TO_PANDAS

router = APIRouter(
    tags=["Datasource"],
    prefix="/datasource",
    dependencies=[Depends(require_chatbi_business_or_platform_admin)],
)
path = settings.EXCEL_PATH


def _tenant_excel_path(current_user: CurrentUser) -> str:
    """
    是什么：_tenant_excel_path 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    tenant_id = (
        DEFAULT_TENANT_ID
        if is_platform_admin(current_user) and not is_platform_workspace_delegate(current_user)
        else require_current_tenant_id(current_user)
    )
    tenant_path = os.path.join(path, f"tenant_{tenant_id}")
    os.makedirs(tenant_path, exist_ok=True)
    return tenant_path


def _can_manage_tenant_projects(user: CurrentUser) -> bool:
    """
    是什么：_can_manage_tenant_projects 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    tenant_role = normalize_tenant_role(getattr(user, "tenant_role", None))
    return (
        is_platform_workspace_delegate(user)
        or (not is_platform_admin(user) and (is_system_admin(user) or tenant_role in TENANT_ADMIN_ROLES))
    )


def _can_manage_datasource_metadata(user: CurrentUser) -> bool:
    """
    是什么：_can_manage_datasource_metadata 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return (
        is_platform_admin(user) and not is_platform_workspace_delegate(user)
    ) or is_platform_workspace_delegate(user)


def _require_platform_project_admin(user: CurrentUser) -> None:
    """
    是什么：_require_platform_project_admin 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if not is_platform_admin(user):
        raise HTTPException(status_code=403, detail="Only SaaS admin can manage projects")


def _require_schema_metadata_admin(user: CurrentUser) -> None:
    """
    是什么：_require_schema_metadata_admin 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if is_platform_admin(user) or can_manage_workspace_scope(user):
        return
    raise HTTPException(status_code=403, detail="Only workspace admin can view datasource schema metadata")


class DatasourceListItem(BaseModel):
    """
    类说明：DatasourceListItem 把数据源相关的数据和行为放在一起，便于其他代码直接复用。
    """
    id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    type_name: Optional[str] = None
    configuration: Optional[str] = None
    create_time: Optional[datetime] = None
    create_by: Optional[int] = None
    status: Optional[str] = None
    num: Optional[str] = None
    table_relation: Optional[List[Any]] = None
    embedding: Optional[str] = None
    recommended_config: Optional[int] = None
    project_role: Optional[str] = None
    tenant_id: Optional[int] = None
    tenant_name: Optional[str] = None
    tenant_ids: list[int] = Field(default_factory=list)
    tenant_names: list[str] = Field(default_factory=list)
    authorized_user_count: int = 0
    can_create_dashboard: bool = False
    can_manage_dashboard: bool = False
    can_manage_project: bool = False
    can_manage_metadata: bool = False
    can_bind_workspace: bool = False


class DatasourceDetailItem(BaseModel):
    """
    类说明：DatasourceDetailItem 把数据源相关的数据和行为放在一起，便于其他代码直接复用。
    """
    id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    type_name: Optional[str] = None
    configuration: Optional[str] = None
    create_time: Optional[datetime] = None
    create_by: Optional[int] = None
    status: Optional[str] = None
    num: Optional[str] = None
    table_relation: Optional[Any] = None
    embedding: Optional[str] = None
    recommended_config: Optional[int] = None
    tenant_id: Optional[int] = None
    tenant_name: Optional[str] = None
    tenant_ids: list[int] = Field(default_factory=list)
    tenant_names: list[str] = Field(default_factory=list)
    can_manage_metadata: bool = False


class DatasourceSchemaFieldItem(BaseModel):
    """
    类说明：DatasourceSchemaFieldItem 把数据源相关的数据和行为放在一起，便于其他代码直接复用。
    """
    id: int
    field_name: str | None = None
    field_type: str | None = None
    field_comment: str | None = None
    custom_comment: str | None = None
    checked: bool = True
    field_index: int | None = None


class DatasourceSchemaTableItem(BaseModel):
    """
    类说明：DatasourceSchemaTableItem 把数据源相关的数据和行为放在一起，便于其他代码直接复用。
    """
    id: int
    table_name: str | None = None
    table_comment: str | None = None
    custom_comment: str | None = None
    checked: bool = True
    fields: list[DatasourceSchemaFieldItem] = Field(default_factory=list)


class DatasourceSchemaMetadata(BaseModel):
    """
    类说明：DatasourceSchemaMetadata 把数据源相关的数据和行为放在一起，便于其他代码直接复用。
    """
    id: int
    name: str | None = None
    description: str | None = None
    type: str | None = None
    type_name: str | None = None
    num: str | None = None
    tables: list[DatasourceSchemaTableItem] = Field(default_factory=list)


class DatasourceSchemaChangeField(BaseModel):
    """
    类说明：DatasourceSchemaChangeField 把数据源相关的数据和行为放在一起，便于其他代码直接复用。
    """
    field_name: str
    field_type: str
    field_comment: str | None = None
    required: bool = False


class DatasourceSchemaChangeCreate(BaseModel):
    """
    类说明：DatasourceSchemaChangeCreate 把数据源相关的数据和行为放在一起，便于其他代码直接复用。
    """
    change_type: str
    table_name: str
    table_comment: str | None = None
    fields: list[DatasourceSchemaChangeField] = Field(default_factory=list)
    request_comment: str | None = None
    source_table_name: str | None = None


class DatasourceSchemaChangeItem(BaseModel):
    """
    类说明：DatasourceSchemaChangeItem 把数据源相关的数据和行为放在一起，便于其他代码直接复用。
    """
    id: int
    tenant_id: int
    datasource_id: int | None = None
    change_type: str
    status: str
    table_name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    requested_by_user_id: int
    request_comment: str | None = None
    execution_comment: str | None = None
    create_time: int = 0
    update_time: int = 0
    execute_time: int | None = None


class DatasourceBindingUpdate(BaseModel):
    """
    类说明：DatasourceBindingUpdate 把数据源相关的数据和行为放在一起，便于其他代码直接复用。
    """
    tenant_id: Optional[int] = None


class DatasourceBindingItem(BaseModel):
    """
    类说明：DatasourceBindingItem 把数据源相关的数据和行为放在一起，便于其他代码直接复用。
    """
    datasource_id: int
    tenant_id: Optional[int] = None
    tenant_name: Optional[str] = None


def _tenant_name_map(session: SessionDep, tenant_ids) -> dict[int, str]:
    """
    是什么：_tenant_name_map 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    ids = {int(tenant_id) for tenant_id in tenant_ids if tenant_id not in (None, "")}
    if not ids:
        return {}
    try:
        if not inspect(session.connection()).has_table(TenantModel.__tablename__):
            return {}
    except Exception:
        return {}
    rows = session.exec(
        select(TenantModel.id, TenantModel.name)
        .where(TenantModel.id.in_(ids))
    ).all()
    return {int(row[0]): row[1] for row in rows}


def _datasource_binding_item(session: SessionDep, datasource: CoreDatasource) -> DatasourceBindingItem:
    """
    是什么：_datasource_binding_item 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    tenant_ids = list_bound_tenant_ids_for_datasource(session, int(datasource.id))
    tenant_id = tenant_ids[0] if tenant_ids else None
    tenant_name = None
    if tenant_id and tenant_id != DEFAULT_TENANT_ID:
        tenant = session.get(TenantModel, tenant_id)
        tenant_name = tenant.name if tenant else None
    return DatasourceBindingItem(
        datasource_id=int(datasource.id),
        tenant_id=tenant_id if tenant_id != DEFAULT_TENANT_ID else None,
        tenant_name=tenant_name,
    )


def _coerce_tenant_id(value) -> int | None:
    """
    是什么：_coerce_tenant_id 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _metadata_tenant_id(
        session: SessionDep,
        datasource: CoreDatasource,
        user: CurrentUser | None = None,
) -> int | None:
    """
    是什么：_metadata_tenant_id 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    user_tenant_id = current_tenant_id(user)
    if user_tenant_id is not None and datasource_bound_to_tenant(session, int(datasource.id), user_tenant_id):
        return int(user_tenant_id)
    return _coerce_tenant_id(getattr(datasource, "tenant_id", None))


def _current_user_id(user: CurrentUser | None) -> int | None:
    """
    是什么：_current_user_id 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return _coerce_tenant_id(getattr(user, "id", None))


def _apply_schema_comments(
        session: SessionDep,
        datasource: CoreDatasource,
        tables: list[CoreTable],
        fields_by_table: dict[int, list[CoreField]] | None = None,
        user: CurrentUser | None = None,
) -> None:
    """
    是什么：_apply_schema_comments 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    tenant_id = _metadata_tenant_id(session, datasource, user)
    table_comments = table_comment_map(session, tenant_id, [table.table_name for table in tables])
    for table in tables:
        if table.table_name in table_comments:
            table.custom_comment = table_comments[table.table_name] or ""
        else:
            table.custom_comment = table.custom_comment or ""

    if fields_by_table is None:
        return
    keys = [
        SchemaFieldKey(table.table_name, field.field_name)
        for table in tables
        for field in fields_by_table.get(int(table.id), [])
    ]
    field_comments = field_comment_map(session, tenant_id, keys)
    table_name_by_id = {int(table.id): table.table_name for table in tables}
    for table_id, fields in fields_by_table.items():
        table_name = table_name_by_id.get(int(table_id))
        if not table_name:
            continue
        for field in fields:
            key = (table_name, field.field_name)
            if key in field_comments:
                field.custom_comment = field_comments[key] or ""
            else:
                field.custom_comment = field.custom_comment or ""


def _schema_change_item(row) -> DatasourceSchemaChangeItem:
    """
    是什么：_schema_change_item 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return DatasourceSchemaChangeItem(
        id=int(row.id),
        tenant_id=int(row.tenant_id),
        datasource_id=int(row.datasource_id) if row.datasource_id is not None else None,
        change_type=row.change_type,
        status=row.status,
        table_name=row.table_name,
        payload=parse_schema_change_payload(row),
        requested_by_user_id=int(row.requested_by_user_id),
        request_comment=row.request_comment,
        execution_comment=row.execution_comment,
        create_time=int(row.create_time or 0),
        update_time=int(row.update_time or 0),
        execute_time=row.execute_time,
    )


def _datasource_list_items(
        session: SessionDep,
        user: CurrentUser,
        datasources: list[CoreDatasource],
) -> list[dict[str, Any]]:
    """
    是什么：_datasource_list_items 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    binding_map = {
        int(datasource.id): list_bound_tenant_ids_for_datasource(session, int(datasource.id))
        for datasource in datasources
    }
    all_tenant_ids = [tenant_id for tenant_ids in binding_map.values() for tenant_id in tenant_ids]
    tenant_names = _tenant_name_map(session, all_tenant_ids)
    authorized_user_counts = list_datasource_user_counts(
        session,
        [datasource.id for datasource in datasources],
        user,
    )
    result = []
    for datasource in datasources:
        role = get_datasource_role(session, user, datasource.id)
        datasource_tenant_ids = [
            int(tenant_id)
            for tenant_id in binding_map.get(int(datasource.id), [])
            if int(tenant_id) != DEFAULT_TENANT_ID
        ]
        bound_tenant_id = datasource_tenant_ids[0] if datasource_tenant_ids else None
        can_platform_manage_project = is_platform_admin(user) and not is_platform_workspace_delegate(user)
        can_manage_tenant_projects = _can_manage_tenant_projects(user)
        can_manage_metadata = _can_manage_datasource_metadata(user)
        item = {
            "id": datasource.id,
            "name": datasource.name,
            "description": datasource.description,
            "type": datasource.type,
            "type_name": datasource.type_name,
            "configuration": (
                decrypt_datasource_configuration_for_output(datasource.configuration)
                if can_platform_manage_project
                else None
            ),
            "create_time": datasource.create_time,
            "create_by": datasource.create_by,
            "status": datasource.status,
            "num": datasource.num,
            "table_relation": datasource.table_relation if isinstance(datasource.table_relation, list) else [],
            "embedding": datasource.embedding,
            "recommended_config": datasource.recommended_config,
            "project_role": role,
            "tenant_id": bound_tenant_id,
            "tenant_name": tenant_names.get(bound_tenant_id) if bound_tenant_id else None,
            "tenant_ids": datasource_tenant_ids,
            "tenant_names": [tenant_names.get(tenant_id) for tenant_id in datasource_tenant_ids if tenant_names.get(tenant_id)],
            "authorized_user_count": authorized_user_counts.get(int(datasource.id), 0),
            "can_create_dashboard": project_role_rank(role) >= project_role_rank(PROJECT_ROLE_VIEWER),
            "can_manage_dashboard": project_role_rank(role) >= project_role_rank(PROJECT_ROLE_EDITOR),
            "can_manage_project": can_manage_tenant_projects,
            "can_manage_metadata": can_manage_metadata,
            "can_bind_workspace": can_platform_manage_project,
        }
        result.append(item)
    return result


@router.get("/list", response_model=List[DatasourceListItem], summary=f"{PLACEHOLDER_PREFIX}ds_list",
            description=f"{PLACEHOLDER_PREFIX}ds_list_description")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def datasource_list(session: SessionDep, user: CurrentUser):
    """
    是什么：datasource_list 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    _require_platform_project_admin(user)
    datasources = get_datasource_list(session=session, user=user)
    return _datasource_list_items(session, user, datasources)


@router.get("/accessible/list", response_model=List[DatasourceListItem], include_in_schema=False)
async def accessible_datasource_list(session: SessionDep, user: CurrentUser):
    """
    是什么：accessible_datasource_list 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    ensure_chatbi_business_user(user)
    datasources = get_datasource_list(session=session, user=user)
    return _datasource_list_items(session, user, datasources)


class DatasourceUserMember(BaseModel):
    """
    类说明：DatasourceUserMember 把数据源相关的数据和行为放在一起，便于其他代码直接复用。
    """
    id: int
    role: Optional[str] = "viewer"


class DatasourceUserUpdate(BaseModel):
    """
    类说明：DatasourceUserUpdate 把数据源相关的数据和行为放在一起，便于其他代码直接复用。
    """
    user_ids: List[int] = Field(default_factory=list)
    users: List[DatasourceUserMember] = Field(default_factory=list)


@router.get("/{id}/users", include_in_schema=False)
@require_permissions(permission=AppPermission(role=['admin']))
async def datasource_users(
        session: SessionDep,
        user: CurrentUser,
        id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id"),
):
    """
    是什么：datasource_users 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    datasource = get_ds(session, id, user)
    if datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    project_users = list_datasource_users(session, id, user)
    user_ids = [item["user_id"] for item in project_users]
    role_map = {item["user_id"]: item["role"] for item in project_users}
    users = []
    if user_ids:
        rows = session.exec(
            select(UserModel.id, UserModel.name, UserModel.account, UserModel.email, UserModel.status)
            .where(UserModel.id.in_(user_ids))
            .order_by(UserModel.account, UserModel.create_time)
        ).all()
        users = [
            {
                "id": row.id,
                "name": row.name,
                "account": row.account,
                "email": row.email,
                "status": row.status,
                "role": role_map.get(int(row.id), "viewer"),
            }
            for row in rows
        ]
    return {"user_ids": user_ids, "users": users}


@router.put("/{id}/users", include_in_schema=False)
@require_permissions(permission=AppPermission(role=['admin']))
async def update_datasource_user_api(
        session: SessionDep,
        user: CurrentUser,
        data: DatasourceUserUpdate,
        id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id")
):
    """
    是什么：update_datasource_user_api 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    datasource = get_ds(session, id, user)
    if datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    requested_user_ids = data.user_ids or [item.id for item in data.users]
    requested_role_map = {int(item.id): normalize_project_role(item.role) for item in data.users}
    valid_user_ids = sorted(list_project_assignable_user_ids(session, requested_user_ids, user))
    updated_users = update_datasource_users(
        session,
        user,
        datasource,
        valid_user_ids,
        {user_id: requested_role_map.get(user_id, "viewer") for user_id in valid_user_ids},
    )
    return {
        "user_ids": [item["user_id"] for item in updated_users],
        "users": [
            {
                "id": item["user_id"],
                "role": item["role"],
            }
            for item in updated_users
        ],
    }


@router.post("/get/{id}", response_model=Optional[DatasourceDetailItem], summary=f"{PLACEHOLDER_PREFIX}ds_get")
@require_permissions(permission=AppPermission(type='ds', keyExpression="id"))
async def get_datasource(
        session: SessionDep,
        user: CurrentUser,
        id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id"),
):
    """
    是什么：get_datasource 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    datasource = get_ds(session, id, user)
    if datasource is None:
        return None
    data = datasource.model_dump()
    if is_platform_admin(user) and not is_platform_workspace_delegate(user):
        data["configuration"] = decrypt_datasource_configuration_for_output(data.get("configuration"))
    else:
        data["configuration"] = None
    tenant_ids = list_bound_tenant_ids_for_datasource(session, int(datasource.id))
    tenant_names = _tenant_name_map(session, tenant_ids)
    data["tenant_ids"] = tenant_ids
    data["tenant_names"] = [tenant_names.get(tenant_id) for tenant_id in tenant_ids if tenant_names.get(tenant_id)]
    data["tenant_id"] = tenant_ids[0] if tenant_ids else None
    data["tenant_name"] = tenant_names.get(tenant_ids[0]) if tenant_ids else None
    data["can_manage_metadata"] = _can_manage_datasource_metadata(user)
    return data


@router.get("/schema-metadata/{id}", response_model=DatasourceSchemaMetadata, include_in_schema=False)
@require_permissions(permission=AppPermission(role=['admin'], type='ds', keyExpression="id"))
async def schema_metadata(
        session: SessionDep,
        user: CurrentUser,
        id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id"),
):
    """
    是什么：schema_metadata 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    _require_schema_metadata_admin(user)
    datasource = get_ds(session, id, user)
    if datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    tables = get_tables_by_ds_id(session, id)
    table_ids = [int(table.id) for table in tables if table.id is not None]
    fields_by_table: dict[int, list[CoreField]] = {table_id: [] for table_id in table_ids}
    if table_ids:
        rows = session.exec(
            select(CoreField)
            .where(CoreField.table_id.in_(table_ids))
            .order_by(CoreField.table_id, CoreField.field_index, CoreField.id)
        ).all()
        for field in rows:
            fields_by_table.setdefault(int(field.table_id), []).append(field)
    _apply_schema_comments(session, datasource, tables, fields_by_table, user)

    return DatasourceSchemaMetadata(
        id=int(datasource.id),
        name=datasource.name,
        description=datasource.description,
        type=datasource.type,
        type_name=datasource.type_name,
        num=datasource.num,
        tables=[
            DatasourceSchemaTableItem(
                id=int(table.id),
                table_name=table.table_name,
                table_comment=table.table_comment,
                custom_comment=table.custom_comment,
                checked=bool(table.checked),
                fields=[
                    DatasourceSchemaFieldItem(
                        id=int(field.id),
                        field_name=field.field_name,
                        field_type=field.field_type,
                        field_comment=field.field_comment,
                        custom_comment=field.custom_comment,
                        checked=bool(field.checked),
                        field_index=field.field_index,
                    )
                    for field in fields_by_table.get(int(table.id), [])
                ],
            )
            for table in tables
        ],
    )


@router.get("/schema-change/{id}", response_model=list[DatasourceSchemaChangeItem], include_in_schema=False)
@require_permissions(permission=AppPermission(role=['admin'], type='ds', keyExpression="id"))
async def schema_change_list(
        session: SessionDep,
        user: CurrentUser,
        id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id"),
        limit: int = 20,
):
    """
    是什么：schema_change_list 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    _require_schema_metadata_admin(user)
    datasource = get_ds(session, id, user)
    if datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    tenant_id = _metadata_tenant_id(session, datasource, user)
    if tenant_id is None:
        return []
    return [
        _schema_change_item(row)
        for row in list_schema_change_requests(
            session,
            tenant_id=tenant_id,
            datasource_id=int(datasource.id),
            limit=limit,
        )
    ]


@router.post("/schema-change/{id}", response_model=DatasourceSchemaChangeItem, include_in_schema=False)
@require_permissions(permission=AppPermission(role=['admin'], type='ds', keyExpression="id"))
async def submit_schema_change(
        session: SessionDep,
        user: CurrentUser,
        data: DatasourceSchemaChangeCreate,
        id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id"),
):
    """
    是什么：submit_schema_change 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    _require_schema_metadata_admin(user)
    datasource = get_ds(session, id, user)
    if datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    tenant_id = _metadata_tenant_id(session, datasource, user)
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="当前工作空间不可提交结构变更")
    try:
        change_type = normalize_change_type(data.change_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if change_type == SCHEMA_CHANGE_TYPE_CREATE_TABLE:
        existing = session.exec(
            select(CoreTable.id).where(
                CoreTable.ds_id == int(datasource.id),
                CoreTable.table_name == data.table_name,
            )
        ).first()
        if existing is not None:
            raise HTTPException(status_code=400, detail="数据表已存在")
    elif change_type == SCHEMA_CHANGE_TYPE_ALTER_TABLE:
        existing = session.exec(
            select(CoreTable.id).where(
                CoreTable.ds_id == int(datasource.id),
                CoreTable.table_name == (data.source_table_name or data.table_name),
            )
        ).first()
        if existing is None:
            raise HTTPException(status_code=400, detail="要修改的数据表不存在")
    try:
        row = create_schema_change_request(
            session,
            tenant_id=tenant_id,
            datasource_id=int(datasource.id),
            requested_by_user_id=int(user.id),
            change_type=change_type,
            table_name=data.table_name,
            table_comment=data.table_comment,
            fields=[field.model_dump() for field in data.fields],
            request_comment=data.request_comment,
            source_table_name=data.source_table_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _schema_change_item(row)


@router.get("/{id}/binding", response_model=DatasourceBindingItem, include_in_schema=False)
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def datasource_binding(
        session: SessionDep,
        user: CurrentUser,
        id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id"),
):
    """
    是什么：datasource_binding 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    _require_platform_project_admin(user)
    datasource = get_ds(session, id, user)
    if datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return _datasource_binding_item(session, datasource)


@router.put("/{id}/binding", response_model=DatasourceBindingItem, include_in_schema=False)
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def update_datasource_binding(
        session: SessionDep,
        user: CurrentUser,
        data: DatasourceBindingUpdate,
        id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id"),
):
    """
    是什么：update_datasource_binding 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    _require_platform_project_admin(user)
    datasource = get_ds(session, id, user)
    if datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    datasource = bind_datasource_to_tenant(session, user, datasource, data.tenant_id)
    return _datasource_binding_item(session, datasource)


@router.post("/check", response_model=bool, summary=f"{PLACEHOLDER_PREFIX}ds_check")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def check(session: SessionDep, trans: Trans, ds: CoreDatasource):
    """
    是什么：check 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责数据源相关的一件事。
        谁调用：外层函数 check 跑到对应步骤时会调用它。
        做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return check_status(session, trans, ds, True)

    return await asyncio.to_thread(inner)


@router.get("/check/{ds_id}", response_model=bool, summary=f"{PLACEHOLDER_PREFIX}ds_check")
@require_permissions(permission=AppPermission(type='ds', keyExpression="ds_id"))
async def check_by_id(session: SessionDep, trans: Trans,
                      ds_id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id")):
    """
    是什么：check_by_id 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责数据源相关的一件事。
        谁调用：外层函数 check_by_id 跑到对应步骤时会调用它。
        做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return check_status_by_id(session, trans, ds_id, True)

    return await asyncio.to_thread(inner)


@router.post("/add", response_model=CoreDatasource, summary=f"{PLACEHOLDER_PREFIX}ds_add")
@system_log(LogConfig(operation_type=OperationType.CREATE, module=OperationModules.DATASOURCE, result_id_expr="id"))
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def add(session: SessionDep, trans: Trans, user: CurrentUser, ds: CreateDatasource):
    """
    是什么：add 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：创建或保存数据源需要的东西，让后续流程能继续往下走。
    """
    return await create_ds(session, trans, user, ds)


@router.post("/chooseTables/{id}", response_model=None, summary=f"{PLACEHOLDER_PREFIX}ds_choose_tables")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def choose_tables(session: SessionDep, trans: Trans, user: CurrentUser, tables: List[CoreTable],
                        id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id")):
    """
    是什么：choose_tables 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    datasource = get_ds(session, id, user)
    if datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责数据源相关的一件事。
        谁调用：外层函数 choose_tables 跑到对应步骤时会调用它。
        做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        chooseTables(session, trans, id, tables)

    await asyncio.to_thread(inner)


@router.post("/update", response_model=CoreDatasource, summary=f"{PLACEHOLDER_PREFIX}ds_update")
@require_permissions(permission=AppPermission(role=['platform_admin']))
@system_log(
    LogConfig(operation_type=OperationType.UPDATE, module=OperationModules.DATASOURCE, resource_id_expr="ds.id"))
async def update(session: SessionDep, trans: Trans, user: CurrentUser, ds: CoreDatasource):
    """
    是什么：update 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责数据源相关的一件事。
        谁调用：外层函数 update 跑到对应步骤时会调用它。
        做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return update_ds(session, trans, user, ds)

    return await asyncio.to_thread(inner)


@router.post("/delete/{id}/{name}", response_model=None, summary=f"{PLACEHOLDER_PREFIX}ds_delete")
@require_permissions(permission=AppPermission(role=['platform_admin']))
@system_log(LogConfig(operation_type=OperationType.DELETE, module=OperationModules.DATASOURCE, resource_id_expr="id",
                      ))
async def delete(session: SessionDep, user: CurrentUser, id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id"), name: str = None):
    """
    是什么：delete 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源不再需要的数据、缓存或临时内容清理掉。
    """
    return await delete_ds(session, id, user)


@router.post("/getTables/{id}", response_model=List[TableSchemaResponse], summary=f"{PLACEHOLDER_PREFIX}ds_get_tables")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def get_tables(session: SessionDep, user: CurrentUser, id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id")):
    """
    是什么：get_tables 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if get_ds(session, id, user) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return getTables(session, id)


@router.post("/getTablesByConf", response_model=List[TableSchemaResponse], summary=f"{PLACEHOLDER_PREFIX}ds_get_tables")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def get_tables_by_conf(session: SessionDep, trans: Trans, ds: CoreDatasource):
    """
    是什么：get_tables_by_conf 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    try:
        def inner():
            """
            是什么：inner 是一个可以复用的小步骤，负责数据源相关的一件事。
            谁调用：外层函数 get_tables_by_conf 跑到对应步骤时会调用它。
            做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
            """
            return getTablesByDs(session, ds)

        return await asyncio.to_thread(inner)
    except Exception as e:
        # 检查数据源状态
        def inner():
            """
            是什么：inner 是一个可以复用的小步骤，负责数据源相关的一件事。
            谁调用：外层函数 get_tables_by_conf 跑到对应步骤时会调用它。
            做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
            """
            return check_status(session, trans, ds, True)

        status = await asyncio.to_thread(inner)
        if status:
            AppLogUtil.error(f"get table failed: {e}")
            raise HTTPException(status_code=500, detail=f'Get table Failed: {e.args}')


@router.post("/getSchemaByConf", response_model=List[str], summary=f"{PLACEHOLDER_PREFIX}ds_get_schema")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def get_schema_by_conf(session: SessionDep, trans: Trans, ds: CoreDatasource):
    """
    是什么：get_schema_by_conf 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    try:
        def inner():
            """
            是什么：inner 是一个可以复用的小步骤，负责数据源相关的一件事。
            谁调用：外层函数 get_schema_by_conf 跑到对应步骤时会调用它。
            做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
            """
            return get_schema(ds)

        return await asyncio.to_thread(inner)
    except Exception as e:
        # 检查数据源状态
        def inner():
            """
            是什么：inner 是一个可以复用的小步骤，负责数据源相关的一件事。
            谁调用：外层函数 get_schema_by_conf 跑到对应步骤时会调用它。
            做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
            """
            return check_status(session, trans, ds, True)

        status = await asyncio.to_thread(inner)
        if status:
            AppLogUtil.error(f"get table failed: {e}")
            raise HTTPException(status_code=500, detail=f'Get table Failed: {e.args}')


@router.post("/getFields/{id}/{table_name}", response_model=List[ColumnSchemaResponse],
             summary=f"{PLACEHOLDER_PREFIX}ds_get_fields")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def get_fields(session: SessionDep,
                     user: CurrentUser,
                     id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id"),
                     table_name: str = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_table_name")):
    """
    是什么：get_fields 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if get_ds(session, id, user) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return getFields(session, id, table_name)


@router.post("/syncFields/{id}", response_model=None, summary=f"{PLACEHOLDER_PREFIX}ds_sync_fields")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def sync_fields(session: SessionDep,
                      current_user: CurrentUser,
                      id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_table_id")):
    """
    是什么：sync_fields 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    table = session.get(CoreTable, id)
    if table is None or get_ds(session, table.ds_id, current_user) is None:
        raise HTTPException(status_code=404, detail="数据表不存在")
    register_builtin_tasks()
    return await enqueue_task(
        "datasource.sync_fields",
        {"table_id": int(id)},
        created_by=current_user.id,
        tenant_id=(
            DEFAULT_TENANT_ID
            if is_platform_admin(current_user) and not is_platform_workspace_delegate(current_user)
            else require_current_tenant_id(current_user)
        ),
    )


@router.post("/tableList/{id}", response_model=List[CoreTable], summary=f"{PLACEHOLDER_PREFIX}ds_table_list")
@require_permissions(permission=AppPermission(role=['admin'], type='ds', keyExpression="id"))
async def table_list(session: SessionDep, current_user: CurrentUser, id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id")):
    """
    是什么：table_list 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    _require_schema_metadata_admin(current_user)
    datasource = get_ds(session, id, current_user)
    if datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    tables = get_tables_by_ds_id(session, id)
    _apply_schema_comments(session, datasource, tables, user=current_user)
    if not is_normal_user(current_user):
        return tables
    contain_rules = get_user_permission_rules(session, current_user, id)
    scoped_table_ids = get_user_scoped_table_ids(session, current_user, id, contain_rules)
    if scoped_table_ids is None:
        return tables
    return [table for table in tables if int(table.id) in scoped_table_ids]


@router.post("/fieldList/{id}", response_model=List[CoreField], summary=f"{PLACEHOLDER_PREFIX}ds_field_list")
@require_permissions(permission=AppPermission(role=['admin'], type='table', keyExpression="id"))
async def field_list(session: SessionDep, current_user: CurrentUser, field: FieldObj,
                     id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_table_id")):
    """
    是什么：field_list 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    _require_schema_metadata_admin(current_user)
    table = session.get(CoreTable, id)
    if table is None:
        return []
    datasource = get_ds(session, table.ds_id, current_user)
    if datasource is None:
        return []
    contain_rules = get_user_permission_rules(session, current_user, table.ds_id) if is_normal_user(current_user) else []
    if not can_access_table(session, current_user, table.ds_id, table.id, contain_rules):
        return []
    fields = get_fields_by_table_id(session, id, field)
    visible_fields = get_column_permission_fields(session, current_user, table, fields, contain_rules)
    _apply_schema_comments(session, datasource, [table], {int(table.id): visible_fields}, current_user)
    return visible_fields


@router.post("/editLocalComment", include_in_schema=False)
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def edit_local(session: SessionDep, user: CurrentUser, data: TableObj):
    """
    是什么：edit_local 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    datasource = get_ds(session, data.table.ds_id, user) if data.table else None
    if not data.table or datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    update_table_and_fields(
        session,
        data,
        current_user_id=int(user.id) if getattr(user, "id", None) is not None else None,
        tenant_id=_metadata_tenant_id(session, datasource, user),
    )


@router.post("/editTable", response_model=None, summary=f"{PLACEHOLDER_PREFIX}ds_edit_table")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def edit_table(session: SessionDep, user: CurrentUser, table: CoreTable):
    """
    是什么：edit_table 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    datasource = get_ds(session, table.ds_id, user)
    if datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    updateTable(
        session,
        table,
        current_user_id=int(user.id) if getattr(user, "id", None) is not None else None,
        tenant_id=_metadata_tenant_id(session, datasource, user),
    )


@router.post("/editField", response_model=None, summary=f"{PLACEHOLDER_PREFIX}ds_edit_field")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def edit_field(session: SessionDep, user: CurrentUser, field: CoreField):
    """
    是什么：edit_field 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    datasource = get_ds(session, field.ds_id, user)
    if datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    updateField(
        session,
        field,
        current_user_id=int(user.id) if getattr(user, "id", None) is not None else None,
        tenant_id=_metadata_tenant_id(session, datasource, user),
    )


@router.post("/previewData/{id}", response_model=PreviewResponse, summary=f"{PLACEHOLDER_PREFIX}ds_preview_data")
@require_permissions(permission=AppPermission(role=['platform_admin'], type='ds', keyExpression="id"))
async def preview_data(session: SessionDep, trans: Trans, current_user: CurrentUser, data: TableObj,
                       id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id")):
    """
    是什么：preview_data 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if is_platform_workspace_delegate(current_user):
        raise HTTPException(status_code=403, detail="SaaS workspace delegate cannot preview datasource rows")

    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责数据源相关的一件事。
        谁调用：外层函数 preview_data 跑到对应步骤时会调用它。
        做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        try:
            return preview(session, current_user, id, data)
        except Exception as e:
            ds = get_ds(session, id, current_user)
            # 检查数据源状态
            status = check_status(session, trans, ds, True)
            if status:
                AppLogUtil.error(f"Preview failed: {e}")
                raise HTTPException(status_code=500, detail=f'Preview Failed: {e.args}')

    return await asyncio.to_thread(inner)


# 暂未使用
@router.post("/fieldEnum/{id}", include_in_schema=False)
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def field_enum(session: SessionDep, user: CurrentUser, id: int):
    """
    是什么：field_enum 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    field = session.get(CoreField, id)
    if field is None or get_ds(session, field.ds_id, user) is None:
        raise HTTPException(status_code=404, detail="字段不存在")

    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责数据源相关的一件事。
        谁调用：外层函数 field_enum 跑到对应步骤时会调用它。
        做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return fieldEnum(session, user, id)

    return await asyncio.to_thread(inner)


# @router.post("/uploadExcel")
# async def upload_excel(session: SessionDep, file: UploadFile = File(...)):
#     ALLOWED_EXTENSIONS = {"xlsx", "xls", "csv"}
#     if not file.filename.lower().endswith(tuple(ALLOWED_EXTENSIONS)):
#         raise HTTPException(400, "Only support .xlsx/.xls/.csv")
#
#     os.makedirs(path, exist_ok=True)
#     filename = f"{file.filename.split('.')[0]}_{hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:10]}.{file.filename.split('.')[1]}"
#     save_path = os.path.join(path, filename)
#     with open(save_path, "wb") as f:
#         f.write(await file.read())
#
#     def inner():
#         sheets = []
#         with get_data_engine() as conn:
#             if filename.endswith(".csv"):
#                 df = pd.read_csv(save_path, engine='c')
#                 tableName = f"sheet1_{hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:10]}"
#                 sheets.append({"tableName": tableName, "tableComment": ""})
#                 column_len = len(df.dtypes)
#                 fields = []
#                 for i in range(column_len):
#                     # build fields
#                     fields.append({"name": df.columns[i], "type": str(df.dtypes[i]), "relType": ""})
#                 # create table
#                 create_table(conn, tableName, fields)
#
#                 data = [
#                     {df.columns[i]: None if pd.isna(row[i]) else (int(row[i]) if "int" in str(df.dtypes[i]) else row[i])
#                      for i in range(len(row))}
#                     for row in df.values
#                 ]
#                 # insert data
#                 insert_data(conn, tableName, fields, data)
#             else:
#                 excel_engine = 'xlrd' if filename.endswith(".xls") else 'openpyxl'
#                 df_sheets = pd.read_excel(save_path, sheet_name=None, engine=excel_engine)
#                 # build columns and data to insert db
#                 for sheet_name, df in df_sheets.items():
#                     tableName = f"{sheet_name}_{hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:10]}"
#                     sheets.append({"tableName": tableName, "tableComment": ""})
#                     column_len = len(df.dtypes)
#                     fields = []
#                     for i in range(column_len):
#                         # build fields
#                         fields.append({"name": df.columns[i], "type": str(df.dtypes[i]), "relType": ""})
#                     # create table
#                     create_table(conn, tableName, fields)
#
#                     data = [
#                         {df.columns[i]: None if pd.isna(row[i]) else (
#                             int(row[i]) if "int" in str(df.dtypes[i]) else row[i])
#                          for i in range(len(row))}
#                         for row in df.values
#                     ]
#                     # insert data
#                     insert_data(conn, tableName, fields, data)
#
#         os.remove(save_path)
#         return {"filename": filename, "sheets": sheets}
#
#     return await asyncio.to_thread(inner)


# 已废弃
@router.post("/uploadExcel", response_model=None, summary=f"{PLACEHOLDER_PREFIX}ds_upload_excel")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def upload_excel(
        session: SessionDep,
        current_user: CurrentUser,
        file: UploadFile = File(..., description=f"{PLACEHOLDER_PREFIX}ds_excel"),
):
    """
    是什么：upload_excel 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

    tenant_path = _tenant_excel_path(current_user)
    _base_filename, filename = AppFileUtils.safe_upload_name(file.filename, ALLOWED_EXTENSIONS)
    save_path = str(AppFileUtils.safe_path(tenant_path, filename))
    with open(save_path, "wb") as f:
        f.write(await AppFileUtils.read_upload_limited(file))

    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责数据源相关的一件事。
        谁调用：外层函数 upload_excel 跑到对应步骤时会调用它。
        做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        sheets = []
        engine = get_engine_conn()
        if filename.endswith(".csv"):
            df = pd.read_csv(save_path, engine='c')
            tableName = f"sheet1_{hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:10]}"
            sheets.append({"tableName": tableName, "tableComment": ""})
            insert_pg(df, tableName, engine)
        else:
            sheet_names = pd.ExcelFile(save_path).sheet_names
            for sheet_name in sheet_names:
                tableName = f"{sheet_name}_{hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:10]}"
                sheets.append({"tableName": tableName, "tableComment": ""})
                # df_temp = pd.read_excel(save_path, nrows=5)
                # non_empty_cols = df_temp.columns[df_temp.notna().any()].tolist()
                df = pd.read_excel(save_path, sheet_name=sheet_name, engine='calamine')
                insert_pg(df, tableName, engine)

        # os.remove(save_path)
        return {"filename": filename, "sheets": sheets}

    return await asyncio.to_thread(inner)


def insert_pg(df, tableName, engine):
    # 修正字段类型
    """
    是什么：insert_pg 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：创建或保存数据源需要的东西，让后续流程能继续往下走。
    """
    for i in range(len(df.dtypes)):
        if str(df.dtypes[i]) == 'uint64':
            df[str(df.columns[i])] = df[str(df.columns[i])].astype('string')

    conn = engine.raw_connection()
    cursor = conn.cursor()
    try:
        df.to_sql(
            tableName,
            engine,
            if_exists='replace',
            index=False
        )
        # 转换 CSV
        output = StringIO()
        df.to_csv(output, sep='\t', header=False, index=False)
        # output.seek(0)

        # PostgreSQL COPY 导入
        query = sql.SQL("COPY {} FROM STDIN WITH CSV DELIMITER E'\t'").format(
            sql.Identifier(tableName)
        )
        cursor.copy_expert(sql=query.as_string(cursor.connection), file=output)
        conn.commit()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(400, str(e))
    finally:
        cursor.close()
        conn.close()


t_sheet = "数据表列表"
t_s_col = "Sheet名称"
t_n_col = "表名"
t_c_col = "表备注"
f_n_col = "字段名"
f_c_col = "字段备注"


@router.get("/exportDsSchema/{id}", response_model=None, summary=f"{PLACEHOLDER_PREFIX}ds_export_ds_schema")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def export_ds_schema(session: SessionDep, user: CurrentUser, id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id")):
    """
    是什么：export_ds_schema 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if id != 0 and get_ds(session, id, user) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    # {
    #     'sheet':'', sheet name
    #     'c1_h':'', column1 column name
    #     'c2_h':'', column2 column name
    #     'c1':[], column1 data
    #     'c2':[], column2 data
    # }
    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责数据源相关的一件事。
        谁调用：外层函数 export_ds_schema 跑到对应步骤时会调用它。
        做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        if id == 0:  # 下载模板
            df_list = [
                {'sheet': t_sheet, 'c0_h': t_s_col, 'c1_h': t_n_col, 'c2_h': t_c_col, 'c0': ["数据表1", "数据表2"],
                 'c1': ["user", "score"],
                 'c2': ["用来存放用户信息的数据表", "用来存放用户课程信息的数据表"]},
                {'sheet': '数据表1', 'c1_h': f_n_col, 'c2_h': f_c_col, 'c1': ["id", "name"],
                 'c2': ["用户id", "用户姓名"]},
                {'sheet': '数据表2', 'c1_h': f_n_col, 'c2_h': f_c_col, 'c1': ["course", "user_id", "score"],
                 'c2': ["课程名称", "用户ID", "课程得分"]},
            ]
        else:
            tables = session.query(CoreTable).filter(CoreTable.ds_id == id).order_by(
                CoreTable.table_name.asc()).all()
            datasource = get_ds(session, id, user)
            fields_by_table: dict[int, list[CoreField]] = {}
            if datasource is not None:
                table_ids = [int(table.id) for table in tables if table.id is not None]
                fields_by_table = {table_id: [] for table_id in table_ids}
                if table_ids:
                    rows = session.exec(
                        select(CoreField)
                        .where(CoreField.table_id.in_(table_ids))
                        .order_by(CoreField.table_id, CoreField.field_index, CoreField.id)
                    ).all()
                    for field in rows:
                        fields_by_table.setdefault(int(field.table_id), []).append(field)
                _apply_schema_comments(session, datasource, tables, fields_by_table, user)
            if len(tables) == 0:
                raise HTTPException(400, "No tables")

            df_list = []
            df1 = {'sheet': t_sheet, 'c0_h': t_s_col, 'c1_h': t_n_col, 'c2_h': t_c_col, 'c0': [], 'c1': [], 'c2': []}
            df_list.append(df1)
            for index, table in enumerate(tables):
                df1['c0'].append(f"Sheet{index}")
                df1['c1'].append(table.table_name)
                df1['c2'].append(table.custom_comment)

                fields = (
                    fields_by_table.get(int(table.id), [])
                    if datasource is not None
                    else session.query(CoreField).filter(CoreField.table_id == table.id).order_by(
                        CoreField.field_index.asc()).all()
                )
                df_fields = {'sheet': f"Sheet{index}", 'c1_h': f_n_col, 'c2_h': f_c_col, 'c1': [], 'c2': []}
                for field in fields:
                    df_fields['c1'].append(field.field_name)
                    df_fields['c2'].append(field.custom_comment)
                df_list.append(df_fields)

        # 构建数据表并导出
        output = io.BytesIO()

        with (pd.ExcelWriter(output, engine='xlsxwriter') as writer):
            for index, df in enumerate(df_list):
                if index == 0:
                    pd.DataFrame({df['c0_h']: df['c0'], df['c1_h']: df['c1'], df['c2_h']: df['c2']}
                                 ).to_excel(writer, sheet_name=df['sheet'], index=False)
                else:
                    pd.DataFrame({df['c1_h']: df['c1'], df['c2_h']: df['c2']}).to_excel(writer, sheet_name=df['sheet'],
                                                                                        index=False)

        output.seek(0)

        return io.BytesIO(output.getvalue())

    # headers = {
    #     'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"
    # }

    result = await asyncio.to_thread(inner)
    return StreamingResponse(
        result,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.post("/uploadDsSchema/{id}", response_model=None, summary=f"{PLACEHOLDER_PREFIX}ds_upload_ds_schema")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def upload_ds_schema(session: SessionDep, user: CurrentUser, id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id"),
                           file: UploadFile = File(...)):
    """
    是什么：upload_ds_schema 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    datasource = get_ds(session, id, user)
    if datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
    AppFileUtils.validate_extension(file.filename, ALLOWED_EXTENSIONS)

    try:
        contents = await AppFileUtils.read_upload_limited(file)
        excel_file = io.BytesIO(contents)

        sheet_names = pd.ExcelFile(excel_file, engine="openpyxl").sheet_names

        excel_file.seek(0)

        field_sheets = []
        table_sheet = None  # []
        for sheet in sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet, engine="openpyxl").fillna('')
            if sheet == t_sheet:
                table_sheet = df.where(pd.notnull(df), None).to_dict(orient="records")
            else:
                field_sheets.append(
                    {'sheet_name': sheet, 'data': df.where(pd.notnull(df), None).to_dict(orient="records")})

        # print(field_sheets)

        # 工作表与表的映射
        sheet_table_map = {}

        # 获取数据并更新
        # 更新表注释
        affected_table_ids: set[int] = set()
        metadata_tenant_id = _metadata_tenant_id(session, datasource, user)
        current_user_id = _current_user_id(user)
        if table_sheet and len(table_sheet) > 0:
            for table in table_sheet:
                sheet_table_map[table[t_s_col]] = table[t_n_col]
                save_table_comment(
                    session,
                    metadata_tenant_id,
                    table[t_n_col],
                    table[t_c_col],
                    current_user_id=current_user_id,
                )
                existing_table = session.query(CoreTable).filter(
                    and_(CoreTable.ds_id == id, CoreTable.table_name == table[t_n_col])).first()
                if existing_table:
                    affected_table_ids.add(int(existing_table.id))
                    existing_table.custom_comment = table[t_c_col]
                    session.add(existing_table)

        # 更新字段注释
        if field_sheets and len(field_sheets) > 0:
            for fields in field_sheets:
                if len(fields['data']) > 0:
                    # 获取表 ID
                    table_name = sheet_table_map.get(fields['sheet_name'])
                    table = session.query(CoreTable).filter(
                        and_(CoreTable.ds_id == id, CoreTable.table_name == table_name)).first()
                    if table:
                        for field in fields['data']:
                            save_field_comment(
                                session,
                                metadata_tenant_id,
                                table.table_name,
                                field[f_n_col],
                                field[f_c_col],
                                current_user_id=current_user_id,
                            )
                            session.query(CoreField).filter(
                                and_(CoreField.ds_id == id,
                                     CoreField.table_id == table.id,
                                     CoreField.field_name == field[f_n_col])).update(
                                {'custom_comment': field[f_c_col]})
                            affected_table_ids.add(int(table.id))
        session.commit()
        if affected_table_ids:
            run_save_table_embeddings(list(affected_table_ids), tenant_id=metadata_tenant_id)
        run_save_ds_embeddings([id], tenant_id=metadata_tenant_id)

        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse Excel Failed: {str(e)}")


@router.post("/parseExcel", response_model=None, summary=f"{PLACEHOLDER_PREFIX}ds_parse_excel")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def parse_excel(
        current_user: CurrentUser,
        file: UploadFile = File(..., description=f"{PLACEHOLDER_PREFIX}ds_excel"),
):
    """
    是什么：parse_excel 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

    tenant_path = _tenant_excel_path(current_user)
    _base_filename, filename = AppFileUtils.safe_upload_name(file.filename, ALLOWED_EXTENSIONS)
    save_path = str(AppFileUtils.safe_path(tenant_path, filename))
    with open(save_path, "wb") as f:
        f.write(await AppFileUtils.read_upload_limited(file))

    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责数据源相关的一件事。
        谁调用：外层函数 parse_excel 跑到对应步骤时会调用它。
        做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        sheets_data = parse_excel_preview(save_path)
        return {
            "filePath": filename,
            "data": sheets_data
        }

    return await asyncio.to_thread(inner)


@router.post("/importToDb", response_model=None, summary=f"{PLACEHOLDER_PREFIX}ds_import_to_db")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def import_to_db(session: SessionDep, trans: Trans, current_user: CurrentUser, import_req: ImportRequest):
    """
    是什么：import_to_db 是一个接口入口，负责接住数据源相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    safe_file_name = os.path.basename(import_req.filePath or "")
    save_path = str(AppFileUtils.safe_path(_tenant_excel_path(current_user), safe_file_name))
    if not os.path.exists(save_path):
        raise HTTPException(400, "File not found")

    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责数据源相关的一件事。
        谁调用：外层函数 import_to_db 跑到对应步骤时会调用它。
        做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        engine = get_engine_conn()
        results = []

        for sheet_info in import_req.sheets:
            sheet_name = sheet_info.sheetName
            table_name = f"excel_{filter_string(sheet_name)}_{hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:10]}"
            fields = sheet_info.fields

            field_mapping = {f.fieldName: f.fieldType for f in fields}
            dtype_dict = {
                col: USER_TYPE_TO_PANDAS.get(field_mapping.get(col, 'string'), 'string')
                for col in field_mapping.keys()
            }

            try:
                if save_path.endswith(".csv"):
                    df = pd.read_csv(save_path, engine='c', dtype=dtype_dict)
                    sheet_name = "Sheet1"
                else:
                    df = pd.read_excel(save_path, sheet_name=sheet_name, engine='calamine', dtype=dtype_dict)
            except Exception as e:
                raise HTTPException(500, f"{trans('i18n_ds_upload_error')}: {str(e)}")

            conn = engine.raw_connection()
            cursor = conn.cursor()
            try:
                df.to_sql(
                    table_name,
                    engine,
                    if_exists='replace',
                    index=False
                )
                output = StringIO()
                df.to_csv(output, sep='\t', header=False, index=False)

                query = sql.SQL("COPY {} FROM STDIN WITH CSV DELIMITER E'\t'").format(
                    sql.Identifier(table_name)
                )
                cursor.copy_expert(sql=query.as_string(cursor.connection), file=output)
                conn.commit()
                results.append({
                    "sheetName": sheet_name,
                    "tableName": table_name,
                    "tableComment": "",
                    "rows": len(df)
                })
            except Exception as e:
                raise HTTPException(500, f"Insert data failed for {table_name}: {str(e)}")
            finally:
                cursor.close()
                conn.close()

        return {"filename": safe_file_name, "sheets": results}

    return await asyncio.to_thread(inner)


# 仅允许中文、英文字母和数字
def filter_string(text):
    """
    是什么：filter_string 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    pattern = r'[^\u4e00-\u9fa5a-zA-Z0-9]'
    return re.sub(pattern, '', text)
