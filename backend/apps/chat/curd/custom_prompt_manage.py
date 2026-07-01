"""
脚本说明：这个脚本封装聊天问数据和 Agent的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
import datetime
import json
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, case, delete, event, func, or_, select

from apps.chat.curd.custom_prompt import (
    CustomPromptTargetScopeEnum,
    CustomPromptTypeEnum,
    CustomPromptVisibilityScopeEnum,
)
from apps.chat.curd.custom_prompt_embedding import skill_definition_signature
from apps.chat.models.custom_prompt_model import (
    CustomPrompt,
    CustomPromptInfo,
    CustomPromptOption,
    CustomPromptUserPreference,
)
from apps.datasource.crud.binding import get_bound_datasource_id_for_tenant
from apps.datasource.models.datasource import CoreDatasource
from apps.system.crud.tenant import DEFAULT_TENANT_ID
from apps.system.models.system_model import AiModelDetail
from apps.system.schemas.access_context import require_tenant_id
from common.core.deps import SessionDep
from common.utils.embedding_threads import run_save_custom_prompt_skill_embeddings


def _normalize_type(custom_prompt_type: CustomPromptTypeEnum | str | None) -> CustomPromptTypeEnum:
    """
    是什么：_normalize_type 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if isinstance(custom_prompt_type, CustomPromptTypeEnum):
        return custom_prompt_type
    try:
        return CustomPromptTypeEnum(str(custom_prompt_type))
    except ValueError:
        raise HTTPException(status_code=400, detail="Unsupported custom prompt type")


def _normalize_target_scope(
        target_scope: CustomPromptTargetScopeEnum | str | None,
) -> CustomPromptTargetScopeEnum:
    """
    是什么：_normalize_target_scope 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if isinstance(target_scope, CustomPromptTargetScopeEnum):
        return target_scope
    if target_scope in (None, ""):
        return CustomPromptTargetScopeEnum.SMART_QA
    try:
        return CustomPromptTargetScopeEnum(str(target_scope))
    except ValueError:
        raise HTTPException(status_code=400, detail="Unsupported custom prompt target scope")


def _ensure_target_scope_allowed(
        prompt_type: CustomPromptTypeEnum,
        target_scope: CustomPromptTargetScopeEnum,
) -> None:
    """
    是什么：_ensure_target_scope_allowed 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查聊天问数据和 Agent里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if (
        target_scope == CustomPromptTargetScopeEnum.REPORT_INTERPRETATION
        and prompt_type != CustomPromptTypeEnum.DATA_SKILL
    ):
        raise HTTPException(status_code=400, detail="Report interpretation scope only supports Data Skills")


def _normalize_platform_generic_scope(
        visibility_scope: CustomPromptVisibilityScopeEnum,
        specific_ds: bool,
        datasource_ids: list[int],
) -> tuple[int | None, bool, list[int]]:
    """
    是什么：_normalize_platform_generic_scope 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC:
        return DEFAULT_TENANT_ID, specific_ds, datasource_ids
    return None, specific_ds, datasource_ids


def _normalize_visibility_scope(
        visibility_scope: CustomPromptVisibilityScopeEnum | str | None,
) -> CustomPromptVisibilityScopeEnum:
    """
    是什么：_normalize_visibility_scope 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if isinstance(visibility_scope, CustomPromptVisibilityScopeEnum):
        return visibility_scope
    if visibility_scope in (None, ""):
        return CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC
    try:
        return CustomPromptVisibilityScopeEnum(str(visibility_scope))
    except ValueError:
        raise HTTPException(status_code=400, detail="Unsupported custom prompt visibility scope")


def _normalize_ids(datasource_ids: Optional[list[int]]) -> list[int]:
    """
    是什么：_normalize_ids 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    result: list[int] = []
    if isinstance(datasource_ids, str):
        try:
            datasource_ids = json.loads(datasource_ids)
        except json.JSONDecodeError:
            datasource_ids = [datasource_ids]
    for item in datasource_ids or []:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return list(dict.fromkeys(result))


def _normalize_ai_model_id(ai_model_id: Optional[int | str]) -> Optional[int]:
    """
    是什么：_normalize_ai_model_id 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if ai_model_id in (None, ""):
        return None
    try:
        return int(ai_model_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="AI model is invalid")


def _datasource_name_map(session: SessionDep, datasource_ids: list[int]) -> dict[int, str]:
    """
    是什么：_datasource_name_map 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not datasource_ids:
        return {}
    rows = session.execute(
        select(CoreDatasource.id, CoreDatasource.name).where(CoreDatasource.id.in_(datasource_ids))
    ).all()
    return {int(row.id): row.name for row in rows}


def _ai_model_name_map(session: SessionDep, ai_model_ids: list[int]) -> dict[int, str]:
    """
    是什么：_ai_model_name_map 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not ai_model_ids:
        return {}
    rows = session.execute(
        select(AiModelDetail.id, AiModelDetail.name).where(AiModelDetail.id.in_(ai_model_ids))
    ).all()
    return {int(row.id): row.name for row in rows}


def _require_ai_model(session: SessionDep, ai_model_id: Optional[int]) -> Optional[int]:
    """
    是什么：_require_ai_model 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查聊天问数据和 Agent里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if ai_model_id is None:
        return None
    if not session.get(AiModelDetail, ai_model_id):
        raise HTTPException(status_code=400, detail="AI model not found")
    return ai_model_id


def ensure_custom_prompt_owner(
        row: CustomPrompt,
        current_user_id: int,
        can_manage_all: bool = False,
        can_manage_public: bool = False,
        can_manage_platform_public: bool = False,
):
    """
    是什么：ensure_custom_prompt_owner 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查聊天问数据和 Agent里的数据、权限或配置是否合法，不对就及时拦住。
    """
    visibility_scope = _normalize_visibility_scope(row.visibility_scope)
    if visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC and can_manage_platform_public:
        return
    if visibility_scope == CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC and (can_manage_all or can_manage_public):
        return
    if (
        visibility_scope != CustomPromptVisibilityScopeEnum.USER_PRIVATE
        or row.create_by is None
        or int(row.create_by) != int(current_user_id)
    ):
        raise HTTPException(status_code=403, detail="Only the creator can edit or delete this Agent")


def _is_owner(row: CustomPrompt, current_user_id: Optional[int]) -> bool:
    """
    是什么：_is_owner 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return (
        current_user_id is not None
        and row.create_by is not None
        and int(row.create_by) == int(current_user_id)
    )


def _can_manage_row(
        row: CustomPrompt,
        current_user_id: Optional[int],
        can_manage_all: bool,
        can_manage_public: bool = False,
        can_manage_platform_public: bool = False,
) -> bool:
    """
    是什么：_can_manage_row 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    visibility_scope = _normalize_visibility_scope(row.visibility_scope)
    if visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC:
        return can_manage_platform_public
    if visibility_scope == CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC:
        return can_manage_all or can_manage_public
    return visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE and _is_owner(row, current_user_id)


def _row_visible_to_current_user(
        row: CustomPrompt,
        current_user_id: Optional[int],
        can_manage_all: bool,
        can_manage_public: bool = False,
        can_manage_platform_public: bool = False,
) -> bool:
    """
    是什么：_row_visible_to_current_user 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    visibility_scope = _normalize_visibility_scope(row.visibility_scope)
    visible = bool(row.visible) if row.visible is not None else True
    if visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC:
        return visible or can_manage_platform_public
    if visibility_scope == CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC:
        return visible or can_manage_all or can_manage_public
    return visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE and _is_owner(row, current_user_id)


def _prompt_visible(
        row: CustomPrompt,
        current_user_id: Optional[int],
        can_manage_all: bool,
        can_manage_public: bool = False,
) -> bool:
    """
    是什么：_prompt_visible 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    visibility_scope = _normalize_visibility_scope(row.visibility_scope)
    if visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC:
        return True
    if visibility_scope == CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC:
        return can_manage_all or can_manage_public
    return visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE and _is_owner(row, current_user_id)


def _to_info(
        row: CustomPrompt,
        ds_names: Optional[dict[int, str]] = None,
        ai_model_names: Optional[dict[int, str]] = None,
        current_user_id: Optional[int] = None,
        can_manage_all: bool = False,
        can_manage_public: bool = False,
        can_manage_platform_public: bool = False,
        user_enabled: Optional[bool] = True,
) -> CustomPromptInfo:
    """
    是什么：_to_info 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    datasource_ids = _normalize_ids(row.datasource_ids)
    ds_names = ds_names or {}
    ai_model_id = _normalize_ai_model_id(row.ai_model_id)
    ai_model_names = ai_model_names or {}
    visibility_scope = _normalize_visibility_scope(row.visibility_scope)
    if visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC and not row.specific_ds:
        datasource_ids = []
    is_owner = _is_owner(row, current_user_id)
    prompt_visible = _prompt_visible(row, current_user_id, can_manage_all, can_manage_public)
    return CustomPromptInfo(
        id=row.id,
        tenant_id=row.tenant_id,
        type=_normalize_type(row.type) if row.type else None,
        create_time=row.create_time,
        name=row.name,
        description=row.description,
        target_scope=_normalize_target_scope(row.target_scope),
        active=bool(row.active),
        visible=bool(row.visible) if row.visible is not None else True,
        ai_model_id=ai_model_id,
        ai_model_name=ai_model_names.get(ai_model_id) if ai_model_id else None,
        is_owner=is_owner,
        can_manage=_can_manage_row(
            row,
            current_user_id,
            can_manage_all,
            can_manage_public,
            can_manage_platform_public,
        ),
        prompt_visible=prompt_visible,
        user_enabled=True if user_enabled is None else bool(user_enabled),
        effective_active=bool(row.active) and (True if user_enabled is None else bool(user_enabled)),
        visibility_scope=visibility_scope,
        prompt=row.prompt if prompt_visible else None,
        specific_ds=bool(row.specific_ds),
        datasource_ids=datasource_ids,
        datasource_names=[ds_names[item] for item in datasource_ids if item in ds_names],
    )


def _to_option(
        row: CustomPrompt,
        ai_model_names: Optional[dict[int, str]] = None,
) -> CustomPromptOption:
    """
    是什么：_to_option 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    ai_model_id = _normalize_ai_model_id(row.ai_model_id)
    ai_model_names = ai_model_names or {}
    return CustomPromptOption(
        id=int(row.id),
        type=_normalize_type(row.type) if row.type else None,
        name=row.name,
        description=row.description,
        target_scope=_normalize_target_scope(row.target_scope),
        visibility_scope=_normalize_visibility_scope(row.visibility_scope),
        ai_model_id=ai_model_id,
        ai_model_name=ai_model_names.get(ai_model_id) if ai_model_id else None,
        visible=bool(row.visible) if row.visible is not None else True,
    )


def _access_conditions(accessible_datasource_ids: Optional[set[int]], include_global: bool = True):
    """
    是什么：_access_conditions 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if accessible_datasource_ids is None:
        return []
    conditions = []
    for ds_id in accessible_datasource_ids:
        conditions.append(CustomPrompt.datasource_ids.contains([int(ds_id)]))
    if include_global:
        conditions.extend([
            CustomPrompt.datasource_ids == [],
            CustomPrompt.specific_ds == False,
            CustomPrompt.specific_ds.is_(None),
        ])
    return conditions


def _tenant_public_visibility_condition():
    """
    是什么：_tenant_public_visibility_condition 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return or_(
        CustomPrompt.visibility_scope == CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC.value,
        CustomPrompt.visibility_scope.is_(None),
    )


def _platform_public_visibility_condition():
    """
    是什么：_platform_public_visibility_condition 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return CustomPrompt.visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value


def _visible_flag_condition():
    """
    是什么：_visible_flag_condition 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return or_(CustomPrompt.visible == True, CustomPrompt.visible.is_(None))


def _display_visible_condition(
        current_user_id: Optional[int],
        can_manage_all: bool = False,
        can_manage_public: bool = False,
        can_manage_platform_public: bool = False,
):
    """
    是什么：_display_visible_condition 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    visible_flag = _visible_flag_condition()
    platform_condition = _platform_public_visibility_condition()
    if not can_manage_platform_public:
        platform_condition = and_(platform_condition, visible_flag)

    tenant_condition = _tenant_public_visibility_condition()
    if not (can_manage_all or can_manage_public):
        tenant_condition = and_(tenant_condition, visible_flag)

    return or_(
        platform_condition,
        tenant_condition,
        _private_visibility_condition(current_user_id),
    )


def _source_order_expression():
    """
    是什么：_source_order_expression 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return case(
        (CustomPrompt.visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value, 0),
        (CustomPrompt.visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE.value, 2),
        else_=1,
    )


def _split_legacy_data_skill_condition():
    """
    是什么：_split_legacy_data_skill_condition 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return or_(
        CustomPrompt.prompt.contains("<!-- data-skill-source:terminology:"),
        CustomPrompt.prompt.contains("<!-- data-skill-source:data-training:"),
        CustomPrompt.prompt.contains("<!-- data-skill-source:custom-prompt-generate-sql:"),
        CustomPrompt.prompt.contains("<!-- data-skill-source:legacy-semantic:"),
        CustomPrompt.prompt.contains("<!-- data-skill-source:semantic-theme:saas:"),
    )


def _apply_hidden_generated_skill_filter(stmt, prompt_type: CustomPromptTypeEnum):
    """
    是什么：_apply_hidden_generated_skill_filter 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if prompt_type != CustomPromptTypeEnum.DATA_SKILL:
        return stmt
    return stmt.where(~_split_legacy_data_skill_condition())


def _tenant_id(tenant_id: int | str | None) -> int:
    """
    是什么：_tenant_id 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return require_tenant_id(tenant_id)


def _schedule_skill_embedding_after_commit(
        session: SessionDep,
        prompt_id: int,
        tenant_id: int | None,
) -> None:
    """
    是什么：_schedule_skill_embedding_after_commit 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    pending = session.info.setdefault("custom_prompt_skill_embedding_after_commit", {})
    pending[int(prompt_id)] = int(tenant_id) if tenant_id is not None else None
    if session.info.get("custom_prompt_skill_embedding_listener_registered"):
        return

    def _enqueue(_session):
        """
        是什么：_enqueue 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 _schedule_skill_embedding_after_commit 跑到对应步骤时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        queued = _session.info.pop("custom_prompt_skill_embedding_after_commit", {})
        _session.info.pop("custom_prompt_skill_embedding_listener_registered", None)
        _session.info.pop("custom_prompt_skill_embedding_rollback_listener_registered", None)
        ids_by_tenant: dict[int | None, list[int]] = {}
        for queued_prompt_id, queued_tenant_id in queued.items():
            ids_by_tenant.setdefault(queued_tenant_id, []).append(int(queued_prompt_id))
        for queued_tenant_id, queued_ids in ids_by_tenant.items():
            run_save_custom_prompt_skill_embeddings(queued_ids, tenant_id=queued_tenant_id)

    def _clear(_session):
        """
        是什么：_clear 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 _schedule_skill_embedding_after_commit 跑到对应步骤时会调用它。
        做了什么：把聊天问数据和 Agent不再需要的数据、缓存或临时内容清理掉。
        """
        _session.info.pop("custom_prompt_skill_embedding_after_commit", None)
        _session.info.pop("custom_prompt_skill_embedding_listener_registered", None)
        _session.info.pop("custom_prompt_skill_embedding_rollback_listener_registered", None)

    session.info["custom_prompt_skill_embedding_listener_registered"] = True
    event.listen(session, "after_commit", _enqueue, once=True)
    if not session.info.get("custom_prompt_skill_embedding_rollback_listener_registered"):
        session.info["custom_prompt_skill_embedding_rollback_listener_registered"] = True
        event.listen(session, "after_rollback", _clear, once=True)


def _mark_skill_embedding_stale_if_needed(row: CustomPrompt, prompt_type: CustomPromptTypeEnum) -> bool:
    """
    是什么：_mark_skill_embedding_stale_if_needed 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if prompt_type != CustomPromptTypeEnum.DATA_SKILL:
        if getattr(row, "embedding", None) or getattr(row, "embedding_signature", None):
            row.embedding = None
            row.embedding_signature = None
        return False

    expected_signature = skill_definition_signature(row.name, row.description, row.prompt)
    if row.embedding and row.embedding_signature == expected_signature:
        return False
    row.embedding = None
    row.embedding_signature = None
    return True


def _private_visibility_condition(current_user_id: Optional[int]):
    """
    是什么：_private_visibility_condition 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if current_user_id is None:
        return False
    return and_(
        CustomPrompt.visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE.value,
        CustomPrompt.create_by == int(current_user_id),
    )


def _visible_conditions(
        datasource_ids: Optional[set[int]],
        current_user_id: Optional[int],
        can_manage_all: bool,
        include_global: bool = True,
):
    """
    是什么：_visible_conditions 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if datasource_ids is None:
        return [_platform_public_visibility_condition()]

    access = _access_conditions(datasource_ids, include_global)
    if not access:
        return []
    access_condition = or_(*access)
    if can_manage_all:
        return [access_condition]

    conditions = [
        and_(_platform_public_visibility_condition(), access_condition),
        and_(_tenant_public_visibility_condition(), access_condition),
    ]
    private_condition = _private_visibility_condition(current_user_id)
    if private_condition is not False:
        conditions.append(and_(private_condition, access_condition))
    return conditions


def _build_query(
        custom_prompt_type: CustomPromptTypeEnum | str,
        name: Optional[str] = None,
        dslist: Optional[list[int]] = None,
        accessible_datasource_ids: Optional[set[int]] = None,
        include_global: bool = True,
        current_user_id: Optional[int] = None,
        can_manage_all: bool = False,
        tenant_id: int | None = None,
        can_manage_public: bool = False,
        can_manage_platform_public: bool = False,
        visibility_scope: CustomPromptVisibilityScopeEnum | str | None = None,
        platform_only: bool = False,
        effective_only: bool = False,
):
    """
    是什么：_build_query 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存聊天问数据和 Agent需要的东西，让后续流程能继续往下走。
    """
    prompt_type = _normalize_type(custom_prompt_type)
    resolved_tenant_id = _tenant_id(tenant_id)
    private_condition = _private_visibility_condition(current_user_id)
    visibility_conditions = [
        and_(CustomPrompt.tenant_id == resolved_tenant_id, _tenant_public_visibility_condition()),
        _platform_public_visibility_condition(),
        private_condition,
    ]
    if platform_only:
        visibility_conditions = [_platform_public_visibility_condition()]
    stmt = select(CustomPrompt).where(CustomPrompt.type == prompt_type.value, or_(*visibility_conditions))
    stmt = _apply_hidden_generated_skill_filter(stmt, prompt_type)
    stmt = stmt.where(_display_visible_condition(
        current_user_id,
        can_manage_all,
        can_manage_public,
        can_manage_platform_public,
    ))
    if effective_only:
        stmt = stmt.where(CustomPrompt.active == True)
        stmt = _apply_user_enabled_filter(stmt, current_user_id)
    if visibility_scope:
        normalized_visibility = _normalize_visibility_scope(visibility_scope)
        if normalized_visibility == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC:
            stmt = stmt.where(_platform_public_visibility_condition())
        elif normalized_visibility == CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC:
            stmt = stmt.where(and_(CustomPrompt.tenant_id == resolved_tenant_id, _tenant_public_visibility_condition()))
        else:
            stmt = stmt.where(_private_visibility_condition(current_user_id))

    if name and name.strip():
        keyword = f"%{name.strip()}%"
        keyword_conditions = [
            CustomPrompt.name.ilike(keyword),
            CustomPrompt.description.ilike(keyword),
        ]
        if can_manage_all or can_manage_public:
            keyword_conditions.append(CustomPrompt.prompt.ilike(keyword))
        stmt = stmt.where(or_(*keyword_conditions))

    visible_datasource_ids = set(int(item) for item in dslist) if dslist else accessible_datasource_ids
    access_conditions = _visible_conditions(
        visible_datasource_ids,
        current_user_id,
        can_manage_all,
        include_global,
    )
    if visible_datasource_ids is not None:
        stmt = stmt.where(or_(*access_conditions) if access_conditions else False)

    if dslist and can_manage_all:
        ds_conditions = [CustomPrompt.datasource_ids.contains([int(ds_id)]) for ds_id in dslist]
        if include_global:
            ds_conditions.extend([
                CustomPrompt.datasource_ids == [],
                CustomPrompt.specific_ds == False,
                CustomPrompt.specific_ds.is_(None),
            ])
        stmt = stmt.where(or_(*ds_conditions))

    return stmt


def _target_scope_condition(target_scope: CustomPromptTargetScopeEnum | str):
    """
    是什么：_target_scope_condition 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    normalized_scope = _normalize_target_scope(target_scope)
    conditions = [
        CustomPrompt.target_scope == normalized_scope.value,
        CustomPrompt.target_scope == CustomPromptTargetScopeEnum.ALL.value,
    ]
    if normalized_scope == CustomPromptTargetScopeEnum.SMART_QA:
        conditions.append(CustomPrompt.target_scope.is_(None))
    return or_(*conditions)


def _user_enabled_map(
        session: SessionDep,
        prompt_ids: list[int],
        current_user_id: Optional[int],
) -> dict[int, bool]:
    """
    是什么：_user_enabled_map 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not prompt_ids or current_user_id is None:
        return {}
    rows = session.execute(
        select(
            CustomPromptUserPreference.custom_prompt_id,
            CustomPromptUserPreference.enabled,
        ).where(
            CustomPromptUserPreference.user_id == int(current_user_id),
            CustomPromptUserPreference.custom_prompt_id.in_(prompt_ids),
        )
    ).all()
    return {int(row.custom_prompt_id): bool(row.enabled) for row in rows}


def _apply_user_enabled_filter(stmt, current_user_id: Optional[int]):
    """
    是什么：_apply_user_enabled_filter 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if current_user_id is None:
        return stmt
    disabled_for_user = select(CustomPromptUserPreference.custom_prompt_id).where(
        CustomPromptUserPreference.user_id == int(current_user_id),
        CustomPromptUserPreference.enabled == False,
    )
    return stmt.where(CustomPrompt.id.not_in(disabled_for_user))


def list_custom_prompt_options(
        session: SessionDep,
        target_scope: CustomPromptTargetScopeEnum | str,
        custom_prompt_type: Optional[CustomPromptTypeEnum | str] = None,
        datasource_id: Optional[int] = None,
        accessible_datasource_ids: Optional[set[int]] = None,
        current_user_id: Optional[int] = None,
        can_manage_all: bool = False,
        can_manage_public: bool = False,
        can_manage_platform_public: bool = False,
        tenant_id: int | None = None,
        platform_only: bool = False,
) -> list[CustomPromptOption]:
    """
    是什么：list_custom_prompt_options 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent需要的数据找出来，整理成后面好用的样子。
    """
    resolved_tenant_id = _tenant_id(tenant_id)
    private_condition = _private_visibility_condition(current_user_id)
    visibility_conditions = [
        and_(CustomPrompt.tenant_id == resolved_tenant_id, _tenant_public_visibility_condition()),
        _platform_public_visibility_condition(),
        private_condition,
    ]
    if platform_only:
        visibility_conditions = [_platform_public_visibility_condition()]
    stmt = select(CustomPrompt).where(
        CustomPrompt.active == True,
        _target_scope_condition(target_scope),
        or_(*visibility_conditions),
        _display_visible_condition(
            current_user_id,
            can_manage_all,
            can_manage_public,
            can_manage_platform_public,
        ),
    )
    stmt = _apply_user_enabled_filter(stmt, current_user_id)
    if custom_prompt_type:
        prompt_type = _normalize_type(custom_prompt_type)
        stmt = stmt.where(CustomPrompt.type == prompt_type.value)
        stmt = _apply_hidden_generated_skill_filter(stmt, prompt_type)

    if datasource_id is not None:
        if accessible_datasource_ids is not None and int(datasource_id) not in accessible_datasource_ids:
            raise HTTPException(status_code=403, detail="Datasource access is required")
        ds_conditions = _visible_conditions({int(datasource_id)}, current_user_id, can_manage_all, include_global=True)
        stmt = stmt.where(or_(*ds_conditions) if ds_conditions else False)
    elif accessible_datasource_ids is not None:
        ds_conditions = _visible_conditions(accessible_datasource_ids, current_user_id, can_manage_all, include_global=True)
        stmt = stmt.where(or_(*ds_conditions) if ds_conditions else False)

    rows = session.execute(
        stmt.order_by(_source_order_expression(), CustomPrompt.create_time.desc(), CustomPrompt.id.desc())
    ).scalars().all()
    ai_model_ids: list[int] = []
    for row in rows:
        ai_model_id = _normalize_ai_model_id(row.ai_model_id)
        if ai_model_id:
            ai_model_ids.append(ai_model_id)
    ai_model_names = _ai_model_name_map(session, list(dict.fromkeys(ai_model_ids)))
    return [_to_option(row, ai_model_names) for row in rows]


def page_custom_prompts(
        session: SessionDep,
        custom_prompt_type: CustomPromptTypeEnum | str,
        current_page: int = 1,
        page_size: int = 10,
        name: Optional[str] = None,
        dslist: Optional[list[int]] = None,
        accessible_datasource_ids: Optional[set[int]] = None,
        include_global: bool = True,
        current_user_id: Optional[int] = None,
        can_manage_all: bool = False,
        can_manage_public: bool = False,
        tenant_id: int | None = None,
        can_manage_platform_public: bool = False,
        visibility_scope: CustomPromptVisibilityScopeEnum | str | None = None,
        platform_only: bool = False,
        effective_only: bool = False,
):
    """
    是什么：page_custom_prompts 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    stmt = _build_query(
        custom_prompt_type=custom_prompt_type,
        name=name,
        dslist=dslist,
        accessible_datasource_ids=accessible_datasource_ids,
        include_global=include_global,
        current_user_id=current_user_id,
        can_manage_all=can_manage_all,
        tenant_id=tenant_id,
        can_manage_public=can_manage_public,
        can_manage_platform_public=can_manage_platform_public,
        visibility_scope=visibility_scope,
        platform_only=platform_only,
        effective_only=effective_only,
    )
    total_count = session.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    page_size = max(10, page_size)
    total_pages = (total_count + page_size - 1) // page_size if total_count else 0
    current_page = max(1, min(current_page, total_pages)) if total_pages > 0 else 1

    rows = session.execute(
        stmt.order_by(_source_order_expression(), CustomPrompt.create_time.desc(), CustomPrompt.id.desc())
        .offset((current_page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    datasource_ids: list[int] = []
    ai_model_ids: list[int] = []
    for row in rows:
        datasource_ids.extend(_normalize_ids(row.datasource_ids))
        ai_model_id = _normalize_ai_model_id(row.ai_model_id)
        if ai_model_id:
            ai_model_ids.append(ai_model_id)
    ds_names = _datasource_name_map(session, list(dict.fromkeys(datasource_ids)))
    ai_model_names = _ai_model_name_map(session, list(dict.fromkeys(ai_model_ids)))
    user_enabled = _user_enabled_map(session, [int(row.id) for row in rows if row.id], current_user_id)

    return current_page, page_size, total_count, total_pages, [
        _to_info(
            row,
            ds_names,
            ai_model_names,
            current_user_id,
            can_manage_all,
            can_manage_public,
            can_manage_platform_public,
            user_enabled.get(int(row.id), True) if row.id else True,
        )
        for row in rows
    ]


def get_all_custom_prompts(
        session: SessionDep,
        custom_prompt_type: CustomPromptTypeEnum | str,
        name: Optional[str] = None,
        dslist: Optional[list[int]] = None,
        accessible_datasource_ids: Optional[set[int]] = None,
        include_global: bool = True,
        current_user_id: Optional[int] = None,
        can_manage_all: bool = False,
        can_manage_public: bool = False,
        tenant_id: int | None = None,
        can_manage_platform_public: bool = False,
        visibility_scope: CustomPromptVisibilityScopeEnum | str | None = None,
        platform_only: bool = False,
        effective_only: bool = False,
) -> list[CustomPromptInfo]:
    """
    是什么：get_all_custom_prompts 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent需要的数据找出来，整理成后面好用的样子。
    """
    stmt = _build_query(
        custom_prompt_type=custom_prompt_type,
        name=name,
        dslist=dslist,
        accessible_datasource_ids=accessible_datasource_ids,
        include_global=include_global,
        current_user_id=current_user_id,
        can_manage_all=can_manage_all,
        tenant_id=tenant_id,
        can_manage_public=can_manage_public,
        can_manage_platform_public=can_manage_platform_public,
        visibility_scope=visibility_scope,
        platform_only=platform_only,
        effective_only=effective_only,
    )
    rows = session.execute(
        stmt.order_by(_source_order_expression(), CustomPrompt.create_time.desc(), CustomPrompt.id.desc())
    ).scalars().all()

    datasource_ids: list[int] = []
    ai_model_ids: list[int] = []
    for row in rows:
        datasource_ids.extend(_normalize_ids(row.datasource_ids))
        ai_model_id = _normalize_ai_model_id(row.ai_model_id)
        if ai_model_id:
            ai_model_ids.append(ai_model_id)
    ds_names = _datasource_name_map(session, list(dict.fromkeys(datasource_ids)))
    ai_model_names = _ai_model_name_map(session, list(dict.fromkeys(ai_model_ids)))
    user_enabled = _user_enabled_map(session, [int(row.id) for row in rows if row.id], current_user_id)

    return [
        _to_info(
            row,
            ds_names,
            ai_model_names,
            current_user_id,
            can_manage_all,
            can_manage_public,
            can_manage_platform_public,
            user_enabled.get(int(row.id), True) if row.id else True,
        )
        for row in rows
    ]


def get_custom_prompt(
        session: SessionDep,
        prompt_id: int,
        current_user_id: Optional[int] = None,
        can_manage_all: bool = False,
        can_manage_public: bool = False,
        can_manage_platform_public: bool = False,
        tenant_id: int | None = None,
) -> CustomPromptInfo:
    """
    是什么：get_custom_prompt 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent需要的数据找出来，整理成后面好用的样子。
    """
    row = session.get(CustomPrompt, prompt_id)
    if not row:
        raise HTTPException(status_code=404, detail="Custom prompt not found")
    visibility_scope = _normalize_visibility_scope(row.visibility_scope)
    public_match = (
        visibility_scope == CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC
        and int(row.tenant_id) == _tenant_id(tenant_id)
    )
    platform_match = visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC
    private_match = (
        visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE
        and _is_owner(row, current_user_id)
    )
    if not public_match and not platform_match and not private_match:
        raise HTTPException(status_code=404, detail="Custom prompt not found")
    if not _row_visible_to_current_user(
        row,
        current_user_id,
        can_manage_all,
        can_manage_public,
        can_manage_platform_public,
    ):
        raise HTTPException(status_code=404, detail="Custom prompt not found")
    ds_names = _datasource_name_map(session, _normalize_ids(row.datasource_ids))
    ai_model_id = _normalize_ai_model_id(row.ai_model_id)
    ai_model_names = _ai_model_name_map(session, [ai_model_id] if ai_model_id else [])
    return _to_info(
        row,
        ds_names,
        ai_model_names,
        current_user_id,
        can_manage_all,
        can_manage_public,
        can_manage_platform_public,
        _user_enabled_map(session, [int(row.id)], current_user_id).get(int(row.id), True) if row.id else True,
    )


def create_custom_prompt(
        session: SessionDep,
        info: CustomPromptInfo,
        current_user_id: Optional[int] = None,
        tenant_id: int | None = None,
) -> int:
    """
    是什么：create_custom_prompt 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存聊天问数据和 Agent需要的东西，让后续流程能继续往下走。
    """
    if not info.name or not info.name.strip():
        raise HTTPException(status_code=400, detail="Prompt name is required")
    if not info.prompt or not info.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt content is required")

    prompt_type = _normalize_type(info.type)
    resolved_tenant_id = _tenant_id(tenant_id if tenant_id is not None else info.tenant_id)
    specific_ds = bool(info.specific_ds)
    datasource_ids = _normalize_ids(info.datasource_ids) if specific_ds else []
    if specific_ds and not datasource_ids:
        raise HTTPException(status_code=400, detail="Datasource is required")
    ai_model_id = _require_ai_model(session, _normalize_ai_model_id(info.ai_model_id))
    target_scope = _normalize_target_scope(info.target_scope)
    _ensure_target_scope_allowed(prompt_type, target_scope)
    visibility_scope = _normalize_visibility_scope(info.visibility_scope)
    platform_tenant_id, specific_ds, datasource_ids = _normalize_platform_generic_scope(
        visibility_scope,
        specific_ds,
        datasource_ids,
    )
    if platform_tenant_id is not None:
        resolved_tenant_id = platform_tenant_id

    exists_query = select(func.count()).select_from(CustomPrompt).where(
        CustomPrompt.type == prompt_type.value,
        CustomPrompt.tenant_id == resolved_tenant_id,
        CustomPrompt.name == info.name.strip(),
        CustomPrompt.id != (info.id or 0),
    )
    if visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC:
        exists_query = exists_query.where(CustomPrompt.visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value)
    elif visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE:
        exists_query = exists_query.where(
            CustomPrompt.visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE.value,
            CustomPrompt.create_by == current_user_id,
        )
    else:
        exists_query = exists_query.where(or_(
            CustomPrompt.visibility_scope == CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC.value,
            CustomPrompt.visibility_scope.is_(None),
        ))
    exists = session.execute(exists_query).scalar()
    if exists:
        raise HTTPException(status_code=400, detail="Prompt name already exists")

    row = CustomPrompt(
        tenant_id=resolved_tenant_id,
        type=prompt_type.value,
        create_time=datetime.datetime.now(),
        name=info.name.strip(),
        description=(info.description or "").strip(),
        target_scope=target_scope.value,
        active=bool(info.active),
        visible=True if info.visible is None else bool(info.visible),
        ai_model_id=ai_model_id,
        create_by=int(current_user_id) if current_user_id is not None else None,
        visibility_scope=visibility_scope.value,
        prompt=info.prompt.strip(),
        specific_ds=specific_ds,
        datasource_ids=datasource_ids,
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    if _mark_skill_embedding_stale_if_needed(row, prompt_type):
        session.add(row)
        session.flush()
        _schedule_skill_embedding_after_commit(session, int(row.id), int(resolved_tenant_id))
    return int(row.id)


def update_custom_prompt(
        session: SessionDep,
        info: CustomPromptInfo,
        current_user_id: Optional[int] = None,
        can_manage_all: bool = False,
        tenant_id: int | None = None,
        can_manage_public: bool = False,
        can_manage_platform_public: bool = False,
) -> int:
    """
    是什么：update_custom_prompt 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent相关的信息改成最新状态，并保存这些变化。
    """
    if not info.id:
        return create_custom_prompt(session, info, current_user_id, tenant_id)
    row = session.get(CustomPrompt, int(info.id))
    resolved_tenant_id = _tenant_id(tenant_id if tenant_id is not None else info.tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="Custom prompt not found")
    visibility_scope = _normalize_visibility_scope(row.visibility_scope)
    public_match = (
        visibility_scope == CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC
        and int(row.tenant_id) == int(resolved_tenant_id)
    )
    platform_match = visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC
    private_match = (
        visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE
        and _is_owner(row, current_user_id)
    )
    if not public_match and not platform_match and not private_match:
        raise HTTPException(status_code=404, detail="Custom prompt not found")
    if current_user_id is not None:
        ensure_custom_prompt_owner(
            row,
            current_user_id,
            can_manage_all,
            can_manage_public,
            can_manage_platform_public,
        )
    if not info.name or not info.name.strip():
        raise HTTPException(status_code=400, detail="Prompt name is required")
    if not info.prompt or not info.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt content is required")

    prompt_type = _normalize_type(info.type or row.type)
    specific_ds = bool(info.specific_ds)
    datasource_ids = _normalize_ids(info.datasource_ids) if specific_ds else []
    if specific_ds and not datasource_ids:
        raise HTTPException(status_code=400, detail="Datasource is required")
    ai_model_id = _require_ai_model(session, _normalize_ai_model_id(info.ai_model_id))
    target_scope = _normalize_target_scope(info.target_scope or row.target_scope)
    _ensure_target_scope_allowed(prompt_type, target_scope)
    visibility_scope = _normalize_visibility_scope(info.visibility_scope or row.visibility_scope)
    platform_tenant_id, specific_ds, datasource_ids = _normalize_platform_generic_scope(
        visibility_scope,
        specific_ds,
        datasource_ids,
    )
    if platform_tenant_id is not None:
        resolved_tenant_id = platform_tenant_id

    exists_query = select(func.count()).select_from(CustomPrompt).where(
        CustomPrompt.type == prompt_type.value,
        CustomPrompt.tenant_id == resolved_tenant_id,
        CustomPrompt.name == info.name.strip(),
        CustomPrompt.id != int(info.id),
    )
    if visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC:
        exists_query = exists_query.where(CustomPrompt.visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value)
    elif visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE:
        exists_query = exists_query.where(
            CustomPrompt.visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE.value,
            CustomPrompt.create_by == row.create_by,
        )
    else:
        exists_query = exists_query.where(or_(
            CustomPrompt.visibility_scope == CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC.value,
            CustomPrompt.visibility_scope.is_(None),
        ))
    exists = session.execute(exists_query).scalar()
    if exists:
        raise HTTPException(status_code=400, detail="Prompt name already exists")

    row.type = prompt_type.value
    row.name = info.name.strip()
    row.description = (info.description or "").strip()
    row.target_scope = target_scope.value
    row.active = bool(info.active)
    if info.visible is not None:
        row.visible = bool(info.visible)
    row.ai_model_id = ai_model_id
    row.tenant_id = resolved_tenant_id
    row.visibility_scope = visibility_scope.value
    row.prompt = info.prompt.strip()
    row.specific_ds = specific_ds
    row.datasource_ids = datasource_ids
    should_refresh_embedding = _mark_skill_embedding_stale_if_needed(row, prompt_type)
    session.add(row)
    session.flush()
    if should_refresh_embedding:
        _schedule_skill_embedding_after_commit(session, int(row.id), int(resolved_tenant_id))
    return int(row.id)


def delete_custom_prompts(
        session: SessionDep,
        ids: list[int],
        current_user_id: Optional[int] = None,
        can_manage_all: bool = False,
        tenant_id: int | None = None,
        can_manage_public: bool = False,
        can_manage_platform_public: bool = False,
):
    """
    是什么：delete_custom_prompts 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent不再需要的数据、缓存或临时内容清理掉。
    """
    normalized_ids = _normalize_ids(ids)
    if not normalized_ids:
        return
    resolved_tenant_id = _tenant_id(tenant_id)
    if current_user_id is not None:
        rows = session.execute(select(CustomPrompt).where(CustomPrompt.id.in_(normalized_ids))).scalars().all()
        if len(rows) != len(set(normalized_ids)):
            raise HTTPException(status_code=404, detail="Custom prompt not found")
        for row in rows:
            visibility_scope = _normalize_visibility_scope(row.visibility_scope)
            public_match = (
                visibility_scope == CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC
                and int(row.tenant_id) == int(resolved_tenant_id)
            )
            platform_match = visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC
            private_match = (
                visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE
                and _is_owner(row, current_user_id)
            )
            if not public_match and not platform_match and not private_match:
                raise HTTPException(status_code=404, detail="Custom prompt not found")
            ensure_custom_prompt_owner(
                row,
                current_user_id,
                can_manage_all,
                can_manage_public,
                can_manage_platform_public,
            )
    delete_conditions = [CustomPrompt.id.in_(normalized_ids)]
    if current_user_id is None:
        delete_conditions.append(CustomPrompt.tenant_id == resolved_tenant_id)
    session.execute(delete(CustomPrompt).where(*delete_conditions))
    session.flush()


def batch_create_custom_prompts(
        session: SessionDep,
        info_list: list[CustomPromptInfo],
        current_user_id: Optional[int] = None,
        tenant_id: int | None = None,
):
    """
    是什么：batch_create_custom_prompts 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    failed_records = []
    success_count = 0
    seen: set[tuple[str, str, str]] = set()

    resolved_tenant_id = _tenant_id(tenant_id)
    datasource_name_to_id = {}
    if resolved_tenant_id == DEFAULT_TENANT_ID:
        datasource_name_to_id = {
            row.name.strip(): int(row.id)
            for row in session.execute(select(CoreDatasource.id, CoreDatasource.name)).all()
            if row.name
        }
    else:
        datasource_id = get_bound_datasource_id_for_tenant(session, resolved_tenant_id)
        if datasource_id is not None:
            datasource_name_to_id = {
                row.name.strip(): int(row.id)
                for row in session.execute(
                    select(CoreDatasource.id, CoreDatasource.name).where(CoreDatasource.id == datasource_id)
                ).all()
                if row.name
            }
    valid_datasource_ids = set(datasource_name_to_id.values())
    if resolved_tenant_id == DEFAULT_TENANT_ID and not valid_datasource_ids:
        datasource_name_to_id = {
            str(row.id): int(row.id)
            for row in session.execute(select(CoreDatasource.id)).all()
            if row.id is not None
        }
        valid_datasource_ids = set(datasource_name_to_id.values())

    for info in info_list:
        try:
            specific_ds = bool(info.specific_ds)
            datasource_ids = _normalize_ids(info.datasource_ids)
            if specific_ds and not datasource_ids and info.datasource_names:
                datasource_ids = [
                    datasource_name_to_id[name.strip()]
                    for name in info.datasource_names
                    if name and name.strip() in datasource_name_to_id
                ]
            invalid_datasource_ids = [item for item in datasource_ids if int(item) not in valid_datasource_ids]
            if invalid_datasource_ids:
                raise HTTPException(status_code=400, detail="Datasource is not in current tenant")
            if specific_ds and not datasource_ids:
                raise HTTPException(status_code=400, detail="Datasource is required")
            info.datasource_ids = datasource_ids

            key = (
                str(_normalize_type(info.type).value),
                (info.name or "").strip().lower(),
                ",".join(str(item) for item in sorted(datasource_ids)) if specific_ds else "all",
            )
            if key in seen:
                raise HTTPException(status_code=400, detail="Duplicate prompt in import file")
            seen.add(key)
            info.tenant_id = info.tenant_id or resolved_tenant_id
            create_custom_prompt(session, info, current_user_id, resolved_tenant_id)
            session.commit()
            success_count += 1
        except Exception as exc:
            failed_records.append({"data": info, "errors": [getattr(exc, "detail", str(exc))]})
            session.rollback()

    return {
        "success_count": success_count,
        "failed_records": failed_records,
        "duplicate_count": 0,
        "original_count": len(info_list),
    }
