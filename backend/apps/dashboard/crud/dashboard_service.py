from typing import Any

from collections import OrderedDict
import copy
import hashlib
import json
from threading import BoundedSemaphore, Lock

from fastapi import HTTPException
from orjson import orjson
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import String, case, cast, select, and_, or_, text, func, inspect

from apps.dashboard.models.dashboard_model import (
    CoreDashboard,
    CoreDashboardShare,
    CreateDashboard,
    QueryDashboard,
    DashboardBaseResponse,
    DashboardDefaultCopyRequest,
    DashboardDefaultRequest,
    DashboardDefaultSortRequest,
    DashboardReorderRequest,
    DashboardSqlPreview,
    DashboardShareRequest,
    DashboardShareListQuery,
    SharedDashboardQuery,
    SharedDashboardUseRequest,
)
from apps.datasource.crud.permission import (
    PROJECT_ROLE_EDITOR,
    get_accessible_datasource_ids,
    has_datasource_access,
    has_datasource_role,
    is_normal_user,
)
from apps.datasource.crud.binding import datasource_bound_to_tenant
from apps.datasource.crud.binding import get_bound_datasource_id_for_tenant
from apps.datasource.crud.query_executor import execute_user_query
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import get_sqlglot_dialect
from apps.system.schemas.access_context import can_manage_workspace_scope, require_current_tenant_id
from apps.system.models.user import UserModel
from apps.system.models.tenant import TenantUserModel
from apps.system.crud.tenant import TENANT_ROLE_ADMIN, TENANT_ROLE_OWNER
from apps.system.crud.user import is_platform_workspace_delegate, is_system_admin
from common.core.config import settings
from common.core.redis_client import build_redis_url, redis_key
from common.core.deps import SessionDep, CurrentUser
from common.utils.chart_config import sanitize_chart_display_names
from common.utils.utils import AppLogUtil
import uuid
import time
import re

from common.utils.tree_utils import build_tree_generic


def _first_scalar_value(value: Any):
    if value is None:
        return None
    if hasattr(value, "_mapping"):
        values = list(value._mapping.values())
        return values[0] if values else None
    if isinstance(value, (tuple, list)):
        return value[0] if value else None
    return value


def _dashboard_chart_has_materialized_result(item: dict) -> bool:
    data_obj = item.get('data') if isinstance(item.get('data'), dict) else {}
    rows = data_obj.get('data')
    data_fields = data_obj.get('fields')
    item_fields = item.get('fields')
    return (
        (isinstance(rows, list) and len(rows) > 0)
        or (isinstance(data_fields, list) and len(data_fields) > 0)
        or (isinstance(item_fields, list) and len(item_fields) > 0)
    )


def _normalize_persisted_dashboard_chart_state(canvas_view_obj: dict) -> dict:
    for item in canvas_view_obj.values():
        if not isinstance(item, dict):
            continue
        if item.get('dataState') != 'loading' and item.get('status') != 'loading':
            continue
        if not _dashboard_chart_has_materialized_result(item):
            continue
        if item.get('status') == 'loading':
            item['status'] = 'success'
        item['dataState'] = 'failed' if item.get('status') == 'failed' else 'ready'
        item['loadingProgress'] = 100
    return canvas_view_obj


def _sanitize_canvas_view_info(canvas_view_info: str | bytes | None) -> str | bytes | None:
    if not canvas_view_info:
        return canvas_view_info
    try:
        canvas_view_obj = orjson.loads(canvas_view_info)
    except Exception:
        return canvas_view_info
    canvas_view_obj = sanitize_chart_display_names(canvas_view_obj)
    if isinstance(canvas_view_obj, dict):
        canvas_view_obj = _normalize_persisted_dashboard_chart_state(canvas_view_obj)
    return orjson.dumps(canvas_view_obj).decode()


def _user_id(current_user: CurrentUser) -> str:
    return str(current_user.id)


def _now() -> int:
    return int(time.time())


def _smallint_flag(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    return 1 if bool(value) else 0


DEFAULT_TENANT_ID = 1
DASHBOARD_STATUS_ACTIVE = 1
DASHBOARD_STATUS_DELIVERY_DRAFT = 2
DASHBOARD_DRAFT_STATUSES = {
    DASHBOARD_STATUS_DELIVERY_DRAFT,
    3,
}
DASHBOARD_SOURCE_PLATFORM_DELEGATE = "platform_delegate"
DASHBOARD_SOURCE_PLATFORM_TEMPLATE = "platform_template"
DASHBOARD_SQL_PREVIEW_BUSY_MESSAGE = "当前看板查询较多，请稍后刷新"
DASHBOARD_REFRESH_POLICY_DEFAULT = {
    "auto_refresh": True,
    "snapshot_max_age_hours": 3,
}
DASHBOARD_REFRESH_POLICY_PATTERN = re.compile(
    r"<!--\s*dashboard-refresh-policy\s*:\s*(.*?)\s*-->",
    re.DOTALL | re.IGNORECASE,
)
CUSTOM_PROMPT_TYPE_DATA_SKILL = "DATA_SKILL"
CUSTOM_PROMPT_SCOPE_PLATFORM_PUBLIC = "PLATFORM_PUBLIC"
CUSTOM_PROMPT_SCOPE_ADMIN_PUBLIC = "ADMIN_PUBLIC"
CUSTOM_PROMPT_SCOPE_USER_PRIVATE = "USER_PRIVATE"

_DASHBOARD_SQL_PREVIEW_CACHE: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
_DASHBOARD_SQL_PREVIEW_CACHE_LOCK = Lock()
_DASHBOARD_SQL_PREVIEW_INFLIGHT_LOCKS: dict[str, Lock] = {}
_DASHBOARD_SQL_PREVIEW_INFLIGHT_LOCKS_LOCK = Lock()
_DASHBOARD_SQL_PREVIEW_DATASOURCE_SEMAPHORES: dict[int, BoundedSemaphore] = {}
_DASHBOARD_SQL_PREVIEW_DATASOURCE_SEMAPHORES_LOCK = Lock()
_DASHBOARD_SQL_PREVIEW_REDIS_CLIENT: Redis | None = None
_DASHBOARD_SQL_PREVIEW_REDIS_CLIENT_LOCK = Lock()
_DASHBOARD_SQL_PREVIEW_REDIS_WARNING_LOGGED = False
_DASHBOARD_SQL_PREVIEW_REDIS_DISABLED_UNTIL = 0.0


def _current_tenant_id(current_user: CurrentUser | None) -> int:
    return require_current_tenant_id(current_user)


def _same_tenant(current_user: CurrentUser | None, record) -> bool:
    return int(getattr(record, "tenant_id")) == _current_tenant_id(current_user)


def _workspace_admin_user_ids(session: SessionDep, current_user: CurrentUser) -> set[str]:
    try:
        rows = session.exec(
            select(TenantUserModel.user_id).where(
                and_(
                    TenantUserModel.tenant_id == _current_tenant_id(current_user),
                    TenantUserModel.status == 1,
                    TenantUserModel.role.in_([TENANT_ROLE_OWNER, TENANT_ROLE_ADMIN]),
                )
            )
        ).all()
    except Exception:
        return set()
    return {str(_first_scalar_value(row)) for row in rows if _first_scalar_value(row) is not None}


def _workspace_delegate_asset_owner_id(session: SessionDep, current_user: CurrentUser) -> str:
    if not is_platform_workspace_delegate(current_user):
        return _user_id(current_user)
    tenant_id = _current_tenant_id(current_user)
    current_user_id = _user_id(current_user)
    role_priority = case(
        (TenantUserModel.role == TENANT_ROLE_OWNER, 0),
        (TenantUserModel.role == TENANT_ROLE_ADMIN, 1),
        else_=2,
    )
    try:
        row = session.exec(
            select(TenantUserModel.user_id)
            .where(
                and_(
                    TenantUserModel.tenant_id == tenant_id,
                    TenantUserModel.status == 1,
                    cast(TenantUserModel.user_id, String) != current_user_id,
                )
            )
            .order_by(
                role_priority.asc(),
                TenantUserModel.is_primary.desc(),
                TenantUserModel.user_id.asc(),
            )
        ).first()
    except Exception:
        row = None
    owner_id = _first_scalar_value(row)
    return str(owner_id) if owner_id is not None else current_user_id


def _asset_operator_id(session: SessionDep, current_user: CurrentUser) -> str:
    return _workspace_delegate_asset_owner_id(session, current_user)


def _platform_delegate_visible_creator_ids(session: SessionDep, current_user: CurrentUser) -> set[str]:
    visible_ids = _workspace_admin_user_ids(session, current_user)
    visible_ids.add(_workspace_delegate_asset_owner_id(session, current_user))
    visible_ids.add(_user_id(current_user))
    return {item for item in visible_ids if item}


def _is_workspace_admin_owned_dashboard(session: SessionDep, current_user: CurrentUser, dashboard: CoreDashboard) -> bool:
    return str(dashboard.create_by) in _platform_delegate_visible_creator_ids(session, current_user)


def _is_platform_admin_context(current_user: CurrentUser | None) -> bool:
    workspace_status = getattr(current_user, "workspace_status", None)
    tenant_id = getattr(current_user, "tenant_id", None)
    return bool(
        is_system_admin(current_user)
        and not is_platform_workspace_delegate(current_user)
        and (tenant_id in (None, "") or workspace_status == "platform_admin")
    )


def _tenant_not_found(detail: str):
    raise HTTPException(status_code=404, detail=detail)


def _can_edit_datasource_dashboard(session: SessionDep, current_user: CurrentUser, datasource_id: int | None) -> bool:
    if datasource_id is None:
        return is_system_admin(current_user)
    return has_datasource_role(session, current_user, datasource_id, PROJECT_ROLE_EDITOR)


def _can_create_datasource_dashboard(session: SessionDep, current_user: CurrentUser, datasource_id: int | None) -> bool:
    if datasource_id is None:
        return is_system_admin(current_user)
    return has_datasource_access(session, current_user, datasource_id)


def _supports_datasource_editor_role_lookup(session: SessionDep) -> bool:
    try:
        inspector = inspect(session.connection())
        return inspector.has_table(CoreDatasource.__tablename__) and inspector.has_table("core_datasource_user")
    except Exception:
        return False


def _dashboard_list_visibility_filter(
        session: SessionDep,
        current_user: CurrentUser,
        datasource_id: int | None,
):
    if is_platform_workspace_delegate(current_user):
        return _platform_delegate_visible_dashboard_filter(session, current_user)
    if is_system_admin(current_user):
        return None
    if _can_set_default_dashboard(current_user):
        return or_(
            CoreDashboard.create_by == _user_id(current_user),
            CoreDashboard.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE,
        )
    return CoreDashboard.create_by == _user_id(current_user)


def _platform_delegate_visible_dashboard_filter(
        session: SessionDep,
        current_user: CurrentUser,
):
    visible_creator_ids = _platform_delegate_visible_creator_ids(session, current_user)
    return or_(
        CoreDashboard.is_default == 1,
        CoreDashboard.create_by.in_(visible_creator_ids),
        CoreDashboard.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE,
    )


def _is_public_dashboard_for_delegate(session: SessionDep, current_user: CurrentUser, dashboard: CoreDashboard) -> bool:
    if dashboard.is_default:
        return True
    if dashboard.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE:
        return True
    if _is_workspace_admin_owned_dashboard(session, current_user, dashboard):
        return True
    return False


def _is_published_workspace_dashboard(dashboard: CoreDashboard) -> bool:
    if dashboard.status in DASHBOARD_DRAFT_STATUSES:
        return False
    return bool(dashboard.is_default) or dashboard.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE


def _can_edit_dashboard(session: SessionDep, current_user: CurrentUser, dashboard: CoreDashboard) -> bool:
    if not _same_tenant(current_user, dashboard):
        return False
    if is_platform_workspace_delegate(current_user):
        return (
            str(dashboard.create_by) == _user_id(current_user)
            or _is_workspace_admin_owned_dashboard(session, current_user, dashboard)
            or dashboard.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE
            or bool(dashboard.is_default)
        )
    if dashboard.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE:
        return is_system_admin(current_user) or _can_set_default_dashboard(current_user)
    if dashboard.is_default:
        return _can_manage_default_dashboard(current_user, dashboard)
    return (
        is_system_admin(current_user)
        or str(dashboard.create_by) == _user_id(current_user)
    )


def _can_share_dashboard(session: SessionDep, current_user: CurrentUser, dashboard: CoreDashboard) -> bool:
    return _can_edit_dashboard(session, current_user, dashboard)


def _can_set_default_dashboard(current_user: CurrentUser) -> bool:
    return can_manage_workspace_scope(current_user)


def _can_manage_default_dashboard(current_user: CurrentUser, dashboard: CoreDashboard) -> bool:
    if not _same_tenant(current_user, dashboard):
        return False
    if is_platform_workspace_delegate(current_user):
        return True
    return (
        is_system_admin(current_user)
        or _can_set_default_dashboard(current_user)
        or str(dashboard.create_by) == _user_id(current_user)
    )


def _can_view_legacy_dashboard(current_user: CurrentUser, dashboard: CoreDashboard) -> bool:
    if not _same_tenant(current_user, dashboard):
        return False
    return is_system_admin(current_user) or str(dashboard.create_by) == _user_id(current_user)


def _can_view_dashboard_resource(session: SessionDep, current_user: CurrentUser, dashboard: CoreDashboard) -> bool:
    if not _same_tenant(current_user, dashboard):
        return False
    if is_platform_workspace_delegate(current_user):
        return (
            bool(dashboard.is_default)
            or str(dashboard.create_by) == _user_id(current_user)
            or _is_workspace_admin_owned_dashboard(session, current_user, dashboard)
            or dashboard.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE
        )
    if dashboard.is_default:
        return True
    if _is_published_workspace_dashboard(dashboard) and (is_system_admin(current_user) or _can_set_default_dashboard(current_user)):
        return True
    if str(dashboard.create_by) == _user_id(current_user):
        return True
    return False


def _require_create_permission(
        session: SessionDep,
        current_user: CurrentUser,
        datasource_id: int | None,
        parent_id: str | None = None,
):
    if not _can_create_datasource_dashboard(session, current_user, datasource_id):
        raise HTTPException(status_code=403, detail="Project access is required to create dashboards")
    if not parent_id or parent_id == "root":
        return

    parent = _load_dashboard_or_404(session, parent_id, current_user)
    parent_datasource = _effective_dashboard_datasource(parent)
    if parent_datasource != datasource_id:
        raise HTTPException(status_code=400, detail="Dashboard parent must belong to the same datasource")
    _require_edit_permission(session, current_user, parent)


def _require_edit_permission(session: SessionDep, current_user: CurrentUser, dashboard: CoreDashboard):
    if not _can_edit_dashboard(session, current_user, dashboard):
        raise HTTPException(status_code=403, detail="You do not have permission to modify this dashboard")


def _require_share_permission(session: SessionDep, current_user: CurrentUser, dashboard: CoreDashboard):
    if not _can_share_dashboard(session, current_user, dashboard):
        raise HTTPException(status_code=403, detail="You do not have permission to share this dashboard")


def _require_set_default_permission(current_user: CurrentUser):
    if not _can_set_default_dashboard(current_user):
        raise HTTPException(status_code=403, detail="Only workspace admin can set default dashboards")


def _require_platform_delegate(current_user: CurrentUser):
    if not is_platform_workspace_delegate(current_user):
        raise HTTPException(status_code=403, detail="Only SaaS delegate can use this dashboard operation")


def _normalize_datasource_id(datasource) -> int | None:
    if datasource is None or datasource == "":
        return None
    try:
        return int(datasource)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid datasource")


def _ensure_datasource_access(session: SessionDep, current_user: CurrentUser, datasource, required: bool = False) -> int | None:
    datasource_id = _normalize_datasource_id(datasource)
    if datasource_id is None:
        if required:
            raise HTTPException(status_code=400, detail="Dashboard datasource is required")
        return None
    if not session.get(CoreDatasource, datasource_id):
        raise HTTPException(status_code=404, detail="Datasource does not exist")
    if not has_datasource_access(session, current_user, datasource_id):
        raise HTTPException(status_code=403, detail="You do not have permission to access this datasource")
    return datasource_id


def _check_dashboard_view_permission(session: SessionDep, current_user: CurrentUser, dashboard: CoreDashboard):
    if dashboard.datasource:
        _ensure_datasource_access(session, current_user, dashboard.datasource)
        return
    if not _can_view_legacy_dashboard(current_user, dashboard):
        raise HTTPException(status_code=403, detail="You do not have permission to access this dashboard")


def _load_dashboard_or_404(
        session: SessionDep,
        dashboard_id: str,
        current_user: CurrentUser | None = None,
) -> CoreDashboard:
    record = session.get(CoreDashboard, dashboard_id)
    if not record or record.delete_flag == 1 or record.status in DASHBOARD_DRAFT_STATUSES:
        raise HTTPException(status_code=404, detail="Dashboard does not exist")
    if current_user is not None and not _same_tenant(current_user, record):
        _tenant_not_found("Dashboard does not exist")
    return record


def _load_platform_template_or_404(
        session: SessionDep,
        template_id: str,
        current_user: CurrentUser,
) -> CoreDashboard:
    if not (_is_platform_admin_context(current_user) or is_platform_workspace_delegate(current_user)):
        raise HTTPException(status_code=403, detail="Only SaaS admin can use dashboard templates")
    record = session.get(CoreDashboard, template_id)
    if (
        not record
        or record.delete_flag == 1
        or record.tenant_id != DEFAULT_TENANT_ID
        or record.source != DASHBOARD_SOURCE_PLATFORM_TEMPLATE
        or record.status in DASHBOARD_DRAFT_STATUSES
    ):
        raise HTTPException(status_code=404, detail="Dashboard template does not exist")
    return record


def _load_shared_dashboard_or_404(
        session: SessionDep,
        share_id: str,
        current_user: CurrentUser | None = None,
) -> CoreDashboardShare:
    record = session.get(CoreDashboardShare, share_id)
    if not record or record.delete_flag == 1:
        raise HTTPException(status_code=404, detail="Shared dashboard does not exist")
    if current_user is not None and not _same_tenant(current_user, record):
        _tenant_not_found("Shared dashboard does not exist")
    if current_user is not None and not _share_created_by_active_workspace_member(session, current_user, record):
        _tenant_not_found("Shared dashboard does not exist")
    return record


def _active_workspace_member_share_creator_filter(current_user: CurrentUser):
    return CoreDashboardShare.create_by.in_(
        select(cast(TenantUserModel.user_id, String)).where(
            and_(
                TenantUserModel.tenant_id == _current_tenant_id(current_user),
                TenantUserModel.status == 1,
            )
        )
    )


def _share_created_by_active_workspace_member(
        session: SessionDep,
        current_user: CurrentUser,
        share: CoreDashboardShare,
) -> bool:
    if not share.create_by:
        return False
    try:
        creator_id = int(share.create_by)
    except (TypeError, ValueError):
        return False
    statement = select(TenantUserModel.id).where(
        and_(
            TenantUserModel.tenant_id == _current_tenant_id(current_user),
            TenantUserModel.user_id == creator_id,
            TenantUserModel.status == 1,
        )
    )
    return session.exec(statement).first() is not None


def _parse_canvas_view_info(canvas_view_info: str | bytes | None) -> dict:
    if not canvas_view_info:
        return {}
    try:
        return orjson.loads(canvas_view_info)
    except Exception:
        return {}


def _parse_canvas_component_data(component_data: str | bytes | None) -> list:
    if not component_data:
        return []
    try:
        value = orjson.loads(component_data)
    except Exception:
        return []
    return value if isinstance(value, list) else []


def _new_canvas_id(prefix: str | None = None) -> str:
    value = uuid.uuid4().hex
    return f"{prefix}_{value}" if prefix else value


def _clone_canvas_component_tree(items: list, id_map: dict[str, str]) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        old_id = item.get("id")
        if old_id not in (None, ""):
            new_id = _new_canvas_id()
            id_map[str(old_id)] = new_id
            item["id"] = new_id
            if item.get("_dragId") not in (None, ""):
                item["_dragId"] = new_id

        tab_name_map: dict[str, str] = {}
        prop_value = item.get("propValue")
        if isinstance(prop_value, list):
            for tab in prop_value:
                if not isinstance(tab, dict):
                    continue
                old_tab_name = tab.get("name")
                if old_tab_name not in (None, ""):
                    new_tab_name = _new_canvas_id("tab")
                    tab_name_map[str(old_tab_name)] = new_tab_name
                    tab["name"] = new_tab_name
                if isinstance(tab.get("componentData"), list):
                    _clone_canvas_component_tree(tab["componentData"], id_map)
            active_tab_name = item.get("activeTabName")
            if active_tab_name not in (None, "") and str(active_tab_name) in tab_name_map:
                item["activeTabName"] = tab_name_map[str(active_tab_name)]

        nested_components = item.get("componentData")
        if isinstance(nested_components, list):
            _clone_canvas_component_tree(nested_components, id_map)


def _clone_dashboard_canvas_payload(
        component_data: str | bytes | None,
        canvas_style_data: str | bytes | None,
        canvas_view_info: str | bytes | None,
) -> tuple[str, str, str]:
    component_data_obj = _parse_canvas_component_data(component_data)
    canvas_view_obj = _parse_canvas_view_info(canvas_view_info)
    id_map: dict[str, str] = {}

    _clone_canvas_component_tree(component_data_obj, id_map)

    cloned_canvas_view_obj: dict[str, Any] = {}
    for view_id, view_info in canvas_view_obj.items():
        view_id_text = str(view_id)
        next_view_id = id_map.get(view_id_text, view_id_text)
        if isinstance(view_info, dict):
            current_view_id = view_info.get("id")
            if current_view_id in (None, "") or str(current_view_id) == view_id_text:
                view_info["id"] = next_view_id
            elif str(current_view_id) in id_map:
                view_info["id"] = id_map[str(current_view_id)]

            chart = view_info.get("chart")
            if isinstance(chart, dict):
                chart_id = chart.get("id")
                if chart_id in (None, "") or str(chart_id) == view_id_text:
                    chart["id"] = next_view_id
                elif str(chart_id) in id_map:
                    chart["id"] = id_map[str(chart_id)]
        cloned_canvas_view_obj[next_view_id] = view_info

    return (
        orjson.dumps(component_data_obj).decode(),
        canvas_style_data or "{}",
        orjson.dumps(cloned_canvas_view_obj).decode(),
    )


def _clone_dashboard_canvas_payload_for_datasource(
        component_data: str | bytes | None,
        canvas_style_data: str | bytes | None,
        canvas_view_info: str | bytes | None,
        datasource_id: int | None,
) -> tuple[str, str, str]:
    component_data, canvas_style_data, canvas_view_info = _clone_dashboard_canvas_payload(
        component_data,
        canvas_style_data,
        canvas_view_info,
    )
    if datasource_id is None:
        return component_data, canvas_style_data, canvas_view_info
    canvas_view_obj = _parse_canvas_view_info(canvas_view_info)
    for item in canvas_view_obj.values():
        if isinstance(item, dict):
            item["datasource"] = datasource_id
    return component_data, canvas_style_data, orjson.dumps(canvas_view_obj).decode()


def _copy_dashboard_canvas_payload_without_rekey(
        component_data: str | bytes | None,
        canvas_style_data: str | bytes | None,
        canvas_view_info: str | bytes | None,
        datasource_id: int | None = None,
) -> tuple[str, str, str]:
    component_data_obj = _parse_canvas_component_data(component_data)
    canvas_view_obj = _parse_canvas_view_info(canvas_view_info)
    if datasource_id is not None:
        for item in canvas_view_obj.values():
            if isinstance(item, dict):
                item["datasource"] = datasource_id
    return (
        orjson.dumps(component_data_obj).decode(),
        canvas_style_data or "{}",
        orjson.dumps(canvas_view_obj).decode(),
    )


def _canvas_uses_datasource(record: CoreDashboard, datasource_id: int) -> bool:
    canvas_view_obj = _parse_canvas_view_info(record.canvas_view_info)
    for item in canvas_view_obj.values():
        if not isinstance(item, dict):
            continue
        try:
            item_datasource = _normalize_datasource_id(item.get('datasource'))
        except HTTPException:
            continue
        if item_datasource == datasource_id:
            return True
    return False


def _infer_canvas_datasource(record: CoreDashboard) -> int | None:
    canvas_view_obj = _parse_canvas_view_info(record.canvas_view_info)
    datasource_ids = set()
    for item in canvas_view_obj.values():
        if not isinstance(item, dict):
            continue
        try:
            item_datasource = _normalize_datasource_id(item.get('datasource'))
        except HTTPException:
            continue
        if item_datasource is not None:
            datasource_ids.add(item_datasource)
    if len(datasource_ids) == 1:
        return next(iter(datasource_ids))
    return None


def _effective_dashboard_datasource(record: CoreDashboard) -> int | None:
    if record.datasource is not None:
        return record.datasource
    return _infer_canvas_datasource(record)


def _dashboard_matches_datasource(record: CoreDashboard, datasource_id: int) -> bool:
    if record.datasource == datasource_id:
        return True
    return record.datasource is None and _canvas_uses_datasource(record, datasource_id)


def _chart_datasource(record: CoreDashboard, item: dict, fallback_datasource: int | None = None) -> int | None:
    item_datasource = _normalize_datasource_id(item.get('datasource'))
    if item_datasource is None:
        item_datasource = fallback_datasource if fallback_datasource is not None else record.datasource
    if item_datasource is not None:
        item['datasource'] = item_datasource
    return item_datasource


_USER_PERMISSION_DENIED_MESSAGE = "SQL 超出当前数据权限范围"


_PIVOT_RANGE_DAYS = {
    "7d": 7,
    "14d": 14,
    "30d": 30,
    "90d": 90,
}


def _normalize_datasource_type(ds_type: str | None) -> str:
    return str(ds_type or "").strip().lower()


def _dashboard_sql_dialect(ds_type: str | None) -> str | None:
    dialect = get_sqlglot_dialect(ds_type)
    if dialect:
        return dialect
    ds_key = _normalize_datasource_type(ds_type)
    if ds_key in {"pg", "postgres", "postgresql"}:
        return "postgres"
    if ds_key in {"ck", "clickhouse"}:
        return "clickhouse"
    if ds_key in {"oracle", "dm"}:
        return "oracle"
    if ds_key in {"redshift"}:
        return "redshift"
    return None


def _quote_dashboard_identifier(name: str, ds_type: str | None) -> str:
    value = str(name or "").strip()
    dialect = _dashboard_sql_dialect(ds_type)
    if dialect in {"mysql", "hive"}:
        return f"`{value.replace('`', '``')}`"
    if dialect == "tsql":
        return f"[{value.replace(']', ']]')}]"
    return f'"{value.replace(chr(34), chr(34) + chr(34))}"'


def _dashboard_pivot_column(field_name: str, ds_type: str | None, alias: str = "pivot_src") -> str:
    return f"{_quote_dashboard_identifier(alias, ds_type)}.{_quote_dashboard_identifier(field_name, ds_type)}"


def _dashboard_date_cast(column_sql: str, ds_type: str | None, *, timestamp: bool = False) -> str:
    ds_key = _normalize_datasource_type(ds_type)
    if ds_key in {"mysql", "doris", "starrocks"}:
        return f"CAST({column_sql} AS DATETIME)" if timestamp else f"DATE({column_sql})"
    if ds_key in {"sqlserver", "sql server", "sql_server"}:
        return f"CAST({column_sql} AS DATETIME)" if timestamp else f"CAST({column_sql} AS DATE)"
    if ds_key in {"ck", "clickhouse"}:
        return f"toDateTime({column_sql})" if timestamp else f"toDate({column_sql})"
    if ds_key in {"oracle", "dm"}:
        return f"CAST({column_sql} AS DATE)"
    if ds_key == "hive":
        return f"CAST({column_sql} AS TIMESTAMP)" if timestamp else f"TO_DATE({column_sql})"
    return f"CAST({column_sql} AS TIMESTAMP)" if timestamp else f"CAST({column_sql} AS DATE)"


def _dashboard_period_expr(column_sql: str, ds_type: str | None, granularity: str) -> str:
    ds_key = _normalize_datasource_type(ds_type)
    if ds_key in {"mysql", "doris", "starrocks"}:
        date_expr = _dashboard_date_cast(column_sql, ds_type)
        datetime_expr = _dashboard_date_cast(column_sql, ds_type, timestamp=True)
        if granularity == "week":
            return f"DATE_SUB({date_expr}, INTERVAL WEEKDAY({datetime_expr}) DAY)"
        if granularity == "month":
            return f"DATE_FORMAT({datetime_expr}, '%Y-%m-01')"
        return date_expr
    if ds_key in {"sqlserver", "sql server", "sql_server"}:
        datetime_expr = _dashboard_date_cast(column_sql, ds_type, timestamp=True)
        if granularity == "week":
            return f"DATEADD(week, DATEDIFF(week, 0, {datetime_expr}), 0)"
        if granularity == "month":
            return f"DATEFROMPARTS(YEAR({datetime_expr}), MONTH({datetime_expr}), 1)"
        return _dashboard_date_cast(column_sql, ds_type)
    if ds_key in {"ck", "clickhouse"}:
        datetime_expr = _dashboard_date_cast(column_sql, ds_type, timestamp=True)
        if granularity == "week":
            return f"toStartOfWeek({datetime_expr}, 1)"
        if granularity == "month":
            return f"toStartOfMonth({datetime_expr})"
        return _dashboard_date_cast(column_sql, ds_type)
    if ds_key in {"oracle", "dm"}:
        date_expr = _dashboard_date_cast(column_sql, ds_type)
        if granularity == "week":
            return f"TRUNC({date_expr}, 'IW')"
        if granularity == "month":
            return f"TRUNC({date_expr}, 'MM')"
        return f"TRUNC({date_expr})"
    if granularity == "week":
        return f"DATE_TRUNC('week', {_dashboard_date_cast(column_sql, ds_type, timestamp=True)})"
    if granularity == "month":
        return f"DATE_TRUNC('month', {_dashboard_date_cast(column_sql, ds_type, timestamp=True)})"
    return _dashboard_date_cast(column_sql, ds_type)


def _dashboard_date_literal(value: str, ds_type: str | None) -> str:
    escaped = value.replace("'", "''")
    ds_key = _normalize_datasource_type(ds_type)
    if ds_key in {"mysql", "doris", "starrocks"}:
        return f"DATE('{escaped}')"
    if ds_key in {"ck", "clickhouse"}:
        return f"toDate('{escaped}')"
    if ds_key in {"sqlserver", "sql server", "sql_server"}:
        return f"CAST('{escaped}' AS DATE)"
    if ds_key in {"oracle", "dm"}:
        return f"TO_DATE('{escaped}', 'YYYY-MM-DD')"
    if ds_key == "hive":
        return f"TO_DATE('{escaped}')"
    return f"DATE '{escaped}'"


def _dashboard_date_subtract_expr(date_expr: str, ds_type: str | None, days: int) -> str:
    if days <= 0:
        return date_expr
    ds_key = _normalize_datasource_type(ds_type)
    if ds_key in {"mysql", "doris", "starrocks"}:
        return f"DATE_SUB({date_expr}, INTERVAL {days} DAY)"
    if ds_key in {"sqlserver", "sql server", "sql_server"}:
        return f"DATEADD(day, -{days}, {date_expr})"
    if ds_key in {"ck", "clickhouse"}:
        return f"subtractDays({date_expr}, {days})"
    if ds_key in {"oracle", "dm"}:
        return f"{date_expr} - {days}"
    if ds_key == "hive":
        return f"date_sub({date_expr}, {days})"
    return f"{date_expr} - INTERVAL '{days} days'"


def _dashboard_custom_date_value(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) >= 10:
        text = text[:10]
    if not text:
        return ""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        raise ValueError("自定义日期格式需为 YYYY-MM-DD")
    return text


def _trim_dashboard_sql(sql: str) -> str:
    value = str(sql or "").strip()
    while value.endswith(";"):
        value = value[:-1].rstrip()
    return value


def _dashboard_pivot_value(pivot: Any, key: str, default: Any = None) -> Any:
    if isinstance(pivot, dict):
        return pivot.get(key, default)
    return getattr(pivot, key, default)


def _dashboard_pivot_metric_fields(pivot: Any | None) -> list[str]:
    values = _dashboard_pivot_value(pivot, "metric_fields", []) or []
    if not isinstance(values, list):
        values = []
    fields = [str(field or "").strip() for field in values]
    fields = [field for field in fields if field]
    if not fields:
        fallback = str(_dashboard_pivot_value(pivot, "metric_field", "") or "").strip()
        fields = [fallback] if fallback else []
    return list(dict.fromkeys(fields))


def _dashboard_pivot_metric_aggregations(pivot: Any | None) -> dict[str, str]:
    value = _dashboard_pivot_value(pivot, "metric_aggregations", {}) or {}
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for field, aggregation in value.items():
        field_name = str(field or "").strip()
        agg_name = str(aggregation or "").strip().lower()
        if field_name and agg_name in {"sum", "avg", "min", "max", "count"}:
            result[field_name] = agg_name
    return result


def _dashboard_pivot_enabled(pivot: Any | None) -> bool:
    return bool(pivot is not None and _dashboard_pivot_value(pivot, "enabled", False))


def _dashboard_pivot_date_cast_error(message: str, pivot: Any | None) -> str | None:
    text = str(message or "")
    lowered = text.lower()
    mentions_date = "date" in lowered or "timestamp" in lowered or "日期" in text
    mentions_cast = (
        "cast" in lowered
        or "coerce" in lowered
        or "convert" in lowered
        or "转换" in text
        or "转化" in text
    )
    if not mentions_date or not mentions_cast:
        return None
    time_field = str(_dashboard_pivot_value(pivot, "time_field", "") or "").strip()
    if time_field:
        return f"透视时间字段「{time_field}」无法转换为日期/时间，请改选日期或时间字段；图表指标应选择数值字段。"
    return "透视时间字段无法转换为日期/时间，请改选日期或时间字段；图表指标应选择数值字段。"


def _dashboard_limit_clause(ds_type: str | None) -> str:
    ds_key = _normalize_datasource_type(ds_type)
    if ds_key in {"oracle", "dm", "sqlserver", "sql server", "sql_server"}:
        return ""
    return "\nLIMIT 1000"


def _build_dashboard_pivot_sql(sql: str, datasource: CoreDatasource, pivot: Any | None) -> str:
    if not _dashboard_pivot_enabled(pivot):
        return sql
    time_field = str(_dashboard_pivot_value(pivot, "time_field", "") or "").strip()
    metric_fields = _dashboard_pivot_metric_fields(pivot)
    group_field = str(_dashboard_pivot_value(pivot, "group_field", "") or "").strip()
    group_enabled = bool(_dashboard_pivot_value(pivot, "group_enabled", True))
    aggregation = str(_dashboard_pivot_value(pivot, "aggregation", "sum") or "sum").strip().lower()
    metric_aggregations = _dashboard_pivot_metric_aggregations(pivot)
    granularity = str(_dashboard_pivot_value(pivot, "granularity", "day") or "day").strip().lower()
    range_value = str(_dashboard_pivot_value(pivot, "range", "source") or "source").strip().lower()

    if not time_field or not metric_fields:
        raise ValueError("图表透视配置缺少时间字段或图表指标")
    if time_field in metric_fields:
        raise ValueError("透视时间字段和图表指标不能相同；时间字段请选择日期/时间字段，图表指标请选择数值字段")

    ds_type = getattr(datasource, "type", None)
    source_sql = _trim_dashboard_sql(sql)
    if not source_sql:
        raise ValueError("SQL不能为空")

    source_alias = _quote_dashboard_identifier("pivot_src", ds_type)
    bounds_alias = _quote_dashboard_identifier("pivot_bounds", ds_type)
    time_col = _dashboard_pivot_column(time_field, ds_type)
    source_time_date = _dashboard_date_cast(time_col, ds_type)
    max_period_col = _dashboard_pivot_column("max_period", ds_type, "pivot_bounds")
    period_expr = _dashboard_period_expr(time_col, ds_type, granularity)
    time_alias = _quote_dashboard_identifier(time_field, ds_type)

    if aggregation not in {"sum", "avg", "min", "max", "count"}:
        raise ValueError("不支持的图表透视聚合方式")

    select_items = [
        f"{period_expr} AS {time_alias}",
    ]
    for metric_field in metric_fields:
        metric_col = _dashboard_pivot_column(metric_field, ds_type)
        metric_alias = _quote_dashboard_identifier(metric_field, ds_type)
        metric_aggregation = metric_aggregations.get(metric_field, aggregation)
        if metric_aggregation == "count":
            metric_expr = f"COUNT({metric_col})"
        else:
            metric_expr = f"{metric_aggregation.upper()}({metric_col})"
        select_items.append(f"{metric_expr} AS {metric_alias}")
    group_items = [period_expr]
    order_items = [period_expr]
    if group_field and group_enabled:
        group_col = _dashboard_pivot_column(group_field, ds_type)
        group_alias = _quote_dashboard_identifier(group_field, ds_type)
        select_items.insert(1, f"{group_col} AS {group_alias}")
        group_items.append(group_col)
        order_items.append(group_col)

    where_parts: list[str] = []
    days = _PIVOT_RANGE_DAYS.get(range_value)
    if days is not None:
        cutoff = _dashboard_date_subtract_expr(max_period_col, ds_type, days - 1)
        where_parts.append(f"{source_time_date} >= {cutoff}")
    elif range_value == "custom":
        custom_start = _dashboard_custom_date_value(_dashboard_pivot_value(pivot, "custom_start", ""))
        custom_end = _dashboard_custom_date_value(_dashboard_pivot_value(pivot, "custom_end", ""))
        if custom_start:
            where_parts.append(f"{source_time_date} >= {_dashboard_date_literal(custom_start, ds_type)}")
        if custom_end:
            where_parts.append(f"{source_time_date} <= {_dashboard_date_literal(custom_end, ds_type)}")
        if not custom_start and not custom_end:
            raise ValueError("自定义日期范围至少需要开始日期或结束日期")
    elif range_value not in {"source", "all"}:
        raise ValueError("不支持的图表透视时间范围")

    where_clause = f"\nWHERE {' AND '.join(where_parts)}" if where_parts else ""

    if days is None:
        return (
            "SELECT\n  "
            + ",\n  ".join(select_items)
            + f"\nFROM (\n{source_sql}\n) AS {source_alias}"
            + where_clause
            + "\nGROUP BY "
            + ", ".join(group_items)
            + "\nORDER BY "
            + ", ".join(order_items)
            + _dashboard_limit_clause(ds_type)
        )

    cte_sql = (
        f"WITH {source_alias} AS (\n{source_sql}\n),\n"
        f"{bounds_alias} AS (\n"
        f"  SELECT MAX({source_time_date}) AS {_quote_dashboard_identifier('max_period', ds_type)}\n"
        f"  FROM {source_alias}\n"
        f")"
    )

    return (
        cte_sql
        + "\nSELECT\n  "
        + ",\n  ".join(select_items)
        + f"\nFROM {source_alias}\nCROSS JOIN {bounds_alias}"
        + where_clause
        + "\nGROUP BY "
        + ", ".join(group_items)
        + "\nORDER BY "
        + ", ".join(order_items)
        + _dashboard_limit_clause(ds_type)
    )


def _failed_chart_result(message: str, error_type: str | None = None) -> dict[str, Any]:
    result = {
        'status': 'failed',
        'data': [],
        'fields': [],
        'message': message,
    }
    if error_type:
        result['error_type'] = error_type
        result['reason'] = message
    return result


def _dashboard_sql_preview_cache_ttl() -> int:
    return max(0, int(getattr(settings, "DASHBOARD_SQL_PREVIEW_CACHE_TTL_SECONDS", 60) or 0))


def _dashboard_sql_preview_max_cache_entries() -> int:
    return max(0, int(getattr(settings, "DASHBOARD_SQL_PREVIEW_CACHE_MAX_ENTRIES", 512) or 0))


def _dashboard_sql_preview_datasource_concurrency() -> int:
    return max(1, int(getattr(settings, "DASHBOARD_SQL_PREVIEW_DATASOURCE_CONCURRENCY", 2) or 2))


def _dashboard_sql_preview_wait_timeout() -> float:
    return max(0.0, float(getattr(settings, "DASHBOARD_SQL_PREVIEW_WAIT_TIMEOUT_SECONDS", 1.0) or 0))


def _dashboard_sql_preview_dedupe_wait_timeout() -> float:
    return max(0.0, float(getattr(settings, "DASHBOARD_SQL_PREVIEW_DEDUPE_WAIT_TIMEOUT_SECONDS", 8.0) or 0))


def _dashboard_sql_preview_pivot_payload(pivot: Any | None) -> Any | None:
    if pivot is None:
        return None
    if hasattr(pivot, "model_dump"):
        return pivot.model_dump()
    if isinstance(pivot, dict):
        return pivot
    return str(pivot)


def _dashboard_sql_preview_cache_key(
        current_user: CurrentUser,
        datasource_id: int,
        sql: str,
        pivot: Any | None,
) -> str:
    payload = {
        "tenant_id": _current_tenant_id(current_user),
        "user_id": _user_id(current_user),
        "datasource_id": datasource_id,
        "sql": sql.strip(),
        "pivot": _dashboard_sql_preview_pivot_payload(pivot),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _dashboard_sql_preview_redis_enabled() -> bool:
    return (getattr(settings, "CACHE_TYPE", "memory") or "memory").lower() == "redis"


def _dashboard_sql_preview_redis_client() -> Redis | None:
    if not _dashboard_sql_preview_redis_enabled():
        return None
    global _DASHBOARD_SQL_PREVIEW_REDIS_CLIENT, _DASHBOARD_SQL_PREVIEW_REDIS_WARNING_LOGGED
    global _DASHBOARD_SQL_PREVIEW_REDIS_DISABLED_UNTIL
    if _DASHBOARD_SQL_PREVIEW_REDIS_DISABLED_UNTIL > time.monotonic():
        return None
    if _DASHBOARD_SQL_PREVIEW_REDIS_CLIENT is not None:
        return _DASHBOARD_SQL_PREVIEW_REDIS_CLIENT
    with _DASHBOARD_SQL_PREVIEW_REDIS_CLIENT_LOCK:
        if _DASHBOARD_SQL_PREVIEW_REDIS_CLIENT is not None:
            return _DASHBOARD_SQL_PREVIEW_REDIS_CLIENT
        try:
            _DASHBOARD_SQL_PREVIEW_REDIS_CLIENT = Redis.from_url(
                build_redis_url(),
                socket_timeout=getattr(settings, "REDIS_SOCKET_TIMEOUT", 10.0),
                socket_connect_timeout=getattr(settings, "REDIS_CONNECT_TIMEOUT", 3.0),
                health_check_interval=getattr(settings, "REDIS_HEALTH_CHECK_INTERVAL", 30),
                max_connections=getattr(settings, "REDIS_MAX_CONNECTIONS", 100),
                decode_responses=True,
            )
        except Exception:
            if not _DASHBOARD_SQL_PREVIEW_REDIS_WARNING_LOGGED:
                AppLogUtil.exception("Dashboard SQL preview Redis cache is unavailable; falling back to memory cache")
                _DASHBOARD_SQL_PREVIEW_REDIS_WARNING_LOGGED = True
            _DASHBOARD_SQL_PREVIEW_REDIS_DISABLED_UNTIL = time.monotonic() + 30
            return None
    return _DASHBOARD_SQL_PREVIEW_REDIS_CLIENT


def _dashboard_sql_preview_redis_key(cache_key: str) -> str:
    return redis_key("dashboard", "sql_preview", cache_key)


def _dashboard_sql_preview_memory_get(cache_key: str, *, allow_expired: bool = False) -> dict[str, Any] | None:
    ttl = _dashboard_sql_preview_cache_ttl()
    if ttl <= 0:
        return None
    now = time.monotonic()
    with _DASHBOARD_SQL_PREVIEW_CACHE_LOCK:
        cached = _DASHBOARD_SQL_PREVIEW_CACHE.get(cache_key)
        if cached is None:
            return None
        expires_at, result = cached
        if expires_at < now and not allow_expired:
            _DASHBOARD_SQL_PREVIEW_CACHE.pop(cache_key, None)
            return None
        _DASHBOARD_SQL_PREVIEW_CACHE.move_to_end(cache_key)
        cloned = copy.deepcopy(result)
    if allow_expired and cached[0] < now:
        cloned["cache_stale"] = True
    cloned["cache_hit"] = True
    return cloned


def _dashboard_sql_preview_memory_set(cache_key: str, result: dict[str, Any]) -> None:
    ttl = _dashboard_sql_preview_cache_ttl()
    max_entries = _dashboard_sql_preview_max_cache_entries()
    if ttl <= 0 or max_entries <= 0 or result.get("status") == "failed":
        return
    expires_at = time.monotonic() + ttl
    with _DASHBOARD_SQL_PREVIEW_CACHE_LOCK:
        _DASHBOARD_SQL_PREVIEW_CACHE[cache_key] = (expires_at, copy.deepcopy(result))
        _DASHBOARD_SQL_PREVIEW_CACHE.move_to_end(cache_key)
        while len(_DASHBOARD_SQL_PREVIEW_CACHE) > max_entries:
            _DASHBOARD_SQL_PREVIEW_CACHE.popitem(last=False)


def _dashboard_sql_preview_cache_get(cache_key: str, *, allow_expired: bool = False) -> dict[str, Any] | None:
    ttl = _dashboard_sql_preview_cache_ttl()
    if ttl <= 0:
        return None
    client = _dashboard_sql_preview_redis_client()
    if client is not None:
        try:
            raw = client.get(_dashboard_sql_preview_redis_key(cache_key))
            if raw:
                decoded = json.loads(raw)
                if isinstance(decoded, dict):
                    decoded["cache_hit"] = True
                    return decoded
        except (RedisError, json.JSONDecodeError):
            global _DASHBOARD_SQL_PREVIEW_REDIS_DISABLED_UNTIL, _DASHBOARD_SQL_PREVIEW_REDIS_WARNING_LOGGED
            if not _DASHBOARD_SQL_PREVIEW_REDIS_WARNING_LOGGED:
                AppLogUtil.exception("Dashboard SQL preview Redis cache read failed; falling back to memory cache")
                _DASHBOARD_SQL_PREVIEW_REDIS_WARNING_LOGGED = True
            _DASHBOARD_SQL_PREVIEW_REDIS_DISABLED_UNTIL = time.monotonic() + 30
    return _dashboard_sql_preview_memory_get(cache_key, allow_expired=allow_expired)


def _dashboard_sql_preview_cache_set(cache_key: str, result: dict[str, Any]) -> None:
    ttl = _dashboard_sql_preview_cache_ttl()
    if ttl <= 0 or result.get("status") == "failed":
        return
    client = _dashboard_sql_preview_redis_client()
    if client is not None:
        try:
            payload = copy.deepcopy(result)
            payload.pop("cache_hit", None)
            payload.pop("cache_stale", None)
            client.setex(
                _dashboard_sql_preview_redis_key(cache_key),
                ttl,
                json.dumps(payload, ensure_ascii=False, default=str),
            )
            return
        except RedisError:
            global _DASHBOARD_SQL_PREVIEW_REDIS_DISABLED_UNTIL, _DASHBOARD_SQL_PREVIEW_REDIS_WARNING_LOGGED
            if not _DASHBOARD_SQL_PREVIEW_REDIS_WARNING_LOGGED:
                AppLogUtil.exception("Dashboard SQL preview Redis cache write failed; falling back to memory cache")
                _DASHBOARD_SQL_PREVIEW_REDIS_WARNING_LOGGED = True
            _DASHBOARD_SQL_PREVIEW_REDIS_DISABLED_UNTIL = time.monotonic() + 30
    _dashboard_sql_preview_memory_set(cache_key, result)


def _dashboard_sql_preview_inflight_lock(cache_key: str) -> Lock:
    with _DASHBOARD_SQL_PREVIEW_INFLIGHT_LOCKS_LOCK:
        lock = _DASHBOARD_SQL_PREVIEW_INFLIGHT_LOCKS.get(cache_key)
        if lock is None:
            lock = Lock()
            _DASHBOARD_SQL_PREVIEW_INFLIGHT_LOCKS[cache_key] = lock
        return lock


def _dashboard_sql_preview_release_inflight_lock(cache_key: str, lock: Lock) -> None:
    with _DASHBOARD_SQL_PREVIEW_INFLIGHT_LOCKS_LOCK:
        if _DASHBOARD_SQL_PREVIEW_INFLIGHT_LOCKS.get(cache_key) is lock:
            _DASHBOARD_SQL_PREVIEW_INFLIGHT_LOCKS.pop(cache_key, None)


def _dashboard_sql_preview_datasource_semaphore(datasource_id: int) -> BoundedSemaphore:
    with _DASHBOARD_SQL_PREVIEW_DATASOURCE_SEMAPHORES_LOCK:
        semaphore = _DASHBOARD_SQL_PREVIEW_DATASOURCE_SEMAPHORES.get(datasource_id)
        if semaphore is None:
            semaphore = BoundedSemaphore(_dashboard_sql_preview_datasource_concurrency())
            _DASHBOARD_SQL_PREVIEW_DATASOURCE_SEMAPHORES[datasource_id] = semaphore
        return semaphore


def _normalize_dashboard_refresh_policy(value: Any) -> dict[str, Any]:
    policy = dict(DASHBOARD_REFRESH_POLICY_DEFAULT)
    if not isinstance(value, dict):
        return policy
    if "auto_refresh" in value:
        policy["auto_refresh"] = bool(value.get("auto_refresh"))
    hours_value = value.get("snapshot_max_age_hours")
    if hours_value is None:
        minutes_value = value.get("snapshot_max_age_minutes")
        if minutes_value is not None:
            try:
                hours_value = float(minutes_value) / 60
            except (TypeError, ValueError):
                hours_value = None
    try:
        hours = float(hours_value)
    except (TypeError, ValueError):
        hours = float(policy["snapshot_max_age_hours"])
    policy["snapshot_max_age_hours"] = max(0.0, min(hours, 24 * 30))
    return policy


def _extract_dashboard_refresh_policy_from_text(text_value: str | None) -> dict[str, Any] | None:
    if not text_value:
        return None
    policy: dict[str, Any] | None = None
    for match in DASHBOARD_REFRESH_POLICY_PATTERN.finditer(text_value):
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            policy = _normalize_dashboard_refresh_policy(parsed)
    return policy


def _custom_prompt_datasource_id_values(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _dashboard_refresh_policy_from_skills(
        session: SessionDep,
        current_user: CurrentUser,
        datasource_id: int | None,
) -> dict[str, Any]:
    if datasource_id is None:
        return dict(DASHBOARD_REFRESH_POLICY_DEFAULT)
    try:
        rows = session.execute(
            text(
                f"""
                SELECT id, prompt, specific_ds, datasource_ids, create_by, visibility_scope
                FROM custom_prompt
                WHERE type = :custom_prompt_type
                  AND COALESCE(active, false) = true
                  AND prompt ILIKE :policy_marker
                  AND (
                    (
                      visibility_scope = :platform_scope
                      AND (:can_manage_platform_public OR COALESCE(visible, true) = true)
                    )
                    OR
                    (
                      COALESCE(visibility_scope, :public_scope) = :public_scope
                      AND tenant_id = :tenant_id
                      AND (:can_manage_public OR COALESCE(visible, true) = true)
                    )
                    OR (visibility_scope = :private_scope AND create_by = :current_user_id)
                  )
                  AND (
                    :current_user_id IS NULL
                    OR NOT EXISTS (
                      SELECT 1
                      FROM custom_prompt_user_preference AS pref
                      WHERE pref.custom_prompt_id = custom_prompt.id
                        AND pref.user_id = :current_user_id
                        AND pref.enabled = false
                    )
                  )
                ORDER BY
                  CASE
                    WHEN visibility_scope = :platform_scope THEN 0
                    WHEN visibility_scope = :private_scope THEN 2
                    ELSE 1
                  END,
                  create_time DESC,
                  id DESC
                """
            ),
            {
                "custom_prompt_type": CUSTOM_PROMPT_TYPE_DATA_SKILL,
                "policy_marker": "%dashboard-refresh-policy%",
                "tenant_id": _current_tenant_id(current_user),
                "current_user_id": int(current_user.id) if getattr(current_user, "id", None) not in (None, "") else None,
                "platform_scope": CUSTOM_PROMPT_SCOPE_PLATFORM_PUBLIC,
                "public_scope": CUSTOM_PROMPT_SCOPE_ADMIN_PUBLIC,
                "private_scope": CUSTOM_PROMPT_SCOPE_USER_PRIVATE,
                "can_manage_public": can_manage_workspace_scope(current_user),
                "can_manage_platform_public": _is_platform_admin_context(current_user),
            },
        ).mappings().all()
        policy: dict[str, Any] | None = None
        for row in rows:
            if row.get("specific_ds") and str(datasource_id) not in _custom_prompt_datasource_id_values(row.get("datasource_ids")):
                continue
            next_policy = _extract_dashboard_refresh_policy_from_text(row.get("prompt"))
            if next_policy is not None:
                policy = next_policy
        return policy or dict(DASHBOARD_REFRESH_POLICY_DEFAULT)
    except Exception:
        AppLogUtil.exception(
            "Failed to load dashboard refresh policy from Data Skills by direct metadata query"
        )
        return dict(DASHBOARD_REFRESH_POLICY_DEFAULT)


def _execute_dashboard_chart_sql(
        session: SessionDep,
        current_user: CurrentUser,
        datasource_id: int,
        sql: str,
        pivot: Any | None = None,
) -> dict[str, Any]:
    if _dashboard_pivot_enabled(pivot):
        datasource = session.get(CoreDatasource, datasource_id)
        if datasource is None:
            return _failed_chart_result("项目不存在")
        try:
            sql = _build_dashboard_pivot_sql(sql, datasource, pivot)
        except Exception as exc:
            return _failed_chart_result(f"{exc}")
    result = execute_user_query(
        session=session,
        current_user=current_user,
        datasource_id=datasource_id,
        sql=sql,
        origin_column=True,
    )
    if _dashboard_pivot_enabled(pivot) and result.get("status") == "failed":
        friendly_message = _dashboard_pivot_date_cast_error(str(result.get("message") or ""), pivot)
        if friendly_message:
            result["message"] = friendly_message
            if result.get("reason"):
                result["reason"] = friendly_message
    return result


def _clear_dashboard_chart_data(item: dict) -> None:
    if not isinstance(item.get('data'), dict):
        item['data'] = {}
    item['data']['data'] = []
    item['data']['fields'] = []
    item['fields'] = []
    item['status'] = 'loading'
    item['message'] = ''
    item['dataState'] = 'loading'
    item['loadingProgress'] = 0


def _mark_dashboard_chart_snapshot_ready(item: dict) -> None:
    if not isinstance(item.get('data'), dict):
        item['data'] = {}
    item['data']['data'] = item['data'].get('data') if isinstance(item['data'].get('data'), list) else []
    data_fields = item['data'].get('fields') if isinstance(item['data'].get('fields'), list) else []
    item_fields = item.get('fields') if isinstance(item.get('fields'), list) else []
    item['data']['fields'] = data_fields or item_fields
    item['fields'] = item_fields or item['data']['fields']
    if item.get('status') in (None, '', 'loading') or item.get('dataState') == 'loading':
        item['status'] = 'success'
    item['dataState'] = 'failed' if item.get('status') == 'failed' else 'ready'
    item['loadingProgress'] = 100


def _apply_dashboard_chart_result(item: dict, data_result: dict[str, Any]) -> None:
    if not isinstance(item.get('data'), dict):
        item['data'] = {}
    fields = data_result.get('fields', [])
    item['data']['data'] = data_result['data']
    item['data']['fields'] = fields
    item['status'] = data_result['status']
    item['message'] = data_result['message']
    item['fields'] = fields
    item['dataState'] = 'failed' if item.get('status') == 'failed' else 'ready'
    item['loadingProgress'] = 100


def _clear_dashboard_payload_results(canvas_view_info: str | bytes | None) -> str:
    canvas_view_obj = _parse_canvas_view_info(canvas_view_info)
    for item in canvas_view_obj.values():
        if isinstance(item, dict):
            _mark_dashboard_chart_snapshot_ready(item)
    return orjson.dumps(canvas_view_obj).decode()


def _clear_dashboard_template_datasource(canvas_view_info: str | bytes | None) -> str:
    canvas_view_obj = _parse_canvas_view_info(canvas_view_info)
    _clear_dashboard_template_datasource_obj(canvas_view_obj)
    return orjson.dumps(canvas_view_obj).decode()


def _clear_dashboard_template_datasource_obj(canvas_view_obj: dict) -> None:
    for item in canvas_view_obj.values():
        if isinstance(item, dict):
            item["datasource"] = None


def _prepare_dashboard_template_canvas_view_info(canvas_view_info: str | bytes | None) -> str:
    canvas_view_obj = _parse_canvas_view_info(canvas_view_info)
    for item in canvas_view_obj.values():
        if not isinstance(item, dict):
            continue
        item["datasource"] = None
        if item.get("sql") is not None or isinstance(item.get("chart"), dict):
            _mark_dashboard_chart_snapshot_ready(item)
    return orjson.dumps(canvas_view_obj).decode()


def _remark_value(remark: str | None, key: str) -> str | None:
    if not remark:
        return None
    prefix = f"{key}="
    for part in str(remark).split(";"):
        if part.startswith(prefix):
            value = part[len(prefix):].strip()
            return value or None
    return None


def _platform_template_needs_snapshot_repair(template: CoreDashboard) -> bool:
    if template.datasource is not None:
        return True
    if template.content_id not in (None, "", "0"):
        return True
    canvas_view_obj = _parse_canvas_view_info(template.canvas_view_info)
    for item in canvas_view_obj.values():
        if not isinstance(item, dict):
            continue
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        rows = data.get("data") if isinstance(data, dict) else []
        if item.get("datasource") is not None:
            return True
        if item.get("status") == "loading" or item.get("dataState") == "loading":
            return True
        if item.get("sql") is not None and rows is None:
            return True
    return False


def _repair_platform_template_snapshot_if_needed(session: SessionDep, template: CoreDashboard) -> None:
    if not _platform_template_needs_snapshot_repair(template):
        return
    source_id = _remark_value(template.remark, "source_dashboard_id")
    source = session.get(CoreDashboard, source_id) if source_id else None
    if source and source.delete_flag != 1 and source.node_type == "leaf":
        component_data, canvas_style_data, canvas_view_info = _clone_dashboard_canvas_payload(
            source.component_data,
            source.canvas_style_data,
            source.canvas_view_info,
        )
        template.component_data = component_data
        template.canvas_style_data = canvas_style_data
        template.canvas_view_info = _prepare_dashboard_template_canvas_view_info(canvas_view_info)
    else:
        template.canvas_view_info = _prepare_dashboard_template_canvas_view_info(template.canvas_view_info)
    template.tenant_id = DEFAULT_TENANT_ID
    template.source = DASHBOARD_SOURCE_PLATFORM_TEMPLATE
    template.datasource = None
    template.content_id = "0"
    template.status = DASHBOARD_STATUS_ACTIVE
    template.update_time = _now()
    session.add(template)
    session.commit()
    session.refresh(template)


def _user_name(session: SessionDep, user_id) -> str | None:
    if not user_id:
        return None
    try:
        result = session.exec(select(UserModel.name).where(UserModel.id == int(user_id)))
        if hasattr(result, "scalars"):
            return result.scalars().first()
        value = result.first()
        return value[0] if value is not None and not isinstance(value, str) else value
    except (TypeError, ValueError):
        return None


def _validate_canvas_datasources(session: SessionDep, current_user: CurrentUser, dashboard: CreateDashboard,
                                 bound_datasource: int | None):
    canvas_view_obj = _parse_canvas_view_info(dashboard.canvas_view_info)
    for item in canvas_view_obj.values():
        if not isinstance(item, dict):
            continue
        item_sql = item.get('sql')
        item_datasource = _normalize_datasource_id(item.get('datasource'))
        if item_sql and not item_datasource:
            raise HTTPException(status_code=400, detail="Dashboard chart datasource is required")
        if item_datasource is None:
            continue
        if bound_datasource is not None and item_datasource != bound_datasource:
            raise HTTPException(
                status_code=400,
                detail="Dashboard charts must use the same datasource as the dashboard"
            )
        _ensure_datasource_access(session, current_user, item_datasource)


def _active_share_filter():
    return or_(CoreDashboardShare.delete_flag == 0, CoreDashboardShare.delete_flag.is_(None))


def _active_dashboard_filter():
    return and_(
        or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None)),
        or_(CoreDashboard.status.is_(None), CoreDashboard.status.notin_(DASHBOARD_DRAFT_STATUSES)),
    )


def _active_dashboard_share_map_for_user(
        session: SessionDep,
        current_user: CurrentUser,
        dashboard_ids: list[str],
) -> dict[str, CoreDashboardShare]:
    if not dashboard_ids:
        return {}
    statement = (
        select(CoreDashboardShare)
        .where(
            and_(
                _active_share_filter(),
                CoreDashboardShare.tenant_id == _current_tenant_id(current_user),
                CoreDashboardShare.share_type == "dashboard",
                CoreDashboardShare.source_dashboard_id.in_(dashboard_ids),
                CoreDashboardShare.create_by == _user_id(current_user),
            )
        )
        .order_by(CoreDashboardShare.update_time.desc(), CoreDashboardShare.create_time.desc())
    )
    shares = session.exec(statement).scalars().all()
    result: dict[str, CoreDashboardShare] = {}
    for share in shares:
        if share.source_dashboard_id and share.source_dashboard_id not in result:
            result[share.source_dashboard_id] = share
    return result


def _active_share_for_source(
        session: SessionDep,
        current_user: CurrentUser,
        share_type: str,
        source_dashboard_id: str,
        source_view_id: str | None = None,
) -> CoreDashboardShare | None:
    filters = [
        _active_share_filter(),
        CoreDashboardShare.tenant_id == _current_tenant_id(current_user),
        CoreDashboardShare.share_type == share_type,
        CoreDashboardShare.source_dashboard_id == source_dashboard_id,
        CoreDashboardShare.create_by == _user_id(current_user),
    ]
    if share_type == "chart":
        filters.append(CoreDashboardShare.source_view_id == source_view_id)
    else:
        filters.append(or_(CoreDashboardShare.source_view_id.is_(None), CoreDashboardShare.source_view_id == ""))
    statement = (
        select(CoreDashboardShare)
        .where(and_(*filters))
        .order_by(CoreDashboardShare.update_time.desc(), CoreDashboardShare.create_time.desc())
    )
    return session.exec(statement).scalars().first()


def _share_source_key(
        share: CoreDashboardShare,
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    return (
        str(getattr(share, "tenant_id")),
        str(share.create_by) if share.create_by is not None else None,
        share.share_type,
        share.source_dashboard_id,
        share.source_view_id if share.share_type == "chart" else None,
    )


def _active_shares_for_same_source(session: SessionDep, share: CoreDashboardShare) -> list[CoreDashboardShare]:
    filters = [
        _active_share_filter(),
        CoreDashboardShare.tenant_id == int(share.tenant_id),
        CoreDashboardShare.create_by == share.create_by,
        CoreDashboardShare.share_type == share.share_type,
        CoreDashboardShare.source_dashboard_id == share.source_dashboard_id,
    ]
    if share.share_type == "chart":
        filters.append(CoreDashboardShare.source_view_id == share.source_view_id)
    else:
        filters.append(or_(CoreDashboardShare.source_view_id.is_(None), CoreDashboardShare.source_view_id == ""))
    statement = select(CoreDashboardShare).where(and_(*filters))
    return session.exec(statement).scalars().all()


def _share_can_delete(current_user: CurrentUser, share: CoreDashboardShare) -> bool:
    return _same_tenant(current_user, share) and (
        is_system_admin(current_user) or str(share.create_by) == _user_id(current_user)
    )


def _dashboard_base_response(
        session: SessionDep,
        current_user: CurrentUser,
        record: CoreDashboard,
        datasource: int | None = None,
        active_share: CoreDashboardShare | None = None,
        platform_template_context: bool = False,
) -> DashboardBaseResponse:
    can_edit = (
        True
        if platform_template_context and _is_platform_admin_context(current_user)
        else False
        if _is_platform_admin_context(current_user)
        else _can_edit_dashboard(session, current_user, record)
    )
    can_share = (
        False
        if platform_template_context or _is_platform_admin_context(current_user)
        else _can_share_dashboard(session, current_user, record)
    )
    can_set_default = (
        False
        if platform_template_context or _is_platform_admin_context(current_user)
        else _can_set_default_dashboard(current_user)
    )
    is_public = bool(
        record.is_default
        or active_share is not None
        or record.source in {DASHBOARD_SOURCE_PLATFORM_DELEGATE, DASHBOARD_SOURCE_PLATFORM_TEMPLATE}
    )
    can_copy_to_platform_template = (
        is_platform_workspace_delegate(current_user)
        and record.node_type == "leaf"
        and _is_public_dashboard_for_delegate(session, current_user, record)
    )
    return DashboardBaseResponse(
        id=record.id,
        tenant_id=record.tenant_id,
        name=record.name,
        pid=record.pid,
        datasource=None if platform_template_context else record.datasource if datasource is None else datasource,
        node_type=record.node_type,
        leaf=record.node_type == 'leaf',
        type=record.type,
        status=record.status,
        source=record.source,
        content_id="0" if platform_template_context else record.content_id,
        remark=record.remark,
        create_by=str(record.create_by) if record.create_by is not None else None,
        update_by=str(record.update_by) if record.update_by is not None else None,
        create_time=record.create_time,
        update_time=record.update_time,
        sort=record.sort or 0,
        can_edit=can_edit,
        can_share=can_share,
        can_set_default=can_set_default,
        is_default=bool(record.is_default),
        is_shared=active_share is not None,
        is_public=is_public,
        can_copy_to_platform_template=can_copy_to_platform_template,
        share_id=active_share.id if active_share else None,
    )


def _share_can_use(session: SessionDep, current_user: CurrentUser, share: CoreDashboardShare) -> bool:
    if not _same_tenant(current_user, share):
        return False
    datasource_id = _normalize_datasource_id(share.datasource)
    if datasource_id is None:
        return False
    return has_datasource_access(session, current_user, datasource_id)


def _datasource_name(session: SessionDep, datasource_id: int | None) -> str | None:
    if datasource_id is None:
        return None
    datasource = session.get(CoreDatasource, datasource_id)
    return datasource.name if datasource else None


def _share_chart_snapshot(record: CoreDashboard, source_view_id: str) -> tuple[str, str, str]:
    if not source_view_id:
        raise HTTPException(status_code=400, detail="Shared chart source_view_id is required")
    component_data_obj = orjson.loads(record.component_data or "[]")
    canvas_view_obj = _parse_canvas_view_info(record.canvas_view_info)
    if source_view_id not in canvas_view_obj:
        raise HTTPException(status_code=404, detail="Dashboard chart does not exist")
    component = next(
        (item for item in component_data_obj if isinstance(item, dict) and str(item.get("id")) == source_view_id),
        None,
    )
    if not component:
        raise HTTPException(status_code=404, detail="Dashboard chart component does not exist")
    return (
        orjson.dumps([component]).decode(),
        "{}",
        orjson.dumps({source_view_id: canvas_view_obj[source_view_id]}).decode(),
    )


def _load_share_preview_payload(
        session: SessionDep,
        current_user: CurrentUser,
        share: CoreDashboardShare,
) -> dict[str, Any]:
    datasource_id = _normalize_datasource_id(share.datasource)
    can_use = _share_can_use(session, current_user, share)
    result_dict = {
        "id": share.id,
        "tenant_id": share.tenant_id,
        "name": share.name,
        "datasource": datasource_id,
        "type": "dashboard",
        "node_type": "leaf",
        "component_data": share.component_data or "[]",
        "canvas_style_data": share.canvas_style_data or "{}",
        "canvas_view_info": share.canvas_view_info or "{}",
        "preview_image": share.preview_image,
        "create_name": _user_name(session, share.create_by),
        "update_name": _user_name(session, share.update_by),
        "create_time": share.create_time,
        "update_time": share.update_time,
        "can_edit": False,
        "can_use": can_use,
        "can_delete": _share_can_delete(current_user, share),
        "share_type": share.share_type,
        "source_dashboard_id": share.source_dashboard_id,
        "source_view_id": share.source_view_id,
    }

    canvas_view_obj = _parse_canvas_view_info(result_dict.get("canvas_view_info"))
    for item in canvas_view_obj.values():
        if not isinstance(item, dict):
            continue
        item_datasource = _normalize_datasource_id(item.get("datasource"))
        if item_datasource is None:
            item_datasource = datasource_id
            if item_datasource is not None:
                item["datasource"] = item_datasource
        if item.get("sql") is None:
            continue
        if not can_use or item_datasource is None:
            data_result = _failed_chart_result(_USER_PERMISSION_DENIED_MESSAGE)
        else:
            if _dashboard_pivot_enabled(item.get("pivot")):
                data_result = _execute_dashboard_chart_sql(
                    session,
                    current_user,
                    item_datasource,
                    item["sql"],
                    item.get("pivot"),
                )
            else:
                data_result = _execute_dashboard_chart_sql(session, current_user, item_datasource, item["sql"])
        if not isinstance(item.get("data"), dict):
            item["data"] = {}
        item["data"]["data"] = data_result["data"]
        item["status"] = data_result["status"]
        item["message"] = data_result["message"]
        item["fields"] = data_result.get("fields", [])
    result_dict["canvas_view_info"] = orjson.dumps(canvas_view_obj).decode()
    return result_dict


def list_resource(session: SessionDep, dashboard: QueryDashboard, current_user: CurrentUser):
    filters = [
        _active_dashboard_filter(),
        CoreDashboard.tenant_id == _current_tenant_id(current_user),
        or_(CoreDashboard.is_default == 0, CoreDashboard.node_type == "leaf"),
    ]
    datasource_id = _normalize_datasource_id(dashboard.datasource)
    if datasource_id is not None:
        _ensure_datasource_access(session, current_user, datasource_id)
    elif not is_system_admin(current_user):
        accessible_ids = get_accessible_datasource_ids(session, current_user)
        legacy_filter = and_(CoreDashboard.datasource.is_(None), CoreDashboard.create_by == _user_id(current_user))
        if accessible_ids:
            filters.append(or_(CoreDashboard.datasource.in_(accessible_ids), legacy_filter))
        else:
            filters.append(legacy_filter)

    if dashboard.node_type is not None and dashboard.node_type != "":
        filters.append(CoreDashboard.node_type == dashboard.node_type)

    visibility_filter = _dashboard_list_visibility_filter(session, current_user, datasource_id)
    if visibility_filter is not None:
        filters.append(visibility_filter)

    statement = (
        select(CoreDashboard)
        .where(and_(*filters))
        .order_by(
            func.coalesce(CoreDashboard.sort, 0).asc(),
            CoreDashboard.create_time.desc(),
        )
    )
    result = session.exec(statement).scalars().all()
    if datasource_id is not None:
        result = [record for record in result if _dashboard_matches_datasource(record, datasource_id)]
    share_map = _active_dashboard_share_map_for_user(
        session,
        current_user,
        [record.id for record in result],
    )
    nodes = [
        _dashboard_base_response(session, current_user, record, datasource_id, share_map.get(record.id))
        for record in result
    ]
    visible_ids = {node.id for node in nodes if node.id is not None}
    for node in nodes:
        if (
            node.is_default
            and node.node_type == "leaf"
            and node.pid not in ("root", "0", "", None)
            and node.pid not in visible_ids
        ):
            node.pid = "root"
    tree = build_tree_generic(nodes, root_pid="root")
    return tree


def _dashboard_payload(
        session: SessionDep,
        current_user: CurrentUser,
        record: CoreDashboard,
        *,
        dashboard: QueryDashboard | None = None,
        default_context: bool = False,
        platform_template_context: bool = False,
        include_data: bool = True,
):
    effective_datasource = None if platform_template_context else _effective_dashboard_datasource(record)
    if dashboard is not None and dashboard.datasource is not None and effective_datasource is not None:
        request_datasource = _normalize_datasource_id(dashboard.datasource)
        if request_datasource != effective_datasource:
            raise HTTPException(status_code=403, detail="Dashboard does not belong to the selected datasource")
    if effective_datasource is not None and not default_context and not platform_template_context:
        _ensure_datasource_access(session, current_user, effective_datasource)
    elif effective_datasource is None and not default_context and not platform_template_context:
        _check_dashboard_view_permission(session, current_user, record)

    result_dict = record.model_dump()
    result_dict['datasource'] = effective_datasource
    result_dict['dashboard_refresh_policy'] = _dashboard_refresh_policy_from_skills(
        session,
        current_user,
        effective_datasource,
    )
    creator = _user_name(session, record.create_by)
    updater = _user_name(session, record.update_by)
    result_dict['create_name'] = creator
    result_dict['update_name'] = updater
    if platform_template_context:
        result_dict['can_edit'] = _is_platform_admin_context(current_user)
        result_dict['can_share'] = False
        result_dict['can_set_default'] = False
    else:
        result_dict['can_edit'] = _can_edit_dashboard(session, current_user, record)
        result_dict['can_share'] = _can_share_dashboard(session, current_user, record)
        result_dict['can_set_default'] = _can_set_default_dashboard(current_user)
    result_dict['is_default'] = bool(record.is_default)

    canvas_view_obj = _parse_canvas_view_info(result_dict.get('canvas_view_info'))
    for item in canvas_view_obj.values():
        if not isinstance(item, dict):
            continue
        if platform_template_context:
            item["datasource"] = None
            if item.get('sql') is not None:
                _mark_dashboard_chart_snapshot_ready(item)
            continue
        else:
            item_datasource = _chart_datasource(record, item, effective_datasource)
        if item.get('sql') is not None:
            if not include_data:
                _mark_dashboard_chart_snapshot_ready(item)
                continue
            if item_datasource is None:
                continue
            if record.datasource is not None and item_datasource != record.datasource:
                data_result = {
                    'status': 'failed',
                    'data': [],
                    'fields': [],
                    'message': 'Dashboard chart datasource does not match the dashboard datasource',
                }
            else:
                if _dashboard_pivot_enabled(item.get("pivot")):
                    data_result = _execute_dashboard_chart_sql(
                        session,
                        current_user,
                        item_datasource,
                        item['sql'],
                        item.get("pivot"),
                    )
                else:
                    data_result = _execute_dashboard_chart_sql(session, current_user, item_datasource, item['sql'])
            _apply_dashboard_chart_result(item, data_result)
    result_dict['canvas_view_info'] = orjson.dumps(canvas_view_obj).decode()
    return result_dict


def load_resource(session: SessionDep, dashboard: QueryDashboard, current_user: CurrentUser):
    record = _load_dashboard_or_404(session, dashboard.id, current_user)
    if not _can_view_dashboard_resource(session, current_user, record):
        raise HTTPException(status_code=404, detail="Dashboard does not exist")
    return _dashboard_payload(
        session,
        current_user,
        record,
        dashboard=dashboard,
        include_data=dashboard.include_data,
    )


def list_default_resources(session: SessionDep, current_user: CurrentUser):
    statement = (
        select(CoreDashboard)
        .where(
            and_(
                _active_dashboard_filter(),
                CoreDashboard.tenant_id == _current_tenant_id(current_user),
                CoreDashboard.is_default == 1,
            )
        )
        .order_by(
            func.coalesce(CoreDashboard.sort, 0).asc(),
            CoreDashboard.update_time.asc(),
            CoreDashboard.create_time.asc(),
        )
    )
    result = session.exec(statement).scalars().all()
    nodes = [
        _dashboard_base_response(session, current_user, record, _effective_dashboard_datasource(record))
        for record in result
    ]
    visible_ids = {node.id for node in nodes if node.id is not None}
    for node in nodes:
        if node.pid not in ("root", "0", "", None) and node.pid not in visible_ids:
            node.pid = "root"
    return build_tree_generic(nodes, root_pid="root")


def load_default_resource(session: SessionDep, dashboard: QueryDashboard, current_user: CurrentUser):
    record = _load_dashboard_or_404(session, dashboard.id, current_user)
    if not record.is_default:
        raise HTTPException(status_code=404, detail="Default dashboard does not exist")
    return _dashboard_payload(
        session,
        current_user,
        record,
        default_context=True,
        include_data=dashboard.include_data,
    )


def copy_default_resource(session: SessionDep, user: CurrentUser, request: DashboardDefaultCopyRequest):
    source = _load_dashboard_or_404(session, request.dashboard_id, user)
    if source.node_type != "leaf" or not source.is_default:
        raise HTTPException(status_code=404, detail="Default dashboard does not exist")

    datasource_id = _effective_dashboard_datasource(source)
    if datasource_id is None:
        raise HTTPException(status_code=400, detail="Default dashboard datasource is required")
    if not datasource_bound_to_tenant(session, int(datasource_id), _current_tenant_id(user)):
        raise HTTPException(status_code=403, detail="Dashboard datasource is not in current workspace")
    _ensure_datasource_access(session, user, datasource_id, required=True)
    _require_create_permission(session, user, datasource_id, "root")

    now = int(time.time())
    component_data, canvas_style_data, canvas_view_info = _clone_dashboard_canvas_payload(
        source.component_data,
        source.canvas_style_data,
        source.canvas_view_info,
    )
    operator_id = _asset_operator_id(session, user)
    record = CoreDashboard(
        id=uuid.uuid4().hex,
        tenant_id=_current_tenant_id(user),
        name=source.name,
        pid="root",
        datasource=datasource_id,
        org_id=source.org_id or "",
        level=source.level or 1,
        node_type="leaf",
        type=source.type or "dashboard",
        canvas_style_data=canvas_style_data,
        component_data=component_data,
        canvas_view_info=canvas_view_info,
        mobile_layout=source.mobile_layout or 0,
        status=1,
        self_watermark_status=source.self_watermark_status or 0,
        is_default=0,
        sort=0,
        create_by=operator_id,
        update_by=operator_id,
        create_time=now,
        update_time=now,
        delete_flag=0,
        version=source.version or 3,
        content_id="0",
        check_version=source.check_version or "1",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def get_create_base_info(user: CurrentUser, dashboard: CreateDashboard):
    new_id = uuid.uuid4().hex
    record = CoreDashboard(**dashboard.model_dump(exclude={"include_data"}))
    record.id = new_id
    record.tenant_id = _current_tenant_id(user)
    record.create_by = str(user.id)
    record.create_time = _now()
    record.status = record.status or DASHBOARD_STATUS_ACTIVE
    record.is_default = _smallint_flag(record.is_default)
    record.delete_flag = 0 if record.delete_flag is None else record.delete_flag
    return record


def create_resource(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    is_default_folder = bool(dashboard.is_default) and dashboard.node_type == "folder"
    if is_default_folder:
        _require_set_default_permission(user)
        dashboard.datasource = None
        if dashboard.pid and dashboard.pid != "root":
            parent = _load_dashboard_or_404(session, dashboard.pid, user)
            if parent.node_type != "folder" or not parent.is_default:
                raise HTTPException(status_code=400, detail="Default dashboard parent must be recommended folder")
    else:
        dashboard.datasource = _ensure_datasource_access(session, user, dashboard.datasource, required=True)
        _require_create_permission(session, user, dashboard.datasource, dashboard.pid)
    record = get_create_base_info(user, dashboard)
    record.is_default = 1 if dashboard.is_default else 0
    if is_platform_workspace_delegate(user):
        record.create_by = _asset_operator_id(session, user)
    record.update_by = record.create_by
    session.add(record)
    session.flush()
    session.refresh(record)
    session.commit()
    session.refresh(record)
    return record


def update_resource(session: SessionDep, user: CurrentUser, dashboard: QueryDashboard):
    record = _load_dashboard_or_404(session, dashboard.id, user)
    _require_edit_permission(session, user, record)
    if record.datasource:
        _ensure_datasource_access(session, user, record.datasource)
    record.name = dashboard.name
    record.update_by = _asset_operator_id(session, user)
    record.update_time = int(time.time())
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def create_canvas(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    dashboard.datasource = _ensure_datasource_access(session, user, dashboard.datasource, required=True)
    _require_create_permission(session, user, dashboard.datasource, dashboard.pid)
    _validate_canvas_datasources(session, user, dashboard, dashboard.datasource)
    record = get_create_base_info(user, dashboard)
    if is_platform_workspace_delegate(user):
        record.create_by = _asset_operator_id(session, user)
    record.update_by = record.create_by
    record.node_type = dashboard.node_type
    record.component_data = dashboard.component_data
    record.canvas_style_data = dashboard.canvas_style_data
    record.canvas_view_info = _sanitize_canvas_view_info(dashboard.canvas_view_info)
    session.add(record)
    session.flush()
    session.refresh(record)
    session.commit()
    session.refresh(record)
    return record


def update_canvas(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    record = _load_dashboard_or_404(session, dashboard.id, user)
    _require_edit_permission(session, user, record)
    request_datasource = _normalize_datasource_id(dashboard.datasource)
    bound_datasource = record.datasource or request_datasource
    if request_datasource is not None and record.datasource is not None and request_datasource != record.datasource:
        raise HTTPException(status_code=400, detail="Dashboard datasource cannot be changed")
    if bound_datasource is not None:
        _ensure_datasource_access(session, user, bound_datasource)
    _validate_canvas_datasources(session, user, dashboard, bound_datasource)
    record.name = dashboard.name
    record.datasource = bound_datasource
    record.update_by = _asset_operator_id(session, user)
    record.update_time = int(time.time())
    record.component_data = dashboard.component_data
    record.canvas_style_data = dashboard.canvas_style_data
    record.canvas_view_info = _sanitize_canvas_view_info(dashboard.canvas_view_info)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def move_resource(session: SessionDep, user: CurrentUser, dashboard: QueryDashboard):
    record = _load_dashboard_or_404(session, dashboard.id, user)
    _require_edit_permission(session, user, record)
    target_pid = dashboard.pid or "root"
    if target_pid in ("0", ""):
        target_pid = "root"
    if target_pid == record.id:
        raise HTTPException(status_code=400, detail="Dashboard cannot move under itself")
    if target_pid != "root":
        parent = _load_dashboard_or_404(session, target_pid, user)
        _require_edit_permission(session, user, parent)
        if parent.node_type != "folder":
            raise HTTPException(status_code=400, detail="Dashboard parent must be a folder")
        if _effective_dashboard_datasource(parent) != _effective_dashboard_datasource(record):
            raise HTTPException(status_code=400, detail="Dashboard parent must belong to the same datasource")
    record.pid = target_pid
    record.update_by = _asset_operator_id(session, user)
    record.update_time = _now()
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def set_default_resource(session: SessionDep, user: CurrentUser, request: DashboardDefaultRequest):
    _require_set_default_permission(user)
    record = _load_dashboard_or_404(session, request.dashboard_id, user)
    if record.node_type != "leaf":
        raise HTTPException(status_code=400, detail="Default dashboard must be a dashboard")
    effective_datasource = _effective_dashboard_datasource(record)
    if effective_datasource is not None:
        datasource = session.get(CoreDatasource, effective_datasource)
        if not datasource or not datasource_bound_to_tenant(session, int(effective_datasource), _current_tenant_id(user)):
            raise HTTPException(status_code=403, detail="Dashboard datasource is not in current workspace")

    now = int(time.time())
    if request.is_default and not record.is_default:
        max_sort_row = session.exec(
            select(func.max(func.coalesce(CoreDashboard.sort, 0)))
            .where(
                and_(
                    _active_dashboard_filter(),
                    CoreDashboard.tenant_id == _current_tenant_id(user),
                    CoreDashboard.node_type == "leaf",
                    CoreDashboard.is_default == 1,
                )
            )
        ).first()
        max_sort = _first_scalar_value(max_sort_row)
        record.sort = int(max_sort or 0) + 1
    elif not request.is_default and record.is_default:
        parent = (
            session.exec(
                select(CoreDashboard).where(
                    and_(
                        _active_dashboard_filter(),
                        CoreDashboard.tenant_id == _current_tenant_id(user),
                        CoreDashboard.id == record.pid,
                    )
                )
            ).first()
            if record.pid not in ("root", "0", "", None)
            else None
        )
        if parent and parent.is_default:
            record.pid = "root"
    record.is_default = 1 if request.is_default else 0
    record.update_by = _asset_operator_id(session, user)
    record.update_time = now
    session.add(record)
    session.commit()
    session.refresh(record)
    return _dashboard_base_response(session, user, record, effective_datasource)


def sort_default_resources(session: SessionDep, user: CurrentUser, request: DashboardDefaultSortRequest):
    _require_set_default_permission(user)
    ordered_ids = [str(item) for item in request.ordered_ids if item]
    if not ordered_ids:
        raise HTTPException(status_code=400, detail="ordered_ids is required")

    records = session.exec(
        select(CoreDashboard).where(
            and_(
                _active_dashboard_filter(),
                CoreDashboard.tenant_id == _current_tenant_id(user),
                CoreDashboard.node_type == "leaf",
                CoreDashboard.is_default == 1,
                CoreDashboard.id.in_(ordered_ids),
            )
        )
    ).scalars().all()
    record_by_id = {record.id: record for record in records}
    if len(record_by_id) != len(set(ordered_ids)):
        raise HTTPException(status_code=404, detail="Default dashboard does not exist")

    now = int(time.time())
    operator_id = _asset_operator_id(session, user)
    for index, dashboard_id in enumerate(ordered_ids):
        record = record_by_id[dashboard_id]
        record.sort = index + 1
        record.update_by = operator_id
        record.update_time = now
        session.add(record)

    session.commit()
    return True


def _would_create_dashboard_cycle(record_by_id: dict[str, CoreDashboard], child_id: str, target_pid: str) -> bool:
    seen = {child_id}
    current_pid = target_pid
    while current_pid and current_pid != "root":
        if current_pid in seen:
            return True
        seen.add(current_pid)
        parent = record_by_id.get(current_pid)
        if parent is None:
            return False
        current_pid = parent.pid or "root"
    return False


def reorder_resources(session: SessionDep, user: CurrentUser, request: DashboardReorderRequest):
    if not request.items:
        raise HTTPException(status_code=400, detail="items is required")

    scope = request.scope or "my"
    if scope == "default":
        _require_set_default_permission(user)

    item_ids = [str(item.id) for item in request.items if item.id]
    unique_ids = list(dict.fromkeys(item_ids))
    if not unique_ids:
        raise HTTPException(status_code=400, detail="items is required")

    records = session.exec(
        select(CoreDashboard).where(
            and_(
                _active_dashboard_filter(),
                CoreDashboard.tenant_id == _current_tenant_id(user),
                CoreDashboard.id.in_(unique_ids),
            )
        )
    ).scalars().all()
    record_by_id = {record.id: record for record in records}
    if len(record_by_id) != len(unique_ids):
        raise HTTPException(status_code=404, detail="Dashboard does not exist")

    for record in records:
        if scope == "default":
            if not record.is_default:
                raise HTTPException(status_code=400, detail="Default dashboard tree can only contain recommended dashboards")
        else:
            _require_edit_permission(session, user, record)
            if record.is_default:
                raise HTTPException(status_code=400, detail="Recommended dashboards must be reordered in recommended scope")

    for item in request.items:
        record = record_by_id[str(item.id)]
        target_pid = item.pid or "root"
        if target_pid in ("0", ""):
            target_pid = "root"
        if target_pid == record.id or _would_create_dashboard_cycle(record_by_id, record.id, target_pid):
            raise HTTPException(status_code=400, detail="Dashboard cannot move under itself")
        if target_pid == "root":
            continue
        parent = record_by_id.get(target_pid) or _load_dashboard_or_404(session, target_pid, user)
        if parent.node_type != "folder":
            raise HTTPException(status_code=400, detail="Dashboard parent must be a folder")
        if scope == "default" and not parent.is_default:
            raise HTTPException(status_code=400, detail="Default dashboard parent must be recommended")
        if scope == "my" and parent.is_default:
            raise HTTPException(status_code=400, detail="My dashboard parent cannot be recommended")
        if scope == "my":
            parent_datasource = _effective_dashboard_datasource(parent)
            record_datasource = _effective_dashboard_datasource(record)
            if parent_datasource is not None and record_datasource is not None and parent_datasource != record_datasource:
                raise HTTPException(status_code=400, detail="Dashboard parent must belong to the same datasource")

    now = int(time.time())
    operator_id = _asset_operator_id(session, user)
    for item in request.items:
        record = record_by_id[str(item.id)]
        target_pid = item.pid or "root"
        if target_pid in ("0", ""):
            target_pid = "root"
        record.pid = target_pid
        record.sort = item.sort or 0
        record.update_by = operator_id
        record.update_time = now
        session.add(record)

    session.commit()
    return True


def copy_dashboard_to_platform_template(
        session: SessionDep,
        user: CurrentUser,
        dashboard_id: str,
        name: str = "",
):
    _require_platform_delegate(user)
    source = _load_dashboard_or_404(session, dashboard_id, user)
    if source.node_type != "leaf" or not _is_public_dashboard_for_delegate(session, user, source):
        raise HTTPException(status_code=404, detail="Dashboard does not exist")

    component_data, canvas_style_data, canvas_view_info = _clone_dashboard_canvas_payload(
        source.component_data,
        source.canvas_style_data,
        source.canvas_view_info,
    )
    canvas_view_info = _prepare_dashboard_template_canvas_view_info(canvas_view_info)
    now = _now()
    record = CoreDashboard(
        id=uuid.uuid4().hex,
        tenant_id=DEFAULT_TENANT_ID,
        name=(name or source.name or "").strip() or source.name,
        pid="root",
        datasource=None,
        org_id=source.org_id or "",
        level=1,
        node_type="leaf",
        type=source.type or "dashboard",
        canvas_style_data=canvas_style_data,
        component_data=component_data,
        canvas_view_info=canvas_view_info,
        mobile_layout=source.mobile_layout or 0,
        status=DASHBOARD_STATUS_ACTIVE,
        source=DASHBOARD_SOURCE_PLATFORM_TEMPLATE,
        remark=f"source_dashboard_id={source.id};source_tenant_id={source.tenant_id}",
        self_watermark_status=source.self_watermark_status or 0,
        is_default=0,
        sort=0,
        create_by=str(user.id),
        update_by=str(user.id),
        create_time=now,
        update_time=now,
        delete_flag=0,
        version=source.version or 3,
        content_id="0",
        check_version=source.check_version or "1",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return _dashboard_base_response(
        session,
        user,
        record,
        None,
        platform_template_context=True,
    )


def list_platform_dashboard_templates(session: SessionDep, user: CurrentUser):
    if not (_is_platform_admin_context(user) or is_platform_workspace_delegate(user)):
        raise HTTPException(status_code=403, detail="Only SaaS admin can list dashboard templates")
    statement = (
        select(CoreDashboard)
        .where(
            and_(
                or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None)),
                CoreDashboard.tenant_id == DEFAULT_TENANT_ID,
                CoreDashboard.source == DASHBOARD_SOURCE_PLATFORM_TEMPLATE,
                CoreDashboard.status == DASHBOARD_STATUS_ACTIVE,
                CoreDashboard.node_type == "leaf",
            )
        )
        .order_by(CoreDashboard.update_time.desc(), CoreDashboard.create_time.desc())
    )
    result = session.exec(statement).scalars().all()
    for record in result:
        _repair_platform_template_snapshot_if_needed(session, record)
    return [
        _dashboard_base_response(
            session,
            user,
            record,
            None,
            platform_template_context=True,
        )
        for record in result
    ]


def load_platform_dashboard_template(
        session: SessionDep,
        user: CurrentUser,
        template_id: str,
        include_data: bool = False,
):
    template = _load_platform_template_or_404(session, template_id, user)
    _repair_platform_template_snapshot_if_needed(session, template)
    return _dashboard_payload(
        session,
        user,
        template,
        dashboard=QueryDashboard(id=template_id, include_data=include_data),
        platform_template_context=True,
        include_data=include_data,
    )


def update_platform_dashboard_template(
        session: SessionDep,
        user: CurrentUser,
        dashboard: CreateDashboard,
):
    if not _is_platform_admin_context(user):
        raise HTTPException(status_code=403, detail="Only SaaS admin can edit dashboard templates")
    template = _load_platform_template_or_404(session, dashboard.id, user)
    if not dashboard.name or not dashboard.name.strip():
        raise HTTPException(status_code=400, detail="Dashboard template name is required")
    duplicate = session.exec(
        select(CoreDashboard.id).where(
            and_(
                or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None)),
                CoreDashboard.tenant_id == DEFAULT_TENANT_ID,
                CoreDashboard.source == DASHBOARD_SOURCE_PLATFORM_TEMPLATE,
                CoreDashboard.status == DASHBOARD_STATUS_ACTIVE,
                CoreDashboard.name == dashboard.name.strip(),
                CoreDashboard.id != template.id,
            )
        )
    ).first()
    if duplicate:
        raise HTTPException(status_code=400, detail="Dashboard template name already exists")
    _clone_dashboard_canvas_payload(
        dashboard.component_data,
        dashboard.canvas_style_data,
        dashboard.canvas_view_info,
    )
    template.name = dashboard.name.strip()
    template.canvas_style_data = dashboard.canvas_style_data or "{}"
    template.component_data = dashboard.component_data or "[]"
    template.canvas_view_info = _prepare_dashboard_template_canvas_view_info(
        _sanitize_canvas_view_info(dashboard.canvas_view_info or "{}")
    )
    template.mobile_layout = getattr(dashboard, "mobile_layout", None) or template.mobile_layout or 0
    template.status = DASHBOARD_STATUS_ACTIVE
    template.source = DASHBOARD_SOURCE_PLATFORM_TEMPLATE
    template.tenant_id = DEFAULT_TENANT_ID
    template.datasource = None
    template.content_id = "0"
    template.node_type = "leaf"
    template.pid = "root"
    template.type = dashboard.type or template.type or "dashboard"
    template.update_by = str(user.id)
    template.update_time = _now()
    session.add(template)
    session.commit()
    session.refresh(template)
    return _dashboard_base_response(
        session,
        user,
        template,
        None,
        platform_template_context=True,
    )


def delete_platform_dashboard_template(
        session: SessionDep,
        user: CurrentUser,
        template_id: str,
):
    if not _is_platform_admin_context(user):
        raise HTTPException(status_code=403, detail="Only SaaS admin can delete dashboard templates")
    template = _load_platform_template_or_404(session, template_id, user)
    template.delete_flag = 1
    template.delete_time = _now()
    template.delete_by = _user_id(user)
    session.add(template)
    session.commit()
    return True


def copy_platform_template_to_workspace_dashboard(
        session: SessionDep,
        user: CurrentUser,
        template_id: str,
        name: str = "",
):
    _require_platform_delegate(user)
    template = _load_platform_template_or_404(session, template_id, user)
    _repair_platform_template_snapshot_if_needed(session, template)
    target_datasource_id = get_bound_datasource_id_for_tenant(session, _current_tenant_id(user))
    if target_datasource_id is not None:
        _ensure_datasource_access(session, user, target_datasource_id, required=True)
    component_data, canvas_style_data, canvas_view_info = _clone_dashboard_canvas_payload_for_datasource(
        template.component_data,
        template.canvas_style_data,
        template.canvas_view_info,
        target_datasource_id,
    )
    now = _now()
    operator_id = _asset_operator_id(session, user)
    record = CoreDashboard(
        id=uuid.uuid4().hex,
        tenant_id=_current_tenant_id(user),
        name=(name or template.name or "").strip() or template.name,
        pid="root",
        datasource=target_datasource_id,
        org_id=template.org_id or "",
        level=1,
        node_type="leaf",
        type=template.type or "dashboard",
        canvas_style_data=canvas_style_data,
        component_data=component_data,
        canvas_view_info=canvas_view_info,
        mobile_layout=template.mobile_layout or 0,
        status=DASHBOARD_STATUS_ACTIVE,
        source=None,
        remark=f"source_template_id={template.id}",
        self_watermark_status=template.self_watermark_status or 0,
        is_default=0,
        sort=0,
        create_by=operator_id,
        update_by=operator_id,
        create_time=now,
        update_time=now,
        delete_flag=0,
        version=template.version or 3,
        content_id="0",
        check_version=template.check_version or "1",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return _dashboard_base_response(session, user, record, target_datasource_id)


def validate_name(session: SessionDep,user: CurrentUser,  dashboard: QueryDashboard) -> bool:
    if not dashboard.opt:
        raise ValueError("opt is required")
    datasource_id = _normalize_datasource_id(dashboard.datasource)


    if dashboard.opt in ('newLeaf', 'newFolder'):
        is_default_folder = bool(dashboard.is_default) and dashboard.node_type == "folder"
        if is_default_folder:
            _require_set_default_permission(user)
            datasource_id = None
            if dashboard.pid and dashboard.pid != "root":
                parent = _load_dashboard_or_404(session, dashboard.pid, user)
                if parent.node_type != "folder" or not parent.is_default:
                    raise HTTPException(status_code=400, detail="Default dashboard parent must be recommended folder")
        else:
            datasource_id = _ensure_datasource_access(session, user, datasource_id, required=True)
            _require_create_permission(session, user, datasource_id, dashboard.pid)
        duplicate_filters = [
            CoreDashboard.tenant_id == _current_tenant_id(user),
            CoreDashboard.is_default == (1 if is_default_folder else 0),
            or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None)),
            CoreDashboard.name == dashboard.name,
        ]
        if not is_default_folder:
            duplicate_filters.append(
                CoreDashboard.datasource.is_(None)
                if datasource_id is None
                else CoreDashboard.datasource == datasource_id
            )
        query = session.query(CoreDashboard).filter(and_(*duplicate_filters))
    elif dashboard.opt in ('updateLeaf', 'updateFolder', 'rename'):
        if not dashboard.id:
            raise ValueError("id is required for update operation")
        record = _load_dashboard_or_404(session, dashboard.id, user)
        _require_edit_permission(session, user, record)
        if dashboard.name == record.name:
            return True
        datasource_id = record.datasource or datasource_id
        query = session.query(CoreDashboard).filter(
            and_(
                CoreDashboard.tenant_id == _current_tenant_id(user),
                CoreDashboard.datasource == datasource_id,
                or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None)),
                CoreDashboard.name == dashboard.name,
                CoreDashboard.id != dashboard.id
            )
        )
    else:
        raise ValueError(f"Invalid opt value: {dashboard.opt}")
    return not session.query(query.exists()).scalar()


def delete_resource(session: SessionDep, current_user: CurrentUser, resource_id: str):
    coreDashboard = _load_dashboard_or_404(session, resource_id, current_user)
    _require_edit_permission(session, current_user, coreDashboard)
    if coreDashboard.datasource:
        _ensure_datasource_access(session, current_user, coreDashboard.datasource)
    if coreDashboard.is_default:
        _require_set_default_permission(current_user)
    sql = text("DELETE FROM core_dashboard WHERE id = :resource_id AND tenant_id = :tenant_id")
    result = session.execute(sql, {"resource_id": resource_id, "tenant_id": _current_tenant_id(current_user)})
    session.commit()
    return result.rowcount > 0


def preview_sql(session: SessionDep, current_user: CurrentUser, request: DashboardSqlPreview):
    if not request.sql or not request.sql.strip():
        return {
            "status": "failed",
            "fields": [],
            "data": [],
            "message": "SQL不能为空",
        }
    datasource_id = _ensure_datasource_access(session, current_user, request.datasource, required=True)
    if datasource_id is None:
        return _failed_chart_result("Dashboard datasource is required")
    normalized_sql = request.sql.strip()
    cache_key = _dashboard_sql_preview_cache_key(
        current_user=current_user,
        datasource_id=datasource_id,
        sql=normalized_sql,
        pivot=request.pivot,
    )
    cached = _dashboard_sql_preview_cache_get(cache_key)
    if cached is not None:
        return cached
    if request.cache_only:
        return _failed_chart_result("看板缓存未命中", "dashboard_cache_miss")

    inflight_lock = _dashboard_sql_preview_inflight_lock(cache_key)
    if not inflight_lock.acquire(timeout=_dashboard_sql_preview_dedupe_wait_timeout()):
        cached = _dashboard_sql_preview_cache_get(cache_key, allow_expired=True)
        if cached is not None:
            return cached
        return _failed_chart_result(DASHBOARD_SQL_PREVIEW_BUSY_MESSAGE, "dashboard_query_busy")

    datasource_semaphore = _dashboard_sql_preview_datasource_semaphore(datasource_id)
    datasource_acquired = False
    try:
        cached = _dashboard_sql_preview_cache_get(cache_key)
        if cached is not None:
            return cached
        datasource_acquired = datasource_semaphore.acquire(timeout=_dashboard_sql_preview_wait_timeout())
        if not datasource_acquired:
            cached = _dashboard_sql_preview_cache_get(cache_key, allow_expired=True)
            if cached is not None:
                return cached
            AppLogUtil.warning(f"Dashboard SQL preview busy: datasource={datasource_id}")
            return _failed_chart_result(DASHBOARD_SQL_PREVIEW_BUSY_MESSAGE, "dashboard_query_busy")

        result = _execute_dashboard_chart_sql(
            session,
            current_user,
            datasource_id,
            normalized_sql,
            request.pivot,
        )
        _dashboard_sql_preview_cache_set(cache_key, result)
        return result
    finally:
        if datasource_acquired:
            datasource_semaphore.release()
        inflight_lock.release()
        _dashboard_sql_preview_release_inflight_lock(cache_key, inflight_lock)


def share_resource(session: SessionDep, user: CurrentUser, request: DashboardShareRequest):
    record = _load_dashboard_or_404(session, request.dashboard_id, user)
    _require_share_permission(session, user, record)
    datasource_id = _effective_dashboard_datasource(record)
    if datasource_id is not None:
        _ensure_datasource_access(session, user, datasource_id)

    share_id = uuid.uuid4().hex
    share_name = (request.name or "").strip()
    if request.share_type == "chart":
        component_data, canvas_style_data, canvas_view_info = _share_chart_snapshot(
            record,
            request.source_view_id,
        )
        if not share_name:
            view_info = _parse_canvas_view_info(canvas_view_info).get(request.source_view_id, {})
            share_name = view_info.get("chart", {}).get("title") or record.name
    else:
        component_data = record.component_data or "[]"
        canvas_style_data = record.canvas_style_data or "{}"
        canvas_view_info = record.canvas_view_info or "{}"
        if not share_name:
            share_name = record.name

    now = int(time.time())
    operator_id = _asset_operator_id(session, user)
    share = _active_share_for_source(
        session,
        user,
        request.share_type,
        record.id,
        request.source_view_id or None,
    )
    if share:
        share.name = share_name
        share.datasource = datasource_id
        share.source_view_id = request.source_view_id or None
        share.component_data = component_data
        share.canvas_style_data = canvas_style_data
        share.canvas_view_info = canvas_view_info
        share.preview_image = request.preview_image or share.preview_image
        share.update_by = operator_id
        share.update_time = now
        share.delete_flag = 0
    else:
        share = CoreDashboardShare(
            id=share_id,
            tenant_id=_current_tenant_id(user),
            name=share_name,
            datasource=datasource_id,
            share_type=request.share_type,
            source_dashboard_id=record.id,
            source_view_id=request.source_view_id or None,
            component_data=component_data,
            canvas_style_data=canvas_style_data,
            canvas_view_info=canvas_view_info,
            preview_image=request.preview_image or None,
            create_by=operator_id,
            update_by=operator_id,
            create_time=now,
            update_time=now,
            delete_flag=0,
        )
    session.add(share)
    session.commit()
    session.refresh(share)
    return share


def list_shared_resources(session: SessionDep, current_user: CurrentUser, query: DashboardShareListQuery):
    filters = [
        _active_share_filter(),
        CoreDashboardShare.tenant_id == _current_tenant_id(current_user),
        _active_workspace_member_share_creator_filter(current_user),
    ]
    keyword = (query.keyword or "").strip()
    if keyword:
        filters.append(CoreDashboardShare.name.ilike(f"%{keyword}%"))

    statement = (
        select(CoreDashboardShare)
        .where(and_(*filters))
        .order_by(CoreDashboardShare.update_time.desc(), CoreDashboardShare.create_time.desc())
    )
    result = session.exec(statement).scalars().all()
    items = []
    seen_keys = set()
    for share in result:
        share_key = _share_source_key(share)
        if share_key in seen_keys:
            continue
        seen_keys.add(share_key)
        datasource_id = _normalize_datasource_id(share.datasource)
        items.append({
            "id": share.id,
            "tenant_id": share.tenant_id,
            "name": share.name,
            "datasource": datasource_id,
            "datasource_name": _datasource_name(session, datasource_id),
            "share_type": share.share_type,
            "source_dashboard_id": share.source_dashboard_id,
            "source_view_id": share.source_view_id,
            "preview_image": share.preview_image,
            "create_time": share.create_time,
            "update_time": share.update_time,
            "create_name": _user_name(session, share.create_by),
            "update_name": _user_name(session, share.update_by),
            "can_use": _share_can_use(session, current_user, share),
            "can_delete": _share_can_delete(current_user, share),
        })
    return items


def load_shared_resource(session: SessionDep, current_user: CurrentUser, query: SharedDashboardQuery):
    share = _load_shared_dashboard_or_404(session, query.id, current_user)
    return _load_share_preview_payload(session, current_user, share)


def delete_shared_resource(session: SessionDep, current_user: CurrentUser, query: SharedDashboardQuery):
    share = _load_shared_dashboard_or_404(session, query.id, current_user)
    if not _share_can_delete(current_user, share):
        raise HTTPException(status_code=403, detail="You do not have permission to delete this shared dashboard")
    now = int(time.time())
    operator_id = _asset_operator_id(session, current_user)
    for active_share in _active_shares_for_same_source(session, share):
        active_share.delete_flag = 1
        active_share.delete_time = now
        active_share.delete_by = operator_id
        session.add(active_share)
    session.commit()
    return True


def use_shared_resource(session: SessionDep, user: CurrentUser, request: SharedDashboardUseRequest):
    share = _load_shared_dashboard_or_404(session, request.id, user)
    datasource_id = _normalize_datasource_id(share.datasource)
    if datasource_id is None or not _share_can_use(session, user, share):
        raise HTTPException(status_code=403, detail="You do not have permission to use this shared dashboard")

    operator_id = _asset_operator_id(session, user)
    record = CoreDashboard(
        id=uuid.uuid4().hex,
        tenant_id=_current_tenant_id(user),
        name=share.name,
        pid="root",
        datasource=datasource_id,
        org_id="",
        level=1,
        node_type="leaf",
        type="dashboard",
        canvas_style_data=share.canvas_style_data or "{}",
        component_data=share.component_data or "[]",
        canvas_view_info=share.canvas_view_info or "{}",
        create_by=operator_id,
        update_by=operator_id,
        create_time=int(time.time()),
        update_time=int(time.time()),
        delete_flag=0,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record
