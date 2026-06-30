"""
脚本说明：这个脚本放系统管理的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
import asyncio
import datetime
import io
import os
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlmodel import Session, select

from apps.chat.curd.custom_prompt import (
    CustomPromptTargetScopeEnum,
    CustomPromptTypeEnum,
    CustomPromptVisibilityScopeEnum,
)
from apps.chat.curd.custom_prompt_manage import (
    batch_create_custom_prompts,
    create_custom_prompt,
    delete_custom_prompts,
    get_all_custom_prompts,
    get_custom_prompt,
    list_custom_prompt_options,
    page_custom_prompts,
    update_custom_prompt,
)
from apps.chat.models.chat_model import AxisObj
from apps.chat.models.custom_prompt_model import (
    CustomPrompt,
    CustomPromptInfo,
    CustomPromptOption,
    CustomPromptUserPreference,
)
from apps.datasource.crud.permission import (
    get_datasource_ids_with_min_role,
    has_datasource_role,
)
from apps.datasource.crud.binding import get_bound_datasource_id_for_tenant
from apps.datasource.models.datasource import CoreDatasource
from apps.system.crud.tenant import DEFAULT_TENANT_ID, TENANT_ADMIN_ROLES, normalize_tenant_role
from apps.system.crud.user import is_collab_admin, is_platform_admin, is_platform_workspace_delegate
from apps.system.schemas.access_context import require_current_tenant_id
from apps.system.models.user import UserModel
from apps.system.models.system_model import AiModelDetail
from common.audit.models.log_model import OperationModules, OperationType
from common.audit.schemas.logger_decorator import LogConfig, system_log
from common.core.config import settings
from common.core.db import engine
from common.core.deps import CurrentUser, SessionDep, Trans
from common.utils.data_format import DataFormat
from common.utils.excel import get_excel_column_count
from common.utils.file_utils import AppFileUtils

router = APIRouter(
    tags=["CustomPrompt"],
    prefix="/system/custom_prompt",
    include_in_schema=False,
)

path = settings.EXCEL_PATH
session_maker = scoped_session(sessionmaker(bind=engine, class_=Session))


def _visible_datasource_ids(session: SessionDep, current_user: CurrentUser) -> Optional[set[int]]:
    """
    是什么：_visible_datasource_ids 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if _can_manage_platform_public_prompts(session, current_user):
        return None
    return get_datasource_ids_with_min_role(session, current_user, "project_viewer")


def _can_manage_all_prompts(session: SessionDep, current_user: CurrentUser) -> bool:
    """
    是什么：_can_manage_all_prompts 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if is_platform_workspace_delegate(current_user):
        return False
    if is_collab_admin(current_user):
        return True
    try:
        db_user = session.get(UserModel, int(current_user.id))
    except (TypeError, ValueError):
        return False
    return bool(db_user and is_collab_admin(db_user))


def _can_manage_platform_public_prompts(session: SessionDep, current_user: CurrentUser) -> bool:
    """
    是什么：_can_manage_platform_public_prompts 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if is_platform_workspace_delegate(current_user):
        return False
    if is_platform_admin(current_user):
        return True
    try:
        db_user = session.get(UserModel, int(current_user.id))
    except (TypeError, ValueError):
        return False
    return bool(db_user and is_platform_admin(db_user))


def _can_manage_tenant_public_prompts(session: SessionDep, current_user: CurrentUser) -> bool:
    """
    是什么：_can_manage_tenant_public_prompts 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if _can_manage_platform_public_prompts(session, current_user):
        return False
    if _can_manage_all_prompts(session, current_user):
        return True
    tenant_role = normalize_tenant_role(getattr(current_user, "tenant_role", None))
    return tenant_role in TENANT_ADMIN_ROLES


def _is_public_scope(value) -> bool:
    """
    是什么：_is_public_scope 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if isinstance(value, CustomPromptVisibilityScopeEnum):
        return value == CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC
    return value in (None, "", CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC.value)


def _is_platform_public_scope(value) -> bool:
    """
    是什么：_is_platform_public_scope 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if isinstance(value, CustomPromptVisibilityScopeEnum):
        return value == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC
    return value == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value


def _require_prompt_manage(session: SessionDep, current_user: CurrentUser, prompt: CustomPromptInfo | CustomPrompt):
    """
    是什么：_require_prompt_manage 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if _is_platform_public_scope(getattr(prompt, "visibility_scope", None)):
        if _can_manage_platform_public_prompts(session, current_user):
            return
        raise HTTPException(status_code=403, detail="Only SaaS admin can maintain SaaS Agents")
    if _can_manage_all_prompts(session, current_user):
        return
    if (
        _is_public_scope(getattr(prompt, "visibility_scope", None))
        and _can_manage_tenant_public_prompts(session, current_user)
    ):
        return
    if (
        not _is_user_private_scope(getattr(prompt, "visibility_scope", None))
        or prompt.create_by is None
        or int(prompt.create_by) != int(current_user.id)
    ):
        raise HTTPException(status_code=403, detail="Only the creator can edit or delete this Agent")


def _normalize_datasource_ids(value) -> list[int]:
    """
    是什么：_normalize_datasource_ids 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    result: list[int] = []
    for item in value or []:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return list(dict.fromkeys(result))


def _is_user_private_scope(value) -> bool:
    """
    是什么：_is_user_private_scope 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if isinstance(value, CustomPromptVisibilityScopeEnum):
        return value == CustomPromptVisibilityScopeEnum.USER_PRIVATE
    return value == CustomPromptVisibilityScopeEnum.USER_PRIVATE.value


def _force_user_private_prompt(session: SessionDep, current_user: CurrentUser, info: CustomPromptInfo):
    """
    是什么：_force_user_private_prompt 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    info.visibility_scope = CustomPromptVisibilityScopeEnum.USER_PRIVATE
    info.specific_ds = False
    info.datasource_ids = []


def _validate_prompt_datasource_scope(session: SessionDep, current_user: CurrentUser, info: CustomPromptInfo):
    """
    是什么：_validate_prompt_datasource_scope 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    datasource_ids = _normalize_datasource_ids(info.datasource_ids)
    if not info.specific_ds:
        info.datasource_ids = []
        return
    if not datasource_ids:
        raise HTTPException(status_code=400, detail="Datasource is required")
    if not has_datasource_role(session, current_user, datasource_ids, "project_viewer"):
        raise HTTPException(status_code=403, detail="Datasource access is required")
    info.datasource_ids = datasource_ids


def _force_platform_public_prompt(info: CustomPromptInfo):
    """
    是什么：_force_platform_public_prompt 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    info.tenant_id = DEFAULT_TENANT_ID
    info.visibility_scope = CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC
    info.specific_ds = False
    info.datasource_ids = []


def _workspace_tenant_id(current_user: CurrentUser) -> int:
    """
    是什么：_workspace_tenant_id 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return require_current_tenant_id(current_user)


def _operation_tenant_id(current_user: CurrentUser, *, platform_only: bool = False) -> int:
    """
    是什么：_operation_tenant_id 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return DEFAULT_TENANT_ID if platform_only else _workspace_tenant_id(current_user)


def _prepare_prompt_for_save(session: SessionDep, current_user: CurrentUser, info: CustomPromptInfo):
    """
    是什么：_prepare_prompt_for_save 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    can_manage_platform_public = _can_manage_platform_public_prompts(session, current_user)
    can_manage_all = _can_manage_all_prompts(session, current_user)
    can_manage_public = _can_manage_tenant_public_prompts(session, current_user)
    current_tid = DEFAULT_TENANT_ID if can_manage_platform_public else _workspace_tenant_id(current_user)
    if info.id:
        existing = session.get(CustomPrompt, int(info.id))
        if not existing:
            raise HTTPException(status_code=404, detail="Custom prompt not found")
        existing_private = _is_user_private_scope(existing.visibility_scope)
        existing_platform_public = _is_platform_public_scope(existing.visibility_scope)
        if existing_private:
            if existing.create_by is None or int(existing.create_by) != int(current_user.id):
                raise HTTPException(status_code=404, detail="Custom prompt not found")
        elif existing_platform_public:
            if not can_manage_platform_public:
                raise HTTPException(status_code=404, detail="Custom prompt not found")
        elif can_manage_platform_public or int(existing.tenant_id) != current_tid:
            raise HTTPException(status_code=404, detail="Custom prompt not found")
        _require_prompt_manage(session, current_user, existing)
        if existing_private:
            info.visibility_scope = CustomPromptVisibilityScopeEnum.USER_PRIVATE
            info.tenant_id = existing.tenant_id or current_tid
            info.specific_ds = False
            info.datasource_ids = []
        elif existing_platform_public:
            _force_platform_public_prompt(info)
        else:
            if not can_manage_public:
                raise HTTPException(status_code=403, detail="Only tenant admin can maintain public Agents")
            info.tenant_id = current_tid
            _validate_prompt_datasource_scope(session, current_user, info)
            info.visibility_scope = CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC
        return

    if can_manage_platform_public:
        _force_platform_public_prompt(info)
        return

    if _is_platform_public_scope(info.visibility_scope):
        raise HTTPException(status_code=403, detail="Only SaaS admin can maintain SaaS Agents")

    if _is_user_private_scope(info.visibility_scope):
        info.tenant_id = current_tid
        _force_user_private_prompt(session, current_user, info)
        return

    if can_manage_public:
        info.tenant_id = current_tid
        _validate_prompt_datasource_scope(session, current_user, info)
        info.visibility_scope = CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC
        return

    _force_user_private_prompt(session, current_user, info)


def _require_prompt_ids_admin(session: SessionDep, current_user: CurrentUser, ids: list[int]):
    """
    是什么：_require_prompt_ids_admin 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if not ids:
        return
    rows = session.exec(select(CustomPrompt).where(CustomPrompt.id.in_(ids))).all()
    if len(rows) != len(set(ids)):
        raise HTTPException(status_code=404, detail="Custom prompt not found")
    for row in rows:
        if _is_user_private_scope(row.visibility_scope):
            if row.create_by is None or int(row.create_by) != int(current_user.id):
                raise HTTPException(status_code=404, detail="Custom prompt not found")
        elif _is_platform_public_scope(row.visibility_scope):
            if not _can_manage_platform_public_prompts(session, current_user):
                raise HTTPException(status_code=404, detail="Custom prompt not found")
        elif _can_manage_platform_public_prompts(session, current_user):
            raise HTTPException(status_code=404, detail="Custom prompt not found")
        elif int(row.tenant_id) != _workspace_tenant_id(current_user):
            raise HTTPException(status_code=404, detail="Custom prompt not found")
        _require_prompt_manage(session, current_user, row)


def _parse_type(value: str) -> CustomPromptTypeEnum:
    """
    是什么：_parse_type 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    try:
        return CustomPromptTypeEnum(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unsupported custom prompt type")


def _parse_target_scope(value: Optional[str]) -> CustomPromptTargetScopeEnum:
    """
    是什么：_parse_target_scope 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if value in (None, ""):
        return CustomPromptTargetScopeEnum.SMART_QA
    try:
        return CustomPromptTargetScopeEnum(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unsupported custom prompt target scope")


def _parse_visibility_scope(value: Optional[str]) -> CustomPromptVisibilityScopeEnum | None:
    """
    是什么：_parse_visibility_scope 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if value in (None, ""):
        return None
    try:
        return CustomPromptVisibilityScopeEnum(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unsupported custom prompt visibility scope")


def _target_scope_export_value(value: Optional[CustomPromptTargetScopeEnum | str]) -> str:
    """
    是什么：_target_scope_export_value 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not value:
        return CustomPromptTargetScopeEnum.SMART_QA.value
    try:
        return CustomPromptTargetScopeEnum(str(value)).value
    except ValueError:
        return CustomPromptTargetScopeEnum.SMART_QA.value


def _parse_target_scope_cell(value: str, trans: Trans) -> CustomPromptTargetScopeEnum:
    """
    是什么：_parse_target_scope_cell 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    raw = (value or "").strip()
    if not raw:
        return CustomPromptTargetScopeEnum.SMART_QA
    label_map = {
        CustomPromptTargetScopeEnum.SMART_QA.value.lower(): CustomPromptTargetScopeEnum.SMART_QA,
        CustomPromptTargetScopeEnum.ANALYSIS_ASSISTANT.value.lower(): CustomPromptTargetScopeEnum.ANALYSIS_ASSISTANT,
        CustomPromptTargetScopeEnum.REPORT_INTERPRETATION.value.lower(): CustomPromptTargetScopeEnum.REPORT_INTERPRETATION,
        CustomPromptTargetScopeEnum.ALL.value.lower(): CustomPromptTargetScopeEnum.ALL,
        trans("i18n_custom_prompt.target_scope_smart_qa").lower(): CustomPromptTargetScopeEnum.SMART_QA,
        trans("i18n_custom_prompt.target_scope_analysis_assistant").lower(): CustomPromptTargetScopeEnum.ANALYSIS_ASSISTANT,
        trans("i18n_custom_prompt.target_scope_report_interpretation").lower(): CustomPromptTargetScopeEnum.REPORT_INTERPRETATION,
        trans("i18n_custom_prompt.target_scope_all").lower(): CustomPromptTargetScopeEnum.ALL,
    }
    return label_map.get(raw.lower(), CustomPromptTargetScopeEnum.SMART_QA)


def _parse_active_cell(value: str) -> bool:
    """
    是什么：_parse_active_cell 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    return (value or "").strip().lower() in ["y", "yes", "true", "1", "active", "enabled", "已激活", "启用"]


def _parse_visible_cell(value: str) -> bool:
    """
    是什么：_parse_visible_cell 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    raw = (value or "").strip()
    if not raw:
        return True
    return raw.lower() in ["y", "yes", "true", "1", "visible", "shown", "show", "display", "显示", "可见"]


def _split_query_ids(value) -> Optional[list[int]]:
    """
    是什么：_split_query_ids 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if value is None or value == "":
        return None
    values = value if isinstance(value, list) else [value]
    result: list[int] = []
    for item in values:
        if item is None or item == "":
            continue
        for part in str(item).replace(",", "_").split("_"):
            if part.strip():
                result.append(int(part.strip()))
    return result or None


def _query_ids(request: Request, key: str) -> Optional[list[int]]:
    """
    是什么：_query_ids 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    return _split_query_ids(request.query_params.getlist(key))


@router.get("/options", response_model=list[CustomPromptOption])
async def options(
        session: SessionDep,
        current_user: CurrentUser,
        target_scope: str = Query(CustomPromptTargetScopeEnum.SMART_QA.value),
        custom_prompt_type: Optional[str] = Query(None),
        datasource_id: Optional[int] = Query(None),
):
    """
    是什么：options 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    can_manage_platform_public = _can_manage_platform_public_prompts(session, current_user)
    can_manage_all = _can_manage_all_prompts(session, current_user)
    can_manage_public = _can_manage_tenant_public_prompts(session, current_user)
    visible_ids = _visible_datasource_ids(session, current_user)
    return list_custom_prompt_options(
        session,
        _parse_target_scope(target_scope),
        _parse_type(custom_prompt_type) if custom_prompt_type else None,
        datasource_id=datasource_id,
        accessible_datasource_ids=visible_ids,
        current_user_id=int(current_user.id),
        can_manage_all=can_manage_all,
        can_manage_public=can_manage_public,
        can_manage_platform_public=can_manage_platform_public,
        tenant_id=_operation_tenant_id(current_user, platform_only=can_manage_platform_public),
        platform_only=can_manage_platform_public,
    )


@router.get("/{custom_prompt_type}/page/{current_page}/{page_size}")
async def pager(
        session: SessionDep,
        current_user: CurrentUser,
        request: Request,
        custom_prompt_type: str,
        current_page: int,
        page_size: int,
        name: Optional[str] = Query(None),
        visibility_scope: Optional[str] = Query(None),
        effective_only: bool = Query(False),
):
    """
    是什么：pager 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    can_manage_platform_public = _can_manage_platform_public_prompts(session, current_user)
    can_manage_all = _can_manage_all_prompts(session, current_user)
    can_manage_public = _can_manage_tenant_public_prompts(session, current_user)
    visible_ids = _visible_datasource_ids(session, current_user)
    ds_ids = _query_ids(request, "dslist")
    if ds_ids and visible_ids is not None and not set(ds_ids).issubset(visible_ids):
        raise HTTPException(status_code=403, detail="Datasource access is required")
    current_page, page_size, total_count, total_pages, data = page_custom_prompts(
        session,
        _parse_type(custom_prompt_type),
        current_page=current_page,
        page_size=page_size,
        name=name,
        dslist=ds_ids,
        accessible_datasource_ids=visible_ids,
        include_global=True,
        current_user_id=int(current_user.id),
        can_manage_all=can_manage_all,
        can_manage_public=can_manage_public,
        can_manage_platform_public=can_manage_platform_public,
        tenant_id=_operation_tenant_id(current_user, platform_only=can_manage_platform_public),
        visibility_scope=_parse_visibility_scope(visibility_scope),
        platform_only=can_manage_platform_public,
        effective_only=effective_only,
    )
    return {
        "current_page": current_page,
        "page_size": page_size,
        "total_count": total_count,
        "total_pages": total_pages,
        "data": data,
    }


@router.get("/template")
async def excel_template(trans: Trans):
    """
    是什么：excel_template 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责系统管理相关的一件事。
        谁调用：外层函数 excel_template 跑到对应步骤时会调用它。
        做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        data_list = [
            {
                "name": trans("i18n_custom_prompt.prompt_word_name_template_example1"),
                "description": trans("i18n_custom_prompt.agent_description_template_example1"),
                "target_scope": trans("i18n_custom_prompt.target_scope_smart_qa"),
                "active": "N",
                "visible": "Y",
                "ai_model": trans("i18n_custom_prompt.ai_model_template_example1"),
                "prompt": trans("i18n_custom_prompt.prompt_word_content_template_example1"),
                "datasource": trans("i18n_custom_prompt.effective_data_sources_template_example1"),
                "all_data_sources": "N",
            },
            {
                "name": trans("i18n_custom_prompt.prompt_word_name_template_example2"),
                "description": trans("i18n_custom_prompt.agent_description_template_example2"),
                "target_scope": trans("i18n_custom_prompt.target_scope_all"),
                "active": "Y",
                "visible": "Y",
                "ai_model": "",
                "prompt": trans("i18n_custom_prompt.prompt_word_content_template_example2"),
                "datasource": "",
                "all_data_sources": "Y",
            },
        ]
        fields = [
            AxisObj(name=trans("i18n_custom_prompt.prompt_word_name_template"), value="name"),
            AxisObj(name=trans("i18n_custom_prompt.agent_description_template"), value="description"),
            AxisObj(name=trans("i18n_custom_prompt.target_scope_template"), value="target_scope"),
            AxisObj(name=trans("i18n_custom_prompt.active_template"), value="active"),
            AxisObj(name=trans("i18n_custom_prompt.visible_template"), value="visible"),
            AxisObj(name=trans("i18n_custom_prompt.ai_model_template"), value="ai_model"),
            AxisObj(name=trans("i18n_custom_prompt.prompt_word_content_template"), value="prompt"),
            AxisObj(name=trans("i18n_custom_prompt.effective_data_sources_template"), value="datasource"),
            AxisObj(name=trans("i18n_custom_prompt.all_data_sources_template"), value="all_data_sources"),
        ]
        md_data, field_list = DataFormat.convert_object_array_for_pandas(fields, data_list)
        df = pd.DataFrame(md_data, columns=field_list)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter", engine_kwargs={"options": {"strings_to_numbers": False}}) as writer:
            df.to_excel(writer, sheet_name="Sheet1", index=False)
        buffer.seek(0)
        return io.BytesIO(buffer.getvalue())

    result = await asyncio.to_thread(inner)
    return StreamingResponse(result, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/{prompt_id}")
async def get_one(session: SessionDep, current_user: CurrentUser, prompt_id: int):
    """
    是什么：get_one 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    can_manage_platform_public = _can_manage_platform_public_prompts(session, current_user)
    can_manage_all = _can_manage_all_prompts(session, current_user)
    can_manage_public = _can_manage_tenant_public_prompts(session, current_user)
    info = get_custom_prompt(
        session,
        prompt_id,
        current_user_id=int(current_user.id),
        can_manage_all=can_manage_all,
        can_manage_public=can_manage_public,
        can_manage_platform_public=can_manage_platform_public,
        tenant_id=_operation_tenant_id(current_user, platform_only=can_manage_platform_public),
    )
    if can_manage_platform_public and info.visibility_scope != CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC:
        raise HTTPException(status_code=404, detail="Custom prompt not found")
    if not can_manage_all and not can_manage_platform_public:
        if info.visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE and not info.is_owner:
            raise HTTPException(status_code=403, detail="Datasource access is required")
        if info.specific_ds and not has_datasource_role(session, current_user, info.datasource_ids, "project_viewer"):
            raise HTTPException(status_code=403, detail="Datasource access is required")
    return info


@router.put("/{prompt_id}/activation")
async def set_activation(
        session: SessionDep,
        current_user: CurrentUser,
        prompt_id: int,
        enabled: bool = Query(...),
        scope: str = Query("user"),
):
    """
    是什么：set_activation 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理相关的信息改成最新状态，并保存这些变化。
    """
    prompt = session.get(CustomPrompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Custom prompt not found")

    can_manage_platform_public = _can_manage_platform_public_prompts(session, current_user)
    can_manage_all = _can_manage_all_prompts(session, current_user)
    can_manage_public = _can_manage_tenant_public_prompts(session, current_user)
    info = get_custom_prompt(
        session,
        prompt_id,
        current_user_id=int(current_user.id),
        can_manage_all=can_manage_all,
        can_manage_public=can_manage_public,
        can_manage_platform_public=can_manage_platform_public,
        tenant_id=_operation_tenant_id(current_user, platform_only=can_manage_platform_public),
    )
    if info.specific_ds and not has_datasource_role(session, current_user, info.datasource_ids, "project_viewer"):
        raise HTTPException(status_code=403, detail="Datasource access is required")

    if scope == "global":
        _require_prompt_manage(session, current_user, prompt)
        prompt.active = bool(enabled)
        session.add(prompt)
        session.commit()
        return {"active": bool(prompt.active), "user_enabled": bool(info.user_enabled)}

    if scope != "user":
        raise HTTPException(status_code=400, detail="Unsupported activation scope")
    if not prompt.active and enabled:
        raise HTTPException(status_code=403, detail="This Skill is disabled globally")

    row = session.exec(
        select(CustomPromptUserPreference).where(
            CustomPromptUserPreference.custom_prompt_id == int(prompt_id),
            CustomPromptUserPreference.user_id == int(current_user.id),
        )
    ).first()
    if not row:
        row = CustomPromptUserPreference(
            tenant_id=_workspace_tenant_id(current_user),
            custom_prompt_id=int(prompt_id),
            user_id=int(current_user.id),
        )
    row.enabled = bool(enabled)
    row.update_time = datetime.datetime.now()
    session.add(row)
    session.commit()
    return {"active": bool(prompt.active), "user_enabled": bool(row.enabled)}


@router.put("/{prompt_id}/visibility")
async def set_visibility(
        session: SessionDep,
        current_user: CurrentUser,
        prompt_id: int,
        visible: bool = Query(...),
):
    """
    是什么：set_visibility 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理相关的信息改成最新状态，并保存这些变化。
    """
    prompt = session.get(CustomPrompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Custom prompt not found")

    can_manage_platform_public = _can_manage_platform_public_prompts(session, current_user)
    can_manage_all = _can_manage_all_prompts(session, current_user)
    can_manage_public = _can_manage_tenant_public_prompts(session, current_user)
    get_custom_prompt(
        session,
        prompt_id,
        current_user_id=int(current_user.id),
        can_manage_all=can_manage_all,
        can_manage_public=can_manage_public,
        can_manage_platform_public=can_manage_platform_public,
        tenant_id=_operation_tenant_id(current_user, platform_only=can_manage_platform_public),
    )
    _require_prompt_manage(session, current_user, prompt)
    prompt.visible = bool(visible)
    session.add(prompt)
    session.commit()
    return {"visible": bool(prompt.visible)}


@router.put("")
@system_log(LogConfig(operation_type=OperationType.CREATE_OR_UPDATE, module=OperationModules.PROMPT_WORDS, resource_id_expr="info.id", result_id_expr="result_self"))
async def create_or_update(session: SessionDep, current_user: CurrentUser, info: CustomPromptInfo):
    """
    是什么：create_or_update 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    can_manage_platform_public = _can_manage_platform_public_prompts(session, current_user)
    can_manage_all = _can_manage_all_prompts(session, current_user)
    can_manage_public = _can_manage_tenant_public_prompts(session, current_user)
    _prepare_prompt_for_save(session, current_user, info)
    if info.id:
        return update_custom_prompt(
            session,
            info,
            current_user_id=int(current_user.id),
            can_manage_all=can_manage_all,
            tenant_id=_operation_tenant_id(current_user, platform_only=can_manage_platform_public),
            can_manage_public=can_manage_public,
            can_manage_platform_public=can_manage_platform_public,
        )
    return create_custom_prompt(
        session,
        info,
        current_user_id=int(current_user.id),
        tenant_id=_operation_tenant_id(current_user, platform_only=can_manage_platform_public),
    )


@router.delete("")
@system_log(LogConfig(operation_type=OperationType.DELETE, module=OperationModules.PROMPT_WORDS, resource_id_expr="id_list"))
async def delete(session: SessionDep, current_user: CurrentUser, id_list: list[int]):
    """
    是什么：delete 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理不再需要的数据、缓存或临时内容清理掉。
    """
    can_manage_platform_public = _can_manage_platform_public_prompts(session, current_user)
    can_manage_all = _can_manage_all_prompts(session, current_user)
    can_manage_public = _can_manage_tenant_public_prompts(session, current_user)
    _require_prompt_ids_admin(session, current_user, id_list)
    delete_custom_prompts(
        session,
        id_list,
        current_user_id=int(current_user.id),
        can_manage_all=can_manage_all,
        tenant_id=_operation_tenant_id(current_user, platform_only=can_manage_platform_public),
        can_manage_public=can_manage_public,
        can_manage_platform_public=can_manage_platform_public,
    )


@router.get("/{custom_prompt_type}/export")
@system_log(LogConfig(operation_type=OperationType.EXPORT, module=OperationModules.PROMPT_WORDS))
async def export_excel(
        session: SessionDep,
        current_user: CurrentUser,
        request: Request,
        trans: Trans,
        custom_prompt_type: str,
        name: Optional[str] = Query(None),
        visibility_scope: Optional[str] = Query(None),
):
    """
    是什么：export_excel 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    can_manage_platform_public = _can_manage_platform_public_prompts(session, current_user)
    can_manage_all = _can_manage_all_prompts(session, current_user)
    can_manage_public = _can_manage_tenant_public_prompts(session, current_user)
    visible_ids = _visible_datasource_ids(session, current_user)
    ds_ids = _query_ids(request, "dslist")
    if ds_ids and visible_ids is not None and not set(ds_ids).issubset(visible_ids):
        raise HTTPException(status_code=403, detail="Datasource access is required")

    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责系统管理相关的一件事。
        谁调用：外层函数 export_excel 跑到对应步骤时会调用它。
        做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        rows = get_all_custom_prompts(
            session,
            _parse_type(custom_prompt_type),
            name=name,
            dslist=ds_ids,
            accessible_datasource_ids=visible_ids,
            include_global=True,
            current_user_id=int(current_user.id),
            can_manage_all=can_manage_all,
            can_manage_public=can_manage_public,
            can_manage_platform_public=can_manage_platform_public,
            tenant_id=_operation_tenant_id(current_user, platform_only=can_manage_platform_public),
            visibility_scope=_parse_visibility_scope(visibility_scope),
            platform_only=can_manage_platform_public,
        )
        data_list = [
            {
                "name": row.name,
                "description": row.description,
                "target_scope": _target_scope_export_value(row.target_scope),
                "active": "Y" if row.active else "N",
                "visible": "Y" if row.visible else "N",
                "ai_model": row.ai_model_name or "",
                "prompt": row.prompt,
                "datasource": ", ".join(row.datasource_names or []) if row.specific_ds else "",
                "all_data_sources": "N" if row.specific_ds else "Y",
            }
            for row in rows
        ]
        fields = [
            AxisObj(name=trans("i18n_custom_prompt.prompt_word_name"), value="name"),
            AxisObj(name=trans("i18n_custom_prompt.agent_description"), value="description"),
            AxisObj(name=trans("i18n_custom_prompt.target_scope"), value="target_scope"),
            AxisObj(name=trans("i18n_custom_prompt.active"), value="active"),
            AxisObj(name=trans("i18n_custom_prompt.visible"), value="visible"),
            AxisObj(name=trans("i18n_custom_prompt.ai_model"), value="ai_model"),
            AxisObj(name=trans("i18n_custom_prompt.prompt_word_content"), value="prompt"),
            AxisObj(name=trans("i18n_custom_prompt.effective_data_sources"), value="datasource"),
            AxisObj(name=trans("i18n_custom_prompt.all_data_sources"), value="all_data_sources"),
        ]
        md_data, field_list = DataFormat.convert_object_array_for_pandas(fields, data_list)
        df = pd.DataFrame(md_data, columns=field_list)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter", engine_kwargs={"options": {"strings_to_numbers": False}}) as writer:
            df.to_excel(writer, sheet_name="Sheet1", index=False)
        buffer.seek(0)
        return io.BytesIO(buffer.getvalue())

    result = await asyncio.to_thread(inner)
    return StreamingResponse(result, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/{custom_prompt_type}/uploadExcel")
@system_log(LogConfig(operation_type=OperationType.IMPORT, module=OperationModules.PROMPT_WORDS))
async def upload_excel(
        session: SessionDep,
        trans: Trans,
        current_user: CurrentUser,
        custom_prompt_type: str,
        file: UploadFile = File(...),
):
    """
    是什么：upload_excel 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    can_manage_platform_public = _can_manage_platform_public_prompts(session, current_user)
    can_manage_tenant_public = _can_manage_tenant_public_prompts(session, current_user)
    if not (can_manage_tenant_public or can_manage_platform_public):
        raise HTTPException(status_code=403, detail="Public prompt import can only be maintained by tenant admins")
    ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
    base_filename, filename = AppFileUtils.safe_upload_name(file.filename, ALLOWED_EXTENSIONS)

    prompt_type = _parse_type(custom_prompt_type)
    os.makedirs(path, exist_ok=True)
    save_path = str(AppFileUtils.safe_path(path, filename))
    with open(save_path, "wb") as f:
        f.write(await AppFileUtils.read_upload_limited(file))

    def inner():
        """
        是什么：inner 是一个可以复用的小步骤，负责系统管理相关的一件事。
        谁调用：外层函数 upload_excel 跑到对应步骤时会调用它。
        做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        db_session = session_maker()
        try:
            if can_manage_platform_public:
                datasource_name_to_id = {}
            else:
                datasource_name_to_id = {}
                datasource_id = get_bound_datasource_id_for_tenant(
                    db_session,
                    _workspace_tenant_id(current_user),
                )
                if datasource_id is not None:
                    datasource_name_to_id = {
                        row.name.strip(): int(row.id)
                        for row in db_session.execute(
                            select(CoreDatasource.id, CoreDatasource.name).where(CoreDatasource.id == datasource_id)
                        ).all()
                        if row.name
                    }
            ai_model_name_to_id = {
                row.name.strip(): int(row.id)
                for row in db_session.execute(select(AiModelDetail.id, AiModelDetail.name)).all()
                if row.name
            }
            import_data = []
            for sheet_name in pd.ExcelFile(save_path).sheet_names:
                column_count = get_excel_column_count(save_path, sheet_name)
                if column_count < 4:
                    raise Exception(trans("i18n_excel_import.col_num_not_match"))
                if column_count >= 9:
                    use_cols = [0, 1, 2, 3, 4, 5, 6, 7, 8]
                elif column_count >= 8:
                    use_cols = [0, 1, 2, 3, 4, 5, 6, 7]
                elif column_count >= 6:
                    use_cols = [0, 1, 2, 3, 4, 5]
                else:
                    use_cols = [0, 1, 2, 3, 4] if column_count >= 5 else [0, 1, 2, 3]
                df = pd.read_excel(
                    save_path,
                    sheet_name=sheet_name,
                    engine="calamine",
                    header=0,
                    usecols=use_cols,
                    dtype=str,
                ).fillna("")
                for _, row in df.iterrows():
                    if row.isnull().all():
                        continue
                    if len(use_cols) >= 9:
                        name_raw, description_raw, target_scope_raw, active_raw, visible_raw, ai_model_raw, prompt_raw, datasource_raw, all_datasource_raw = (
                            row.iloc[0],
                            row.iloc[1],
                            row.iloc[2],
                            row.iloc[3],
                            row.iloc[4],
                            row.iloc[5],
                            row.iloc[6],
                            row.iloc[7],
                            row.iloc[8],
                        )
                    elif len(use_cols) >= 8:
                        name_raw, description_raw, target_scope_raw, active_raw, ai_model_raw, prompt_raw, datasource_raw, all_datasource_raw = (
                            row.iloc[0],
                            row.iloc[1],
                            row.iloc[2],
                            row.iloc[3],
                            row.iloc[4],
                            row.iloc[5],
                            row.iloc[6],
                            row.iloc[7],
                        )
                        visible_raw = ""
                    elif len(use_cols) >= 6:
                        name_raw, description_raw, ai_model_raw, prompt_raw, datasource_raw, all_datasource_raw = (
                            row.iloc[0],
                            row.iloc[1],
                            row.iloc[2],
                            row.iloc[3],
                            row.iloc[4],
                            row.iloc[5],
                        )
                        target_scope_raw = ""
                        active_raw = ""
                        visible_raw = ""
                    elif len(use_cols) >= 5:
                        name_raw, description_raw, prompt_raw, datasource_raw, all_datasource_raw = (
                            row.iloc[0],
                            row.iloc[1],
                            row.iloc[2],
                            row.iloc[3],
                            row.iloc[4],
                        )
                        ai_model_raw = ""
                        target_scope_raw = ""
                        active_raw = ""
                        visible_raw = ""
                    else:
                        name_raw, prompt_raw, datasource_raw, all_datasource_raw = (
                            row.iloc[0],
                            row.iloc[1],
                            row.iloc[2],
                            row.iloc[3],
                        )
                        description_raw = ""
                        ai_model_raw = ""
                        target_scope_raw = ""
                        active_raw = ""
                        visible_raw = ""

                    name = name_raw.strip() if pd.notna(name_raw) and name_raw.strip() else ""
                    description = description_raw.strip() if pd.notna(description_raw) and description_raw.strip() else ""
                    target_scope = _parse_target_scope_cell(
                        target_scope_raw.strip() if pd.notna(target_scope_raw) and target_scope_raw.strip() else "",
                        trans,
                    )
                    active = _parse_active_cell(active_raw if pd.notna(active_raw) else "")
                    visible = _parse_visible_cell(visible_raw if pd.notna(visible_raw) else "")
                    ai_model_name = ai_model_raw.strip() if pd.notna(ai_model_raw) and ai_model_raw.strip() else ""
                    ai_model_id = ai_model_name_to_id.get(ai_model_name) if ai_model_name else None
                    prompt = prompt_raw.strip() if pd.notna(prompt_raw) and prompt_raw.strip() else ""
                    datasource_names = [item.strip() for item in datasource_raw.split(",") if item.strip()] if pd.notna(datasource_raw) else []
                    all_datasource = bool(pd.notna(all_datasource_raw) and all_datasource_raw.lower().strip() in ["y", "yes", "true"])
                    datasource_ids = [datasource_name_to_id[item] for item in datasource_names if item in datasource_name_to_id]
                    visibility_scope = (
                        CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC
                        if can_manage_platform_public
                        else CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC
                    )
                    import_data.append(CustomPromptInfo(
                        tenant_id=_operation_tenant_id(current_user, platform_only=can_manage_platform_public),
                        type=prompt_type,
                        name=name,
                        description=description,
                        target_scope=target_scope,
                        active=active,
                        visible=visible,
                        ai_model_id=ai_model_id,
                        ai_model_name=ai_model_name if ai_model_id else None,
                        prompt=prompt,
                        datasource_names=[] if can_manage_platform_public else datasource_names,
                        datasource_ids=[] if can_manage_platform_public else datasource_ids,
                        specific_ds=False if can_manage_platform_public else not all_datasource,
                        visibility_scope=visibility_scope,
                    ))
            result = batch_create_custom_prompts(
                db_session,
                import_data,
                int(current_user.id),
                _operation_tenant_id(current_user, platform_only=can_manage_platform_public),
            )

            error_excel_filename = None
            if result["failed_records"]:
                error_rows = []
                for obj in result["failed_records"]:
                    data = obj["data"]
                    error_rows.append({
                        "name": data.name,
                        "description": data.description,
                        "target_scope": _target_scope_export_value(data.target_scope),
                        "active": "Y" if data.active else "N",
                        "visible": "Y" if data.visible else "N",
                        "ai_model": data.ai_model_name or "",
                        "prompt": data.prompt,
                        "datasource": ", ".join(data.datasource_names or []),
                        "all_data_sources": "N" if data.specific_ds else "Y",
                        "errors": ", ".join(str(item) for item in obj["errors"]),
                    })
                fields = [
                    AxisObj(name=trans("i18n_custom_prompt.prompt_word_name"), value="name"),
                    AxisObj(name=trans("i18n_custom_prompt.agent_description"), value="description"),
                    AxisObj(name=trans("i18n_custom_prompt.target_scope"), value="target_scope"),
                    AxisObj(name=trans("i18n_custom_prompt.active"), value="active"),
                    AxisObj(name=trans("i18n_custom_prompt.visible"), value="visible"),
                    AxisObj(name=trans("i18n_custom_prompt.ai_model"), value="ai_model"),
                    AxisObj(name=trans("i18n_custom_prompt.prompt_word_content"), value="prompt"),
                    AxisObj(name=trans("i18n_custom_prompt.effective_data_sources"), value="datasource"),
                    AxisObj(name=trans("i18n_custom_prompt.all_data_sources"), value="all_data_sources"),
                    AxisObj(name=trans("i18n_common.error_info"), value="errors"),
                ]
                md_data, field_list = DataFormat.convert_object_array_for_pandas(fields, error_rows)
                df = pd.DataFrame(md_data, columns=field_list)
                error_excel_filename = f"{base_filename}_error.xlsx"
                df.to_excel(os.path.join(path, error_excel_filename), index=False)

            return {
                "success_count": result["success_count"],
                "failed_count": len(result["failed_records"]),
                "duplicate_count": result["duplicate_count"],
                "original_count": result["original_count"],
                "error_excel_filename": error_excel_filename,
            }
        finally:
            db_session.close()

    return await asyncio.to_thread(inner)
