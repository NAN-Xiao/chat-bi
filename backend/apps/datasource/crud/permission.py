"""
脚本说明：这个脚本封装数据源的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
import datetime
import json
from typing import Any, List, Optional

from sqlalchemy import and_, inspect
from sqlmodel import func, select

from apps.datasource.crud.permission_rules import (
    list_permission_records,
    list_rule_records,
    parse_json_list,
    trans_record_to_dto,
)
from apps.datasource.crud.row_permission import transFilterTree
from apps.datasource.crud.binding import datasource_tenant_binding_active
from apps.datasource.models.datasource import CoreDatasource, CoreDatasourceTenantBinding, CoreDatasourceUser, CoreField, CoreTable
from apps.system.models.tenant import TenantUserModel
from common.core.deps import CurrentUser, SessionDep
from apps.system.crud.user import (
    SYSTEM_ADMIN_ROLES,
    is_system_admin,
)
from apps.system.models.user import UserModel
from apps.system.schemas.access_context import (
    current_tenant_id,
    has_workspace_context,
    is_global_platform_context,
    can_manage_workspace_scope,
)

PROJECT_ROLE_VIEWER = "viewer"
PROJECT_ROLE_EDITOR = "editor"
PROJECT_ROLE_ORDER = {
    PROJECT_ROLE_VIEWER: 10,
    PROJECT_ROLE_EDITOR: 20,
}
PROJECT_ROLE_ALIASES = {
    "project_viewer": PROJECT_ROLE_VIEWER,
    "project_editor": PROJECT_ROLE_EDITOR,
    "project_admin": PROJECT_ROLE_EDITOR,
    "admin": PROJECT_ROLE_EDITOR,
}
REQUIRED_PROJECT_ROLE_ALIASES = {
    "project_viewer": PROJECT_ROLE_VIEWER,
    "project_editor": PROJECT_ROLE_EDITOR,
}


def _supports_table(session: SessionDep, table_name: str) -> bool:
    """
    是什么：_supports_table 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        return inspect(session.connection()).has_table(table_name)
    except Exception:
        return False


def _supports_datasource_tenant_filter(session: SessionDep) -> bool:
    """
    是什么：_supports_datasource_tenant_filter 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        inspector = inspect(session.connection())
        if not inspector.has_table(CoreDatasource.__tablename__):
            return False
        return any(
            column["name"] == "tenant_id"
            for column in inspector.get_columns(CoreDatasource.__tablename__)
        )
    except Exception:
        return False


def _supports_tenant_user_filter(session: SessionDep) -> bool:
    """
    是什么：_supports_tenant_user_filter 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return _supports_table(session, TenantUserModel.__tablename__)


def _apply_datasource_tenant_filter(statement, session: SessionDep, current_user: CurrentUser | None):
    """
    是什么：_apply_datasource_tenant_filter 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if is_global_platform_context(current_user):
        return statement
    if not has_workspace_context(current_user):
        return statement.where(False)
    tenant_id = current_tenant_id(current_user)
    if tenant_id is None:
        return statement
    if datasource_tenant_binding_active(session):
        bound_datasource_ids = select(CoreDatasourceTenantBinding.datasource_id).where(
            CoreDatasourceTenantBinding.tenant_id == int(tenant_id)
        )
        return statement.where(CoreDatasource.id.in_(bound_datasource_ids))
    if not _supports_datasource_tenant_filter(session):
        return statement
    return statement.where(CoreDatasource.tenant_id == tenant_id)


def _datasource_in_current_tenant(session: SessionDep, datasource_id: int, current_user: CurrentUser | None) -> bool:
    """
    是什么：_datasource_in_current_tenant 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    statement = select(CoreDatasource.id).where(CoreDatasource.id == datasource_id)
    statement = _apply_datasource_tenant_filter(statement, session, current_user)
    return session.exec(statement).first() is not None


def normalize_project_role(role: str | None) -> str:
    """
    是什么：normalize_project_role 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if not role:
        return PROJECT_ROLE_VIEWER
    normalized = PROJECT_ROLE_ALIASES.get(str(role).strip().lower(), str(role).strip().lower())
    return normalized if normalized in PROJECT_ROLE_ORDER else PROJECT_ROLE_VIEWER


def project_role_rank(role: str | None) -> int:
    """
    是什么：project_role_rank 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return PROJECT_ROLE_ORDER.get(normalize_project_role(role), 0)


def required_project_role_rank(role: str | None) -> int:
    """
    是什么：required_project_role_rank 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if not role:
        return PROJECT_ROLE_ORDER[PROJECT_ROLE_VIEWER]
    normalized = REQUIRED_PROJECT_ROLE_ALIASES.get(str(role).strip().lower(), str(role).strip().lower())
    return PROJECT_ROLE_ORDER.get(normalized, 0)


def _can_satisfy_project_role(actual_role: str | None, required_role: str | None) -> bool:
    """
    是什么：_can_satisfy_project_role 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if actual_role is None:
        return False
    required_rank = required_project_role_rank(required_role)
    if required_rank <= 0:
        return False
    return project_role_rank(actual_role) >= required_rank


def _supports_user_system_role_filter(session: SessionDep) -> bool:
    """
    是什么：_supports_user_system_role_filter 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        inspector = inspect(session.connection())
        if not inspector.has_table(UserModel.__tablename__):
            return False
        return any(
            column["name"] == "system_role"
            for column in inspector.get_columns(UserModel.__tablename__)
        )
    except Exception:
        return False


def list_project_assignable_user_ids(
        session: SessionDep,
        user_ids,
        current_user: CurrentUser | None = None,
) -> set[int]:
    """
    是什么：list_project_assignable_user_ids 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    requested_ids = {int(user_id) for user_id in user_ids if user_id is not None}
    if not requested_ids:
        return set()
    statement = select(UserModel.id).where(UserModel.id.in_(requested_ids))
    if _supports_user_system_role_filter(session):
        statement = statement.where(UserModel.system_role.not_in(SYSTEM_ADMIN_ROLES))

    tenant_id = current_tenant_id(current_user)
    if (
        not is_global_platform_context(current_user)
        and _supports_tenant_user_filter(session)
    ):
        if not has_workspace_context(current_user) or tenant_id is None:
            return set()
        statement = statement.join(TenantUserModel, TenantUserModel.user_id == UserModel.id).where(
            TenantUserModel.tenant_id == tenant_id,
            TenantUserModel.status == 1,
        )

    if not _supports_user_system_role_filter(session) and not _supports_tenant_user_filter(session):
        return requested_ids

    rows = session.exec(statement).all()
    return {int(_first_column_value(row)) for row in rows if _first_column_value(row) is not None}


def list_datasource_user_ids(
        session: SessionDep,
        datasource_id: int,
        current_user: CurrentUser | None = None,
) -> list[int]:
    """
    是什么：list_datasource_user_ids 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if not _datasource_in_current_tenant(session, int(datasource_id), current_user):
        return []
    rows = session.query(CoreDatasourceUser).filter(CoreDatasourceUser.ds_id == datasource_id).all()
    assignable_ids = list_project_assignable_user_ids(session, [row.user_id for row in rows], current_user)
    return [int(row.user_id) for row in rows if int(row.user_id) in assignable_ids]


def list_datasource_users(
        session: SessionDep,
        datasource_id: int,
        current_user: CurrentUser | None = None,
) -> list[dict[str, Any]]:
    """
    是什么：list_datasource_users 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if not _datasource_in_current_tenant(session, int(datasource_id), current_user):
        return []
    rows = session.query(CoreDatasourceUser).filter(CoreDatasourceUser.ds_id == datasource_id).all()
    assignable_ids = list_project_assignable_user_ids(session, [row.user_id for row in rows], current_user)
    return [
        {
            "user_id": int(row.user_id),
            "role": normalize_project_role(getattr(row, "role", None)),
        }
        for row in rows
        if int(row.user_id) in assignable_ids
    ]


def list_datasource_user_counts(
        session: SessionDep,
        datasource_ids,
        current_user: CurrentUser | None = None,
) -> dict[int, int]:
    """
    是什么：list_datasource_user_counts 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    requested_ids = {int(datasource_id) for datasource_id in datasource_ids if datasource_id is not None}
    if not requested_ids:
        return {}

    statement = (
        select(CoreDatasourceUser.ds_id, func.count(CoreDatasourceUser.user_id))
        .join(CoreDatasource, CoreDatasource.id == CoreDatasourceUser.ds_id)
        .where(CoreDatasourceUser.ds_id.in_(requested_ids))
        .group_by(CoreDatasourceUser.ds_id)
    )
    statement = _apply_datasource_tenant_filter(statement, session, current_user)
    if _supports_user_system_role_filter(session):
        statement = (
            statement.join(UserModel, UserModel.id == CoreDatasourceUser.user_id)
            .where(UserModel.system_role.not_in(SYSTEM_ADMIN_ROLES))
        )
    tenant_id = current_tenant_id(current_user)
    if (
        not is_global_platform_context(current_user)
        and _supports_tenant_user_filter(session)
    ):
        if not has_workspace_context(current_user) or tenant_id is None:
            return {}
        statement = (
            statement.join(TenantUserModel, TenantUserModel.user_id == CoreDatasourceUser.user_id)
            .where(
                TenantUserModel.tenant_id == tenant_id,
                TenantUserModel.status == 1,
            )
        )

    rows = session.exec(statement).all()
    return {
        int(_first_column_value(row)): int(row[1])
        for row in rows
        if _first_column_value(row) is not None
    }


def list_user_datasource_ids(
        session: SessionDep,
        user_id: int,
        current_user: CurrentUser | None = None,
) -> list[int]:
    """
    是什么：list_user_datasource_ids 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    statement = (
        select(CoreDatasourceUser.ds_id)
        .join(CoreDatasource, CoreDatasource.id == CoreDatasourceUser.ds_id)
        .where(CoreDatasourceUser.user_id == user_id)
        .order_by(CoreDatasourceUser.ds_id)
    )
    statement = _apply_datasource_tenant_filter(statement, session, current_user)
    rows = session.exec(statement).all()
    return [int(_first_column_value(row)) for row in rows if _first_column_value(row) is not None]


def list_user_datasource_roles(
        session: SessionDep,
        user_id: int,
        current_user: CurrentUser | None = None,
) -> dict[int, str]:
    """
    是什么：list_user_datasource_roles 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    statement = (
        select(CoreDatasourceUser.ds_id, CoreDatasourceUser.role)
        .join(CoreDatasource, CoreDatasource.id == CoreDatasourceUser.ds_id)
        .where(CoreDatasourceUser.user_id == user_id)
        .order_by(CoreDatasourceUser.ds_id)
    )
    statement = _apply_datasource_tenant_filter(statement, session, current_user)
    rows = session.exec(statement).all()
    return {int(row[0]): normalize_project_role(row[1]) for row in rows}


def get_datasource_ids_with_min_role(
        session: SessionDep,
        current_user: CurrentUser,
        min_role: str = PROJECT_ROLE_VIEWER,
) -> Optional[set[int]]:
    """
    是什么：get_datasource_ids_with_min_role 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    required_rank = required_project_role_rank(min_role)
    if required_rank <= 0:
        return set()

    if _is_datasource_scope_admin(current_user):
        statement = select(CoreDatasource.id).order_by(CoreDatasource.id)
        statement = _apply_datasource_tenant_filter(statement, session, current_user)
        rows = session.exec(statement).all()
        return {int(_first_column_value(row)) for row in rows if _first_column_value(row) is not None}

    if required_rank <= PROJECT_ROLE_ORDER[PROJECT_ROLE_VIEWER]:
        statement = select(CoreDatasource.id).order_by(CoreDatasource.id)
        statement = _apply_datasource_tenant_filter(statement, session, current_user)
        rows = session.exec(statement).all()
        return {int(_first_column_value(row)) for row in rows if _first_column_value(row) is not None}

    result: set[int] = set()

    statement = (
        select(CoreDatasourceUser)
        .join(CoreDatasource, CoreDatasource.id == CoreDatasourceUser.ds_id)
        .where(CoreDatasourceUser.user_id == current_user.id)
    )
    statement = _apply_datasource_tenant_filter(statement, session, current_user)
    membership_rows = session.exec(statement).all()
    for row in membership_rows:
        if project_role_rank(getattr(row, "role", None)) >= required_rank:
            result.add(int(row.ds_id))

    return result


def update_datasource_users(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
        user_ids: list[int],
        user_roles: Optional[dict[int, str]] = None
) -> list[dict[str, Any]]:
    """
    是什么：update_datasource_users 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    user_roles = user_roles or {}
    if not _datasource_in_current_tenant(session, int(datasource.id), current_user):
        return []
    next_user_ids = list_project_assignable_user_ids(session, user_ids, current_user)
    current_rows = session.query(CoreDatasourceUser).filter(CoreDatasourceUser.ds_id == datasource.id).all()
    current_rows_by_user = {int(row.user_id): row for row in current_rows}

    for row in current_rows:
        if int(row.user_id) not in next_user_ids:
            session.delete(row)

    for user_id in next_user_ids:
        next_role = normalize_project_role(user_roles.get(user_id))
        row = current_rows_by_user.get(user_id)
        if row:
            row.role = next_role
            session.add(row)
        else:
            session.add(CoreDatasourceUser(
                ds_id=datasource.id,
                user_id=user_id,
                role=next_role,
                create_by=current_user.id,
                create_time=datetime.datetime.now()
            ))

    session.flush()
    return [
        {"user_id": user_id, "role": normalize_project_role(user_roles.get(user_id))}
        for user_id in sorted(next_user_ids)
    ]


def update_user_datasources(
        session: SessionDep,
        current_user: CurrentUser,
        user_id: int,
        datasource_ids: list[int],
        datasource_roles: Optional[dict[int, str]] = None,
) -> list[int]:
    """
    是什么：update_user_datasources 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    try:
        target_user_id = int(user_id)
    except (TypeError, ValueError):
        return []
    if target_user_id not in list_project_assignable_user_ids(session, [target_user_id], current_user):
        return []

    next_datasource_ids = {int(datasource_id) for datasource_id in datasource_ids}
    if next_datasource_ids:
        statement = select(CoreDatasource).where(CoreDatasource.id.in_(next_datasource_ids))
        statement = _apply_datasource_tenant_filter(statement, session, current_user)
        existing_datasources = session.exec(statement).all()
        datasource_map = {int(datasource.id): datasource for datasource in existing_datasources}
        next_datasource_ids = set(datasource_map.keys())
    else:
        datasource_map = {}

    should_update_roles = datasource_roles is not None
    datasource_roles = datasource_roles or {}
    normalized_roles = {}
    for datasource_id, role in datasource_roles.items():
        try:
            normalized_roles[int(datasource_id)] = normalize_project_role(role)
        except (TypeError, ValueError):
            continue

    current_rows = session.exec(
        select(CoreDatasourceUser)
        .join(CoreDatasource, CoreDatasource.id == CoreDatasourceUser.ds_id)
        .where(CoreDatasourceUser.user_id == target_user_id)
    ).all()
    current_rows = [
        row for row in current_rows
        if _datasource_in_current_tenant(session, int(row.ds_id), current_user)
    ]
    current_datasource_ids = {int(row.ds_id) for row in current_rows}

    for row in current_rows:
        datasource_id = int(row.ds_id)
        if datasource_id not in next_datasource_ids:
            session.delete(row)
        elif should_update_roles:
            row.role = normalized_roles.get(datasource_id, PROJECT_ROLE_VIEWER)
            session.add(row)

    add_datasource_ids = next_datasource_ids - current_datasource_ids
    for datasource_id in add_datasource_ids:
        session.add(CoreDatasourceUser(
            ds_id=datasource_id,
            user_id=target_user_id,
            role=normalized_roles.get(datasource_id, PROJECT_ROLE_VIEWER),
            create_by=current_user.id if current_user else None,
            create_time=datetime.datetime.now()
        ))

    session.flush()
    return sorted(next_datasource_ids)


JS_SAFE_INTEGER_MAX = 9007199254740991


def _id_text(value) -> str:
    """
    是什么：_id_text 把 ID 统一转成字符串，避免 64 位 ID 在前端数字化后丢精度。
    谁调用：权限规则匹配用户、白名单或权限 ID 时会调用它。
    做了什么：保留原始字符串形态，兼容少量历史数据里的整数/浮点写法。
    """
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _same_id(left, right, *, allow_js_number_alias: bool = False) -> bool:
    """
    是什么：_same_id 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    left_text = _id_text(left)
    right_text = _id_text(right)
    if left_text == right_text:
        return True
    if not allow_js_number_alias:
        return False
    try:
        left_int = int(left_text)
        right_int = int(right_text)
    except (TypeError, ValueError):
        return False
    if abs(left_int) <= JS_SAFE_INTEGER_MAX or abs(right_int) <= JS_SAFE_INTEGER_MAX:
        return False
    return float(left_int) == float(right_int)


def _rule_contains_user(rule: Any, current_user: CurrentUser) -> bool:
    """
    是什么：_rule_contains_user 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return any(
        _same_id(user_id, current_user.id, allow_js_number_alias=True)
        for user_id in parse_json_list(rule.user_list)
    )


def _rule_whitelists_user(rule: Any, current_user: CurrentUser) -> bool:
    """
    是什么：_rule_whitelists_user 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return any(_same_id(user_id, current_user.id) for user_id in parse_json_list(getattr(rule, "white_list_user", None)))


def _permission_whitelists_user(permission: Any, current_user: CurrentUser) -> bool:
    """
    是什么：_permission_whitelists_user 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return any(
        _same_id(user_id, current_user.id)
        for user_id in parse_json_list(getattr(permission, "white_list_user", None))
    )


def _rule_contains_permission(rule: Any, permission_id) -> bool:
    """
    是什么：_rule_contains_permission 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return any(_same_id(item, permission_id) for item in parse_json_list(rule.permission_list))


def _is_datasource_scope_admin(current_user: CurrentUser) -> bool:
    """
    是什么：_is_datasource_scope_admin 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return is_system_admin(current_user) or can_manage_workspace_scope(current_user)


def _first_column_value(row):
    """
    是什么：_first_column_value 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if isinstance(row, tuple):
        return row[0]
    try:
        return row[0]
    except (TypeError, KeyError, IndexError):
        return row


def get_datasource_role(session: SessionDep, current_user: CurrentUser, datasource_id) -> str | None:
    """
    是什么：get_datasource_role 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if datasource_id is None or datasource_id == "":
        return None
    try:
        datasource_id = int(datasource_id)
    except (TypeError, ValueError):
        return None
    if not _datasource_in_current_tenant(session, datasource_id, current_user):
        return None
    if _is_datasource_scope_admin(current_user):
        return PROJECT_ROLE_EDITOR

    row = session.query(CoreDatasourceUser).filter(
        CoreDatasourceUser.ds_id == datasource_id,
        CoreDatasourceUser.user_id == current_user.id,
    ).first()
    if row is not None:
        return normalize_project_role(getattr(row, "role", None))
    return PROJECT_ROLE_VIEWER if has_workspace_context(current_user) else None


def has_datasource_role(
        session: SessionDep,
        current_user: CurrentUser,
        datasource_ids,
        min_role: str = PROJECT_ROLE_VIEWER
) -> bool:
    """
    是什么：has_datasource_role 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if datasource_ids is None or datasource_ids == "":
        return False

    if isinstance(datasource_ids, list):
        requested_ids = datasource_ids
    else:
        requested_ids = [datasource_ids]

    try:
        requested_set = {int(datasource_id) for datasource_id in requested_ids}
    except (TypeError, ValueError):
        return False

    return all(
        _can_satisfy_project_role(get_datasource_role(session, current_user, datasource_id), min_role)
        for datasource_id in requested_set
    )


def get_accessible_datasource_ids(session: SessionDep, current_user: CurrentUser) -> Optional[set[int]]:
    """
    是什么：get_accessible_datasource_ids 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    return get_datasource_ids_with_min_role(session, current_user, PROJECT_ROLE_VIEWER)


def has_datasource_access(session: SessionDep, current_user: CurrentUser, datasource_ids) -> bool:
    """
    是什么：has_datasource_access 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if datasource_ids is None or datasource_ids == "":
        return True

    return has_datasource_role(session, current_user, datasource_ids, PROJECT_ROLE_VIEWER)


def get_row_permission_filters(session: SessionDep, current_user: CurrentUser, ds: CoreDatasource,
                               tables: Optional[list] = None, single_table: Optional[CoreTable] = None):
    """
    是什么：get_row_permission_filters 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if single_table:
        table_list = [session.get(CoreTable, single_table.id)]
    elif tables is None:
        table_list = session.query(CoreTable).filter(CoreTable.ds_id == ds.id).all()
    else:
        table_list = session.query(CoreTable).filter(
            and_(CoreTable.ds_id == ds.id, CoreTable.table_name.in_(tables))
        ).all()

    filters = []
    if is_normal_user(current_user):
        contain_rules = get_user_permission_rules(session, current_user, ds.id)
        for table in table_list:
            if table is None:
                continue
            row_permissions = list_permission_records(
                session,
                ds_id=ds.id,
                table_id=table.id,
                permission_type='row',
                enable=True,
            )
            res: List[Any] = []
            if row_permissions is not None:
                for permission in row_permissions:
                    if _permission_whitelists_user(permission, current_user):
                        continue
                    # 检查权限与用户是否位于同一规则中
                    flag = False
                    for r in contain_rules:
                        if _rule_contains_permission(r, permission.id) and _rule_contains_user(r, current_user):
                            flag = True
                            break
                    if flag:
                        res.append(trans_record_to_dto(session, permission))
            if not res:
                continue
            where_str = transFilterTree(session, current_user, res, ds, deny_mode=True, strict=True)
            if not where_str:
                raise ValueError("行权限过滤条件未生成有效限制")
            filters.append({"table": table.table_name, "filter": where_str})
    return filters


def _permission_applies_to_user(permission: Any, contain_rules: list[Any], current_user: CurrentUser) -> bool:
    """
    是什么：_permission_applies_to_user 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if _permission_whitelists_user(permission, current_user):
        return False
    for rule in contain_rules:
        if _rule_contains_permission(rule, permission.id) and _rule_contains_user(rule, current_user):
            return True
    return False


def has_applicable_row_permissions(
        session: SessionDep,
        current_user: CurrentUser,
        ds: CoreDatasource,
        tables: Optional[list] = None,
        single_table: Optional[CoreTable] = None,
) -> bool:
    """
    是什么：has_applicable_row_permissions 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not is_normal_user(current_user):
        return False
    if single_table:
        table_list = [session.get(CoreTable, single_table.id)]
    else:
        table_list = session.query(CoreTable).filter(
            and_(CoreTable.ds_id == ds.id, CoreTable.table_name.in_(tables or []))
        ).all()
    if not table_list:
        return False

    contain_rules = get_user_permission_rules(session, current_user, ds.id)
    if not contain_rules:
        return False
    for table in table_list:
        if table is None:
            continue
        row_permissions = list_permission_records(
            session,
            ds_id=ds.id,
            table_id=table.id,
            permission_type='row',
            enable=True,
        )
        for permission in row_permissions or []:
            if _permission_applies_to_user(permission, contain_rules, current_user):
                return True
    return False


def has_applicable_permissions(
        session: SessionDep,
        current_user: CurrentUser,
        ds: CoreDatasource,
        tables: Optional[list] = None,
        single_table: Optional[CoreTable] = None,
        permission_types: Optional[list[str]] = None,
) -> bool:
    """
    是什么：has_applicable_permissions 判断当前用户是否命中某个数据源范围内的任意权限规则。
    谁调用：缓存、快照、历史记录等复用旧结果的入口会调用它。
    做了什么：只要涉及表上存在对当前用户生效的表、字段或行权限，就认为旧结果不可信。
    """
    if not is_normal_user(current_user):
        return False
    if single_table:
        table_list = [session.get(CoreTable, single_table.id)]
    elif tables is None:
        table_list = session.query(CoreTable).filter(CoreTable.ds_id == ds.id).all()
    else:
        table_list = session.query(CoreTable).filter(
            and_(CoreTable.ds_id == ds.id, CoreTable.table_name.in_(tables or []))
        ).all()
    if not table_list:
        return False

    contain_rules = get_user_permission_rules(session, current_user, ds.id)
    if not contain_rules:
        return False
    types = permission_types or ["table", "column", "row"]
    for table in table_list:
        if table is None:
            continue
        for permission_type in types:
            permissions = list_permission_records(
                session,
                ds_id=ds.id,
                table_id=table.id,
                permission_type=permission_type,
                enable=True,
            )
            for permission in permissions or []:
                if _permission_applies_to_user(permission, contain_rules, current_user):
                    return True
    return False


def get_column_permission_fields(session: SessionDep, current_user: CurrentUser, table: CoreTable,
                                 fields: list[CoreField], contain_rules: list[Any]):
    """
    是什么：get_column_permission_fields 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if is_normal_user(current_user):
        column_permissions = list_permission_records(
            session,
            ds_id=table.ds_id,
            table_id=table.id,
            permission_type='column',
            enable=True,
        )
        if column_permissions is not None:
            for permission in column_permissions:
                if _permission_applies_to_user(permission, contain_rules, current_user):
                    try:
                        permission_list = json.loads(permission.permissions or "[]")
                    except Exception as exc:
                        raise ValueError("字段权限配置格式无效") from exc
                    if not isinstance(permission_list, list):
                        raise ValueError("字段权限配置格式无效")
                    fields = filter_list(fields, permission_list)
    return fields


def is_normal_user(current_user: CurrentUser):
    """
    是什么：is_normal_user 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return not _is_datasource_scope_admin(current_user)


def get_user_permission_rules(
        session: SessionDep,
        current_user: CurrentUser,
        datasource_id: Optional[int] = None
) -> list[Any]:
    """
    是什么：get_user_permission_rules 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if not is_normal_user(current_user):
        return []

    rules = list_rule_records(
        session,
        enable=True,
        tenant_id=current_tenant_id(current_user),
        include_platform=True,
    )

    if datasource_id is None:
        return [
            rule for rule in rules
            if _rule_contains_user(rule, current_user) and not _rule_whitelists_user(rule, current_user)
        ]

    permission_ids = {
        int(permission.id) for permission in list_permission_records(
            session,
            ds_id=datasource_id,
            enable=True,
        )
    }
    if not permission_ids:
        return []

    user_rules = []
    for rule in rules:
        if not _rule_contains_user(rule, current_user):
            continue
        if _rule_whitelists_user(rule, current_user):
            continue
        rule_permission_ids = set()
        for permission_id in parse_json_list(rule.permission_list):
            try:
                rule_permission_ids.add(int(permission_id))
            except (TypeError, ValueError):
                continue
        if rule_permission_ids & permission_ids:
            user_rules.append(rule)
    return user_rules


def get_user_scoped_table_ids(
        session: SessionDep,
        current_user: CurrentUser,
        datasource_id: int,
        contain_rules: Optional[list[Any]] = None,
) -> Optional[set[int]]:
    """
    是什么：get_user_scoped_table_ids 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if not is_normal_user(current_user):
        return None

    checked_table_ids = {
        int(_first_column_value(row))
        for row in session.query(CoreTable.id).filter(
            CoreTable.ds_id == datasource_id,
            CoreTable.checked == True,
        ).all()
        if _first_column_value(row) is not None
    }
    contain_rules = contain_rules if contain_rules is not None else get_user_permission_rules(
        session,
        current_user,
        datasource_id,
    )
    if not contain_rules:
        return checked_table_ids

    rule_permission_ids: set[int] = set()
    for rule in contain_rules:
        if not _rule_contains_user(rule, current_user):
            continue
        for permission_id in parse_json_list(rule.permission_list):
            try:
                rule_permission_ids.add(int(permission_id))
            except (TypeError, ValueError):
                continue
    if not rule_permission_ids:
        return checked_table_ids

    permissions = list_permission_records(
        session,
        ids=sorted(rule_permission_ids),
        ds_id=datasource_id,
        permission_type='table',
        enable=True,
    )
    denied_table_ids = {
        int(permission.table_id)
        for permission in permissions
        if permission.table_id is not None and not _permission_whitelists_user(permission, current_user)
    }
    return checked_table_ids - denied_table_ids


def can_access_table(
        session: SessionDep,
        current_user: CurrentUser,
        datasource_id: int,
        table_id: int,
        contain_rules: Optional[list[Any]] = None,
) -> bool:
    """
    是什么：can_access_table 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    scoped_table_ids = get_user_scoped_table_ids(session, current_user, datasource_id, contain_rules)
    return scoped_table_ids is None or int(table_id) in scoped_table_ids


def filter_list(list_a, list_b):
    """
    是什么：filter_list 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    id_to_invalid = {}
    for b in list_b:
        if not isinstance(b, dict) or 'field_id' not in b or 'enable' not in b:
            raise ValueError("字段权限配置格式无效")
        if not b['enable']:
            id_to_invalid[str(b['field_id'])] = True

    return [a for a in list_a if not id_to_invalid.get(str(a.id), False)]
