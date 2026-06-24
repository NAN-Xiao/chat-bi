from typing import Any

from fastapi import HTTPException
from orjson import orjson
from sqlalchemy import String, cast, select, and_, or_, text, func, inspect

from apps.dashboard.models.dashboard_model import (
    CoreDashboard,
    CoreDashboardShare,
    CreateDashboard,
    QueryDashboard,
    DashboardBaseResponse,
    DashboardDefaultCopyRequest,
    DashboardDefaultRequest,
    DashboardDefaultSortRequest,
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
from apps.system.schemas.access_context import can_manage_workspace_scope, require_current_tenant_id
from apps.system.models.user import UserModel
from apps.system.models.tenant import TenantUserModel
from apps.system.crud.user import is_platform_workspace_delegate, is_system_admin
from common.core.deps import SessionDep, CurrentUser
from common.utils.chart_config import sanitize_chart_display_names
import uuid
import time

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


def _sanitize_canvas_view_info(canvas_view_info: str | bytes | None) -> str | bytes | None:
    if not canvas_view_info:
        return canvas_view_info
    try:
        canvas_view_obj = orjson.loads(canvas_view_info)
    except Exception:
        return canvas_view_info
    return orjson.dumps(sanitize_chart_display_names(canvas_view_obj)).decode()


def _user_id(current_user: CurrentUser) -> str:
    return str(current_user.id)


def _now() -> int:
    return int(time.time())


DEFAULT_TENANT_ID = 1
DASHBOARD_STATUS_ACTIVE = 1
DASHBOARD_STATUS_DELIVERY_DRAFT = 2
DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT = 3
DASHBOARD_DRAFT_STATUSES = {
    DASHBOARD_STATUS_DELIVERY_DRAFT,
    DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT,
}
DASHBOARD_SOURCE_PLATFORM_DELEGATE = "platform_delegate"
DASHBOARD_SOURCE_PLATFORM_TEMPLATE = "platform_template"


def _current_tenant_id(current_user: CurrentUser | None) -> int:
    return require_current_tenant_id(current_user)


def _same_tenant(current_user: CurrentUser | None, record) -> bool:
    return int(getattr(record, "tenant_id")) == _current_tenant_id(current_user)


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
    return or_(
        CoreDashboard.is_default == 1,
        CoreDashboard.create_by == _user_id(current_user),
        CoreDashboard.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE,
    )


def _is_public_dashboard_for_delegate(session: SessionDep, current_user: CurrentUser, dashboard: CoreDashboard) -> bool:
    if dashboard.is_default:
        return True
    if dashboard.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE and dashboard.status != DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT:
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
        if dashboard.status == DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT:
            return str(dashboard.create_by) == _user_id(current_user)
        return (
            str(dashboard.create_by) == _user_id(current_user)
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
        return (
            str(dashboard.create_by) == _user_id(current_user)
            or dashboard.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE
            or bool(dashboard.is_default)
        )
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
        if dashboard.status == DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT:
            return str(dashboard.create_by) == _user_id(current_user)
        return (
            bool(dashboard.is_default)
            or str(dashboard.create_by) == _user_id(current_user)
            or dashboard.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE
        )
    if dashboard.is_default:
        return True
    if _is_published_workspace_dashboard(dashboard) and (is_system_admin(current_user) or _can_set_default_dashboard(current_user)):
        return True
    if str(dashboard.create_by) == _user_id(current_user):
        return True
    return False


def _can_access_platform_delegate_draft(current_user: CurrentUser | None, dashboard: CoreDashboard) -> bool:
    return (
        current_user is not None
        and is_platform_workspace_delegate(current_user)
        and dashboard.status == DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT
        and dashboard.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE
        and _same_tenant(current_user, dashboard)
        and str(dashboard.create_by) == _user_id(current_user)
    )


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


def _load_platform_delegate_draft_or_404(
        session: SessionDep,
        dashboard_id: str,
        current_user: CurrentUser,
) -> CoreDashboard:
    record = session.get(CoreDashboard, dashboard_id)
    if not record or record.delete_flag == 1 or not _can_access_platform_delegate_draft(current_user, record):
        raise HTTPException(status_code=404, detail="Dashboard draft does not exist")
    return record


def _load_platform_template_or_404(
        session: SessionDep,
        template_id: str,
        current_user: CurrentUser,
) -> CoreDashboard:
    _require_platform_delegate(current_user)
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


def _execute_dashboard_chart_sql(
        session: SessionDep,
        current_user: CurrentUser,
        datasource_id: int,
        sql: str,
) -> dict[str, Any]:
    return execute_user_query(
        session=session,
        current_user=current_user,
        datasource_id=datasource_id,
        sql=sql,
        origin_column=True,
    )


def _clear_dashboard_chart_data(item: dict) -> None:
    if not isinstance(item.get('data'), dict):
        item['data'] = {}
    item['data']['data'] = []
    item['data']['fields'] = []
    item['fields'] = []
    item['status'] = 'loading'
    item['message'] = ''


def _clear_dashboard_payload_results(canvas_view_info: str | bytes | None) -> str:
    canvas_view_obj = _parse_canvas_view_info(canvas_view_info)
    for item in canvas_view_obj.values():
        if isinstance(item, dict):
            _clear_dashboard_chart_data(item)
    return orjson.dumps(canvas_view_obj).decode()


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
) -> DashboardBaseResponse:
    return DashboardBaseResponse(
        id=record.id,
        tenant_id=record.tenant_id,
        name=record.name,
        pid=record.pid,
        datasource=record.datasource if datasource is None else datasource,
        node_type=record.node_type,
        leaf=record.node_type == 'leaf',
        type=record.type,
        status=record.status,
        source=record.source,
        content_id=record.content_id,
        create_time=record.create_time,
        update_time=record.update_time,
        sort=record.sort or 0,
        can_edit=_can_edit_dashboard(session, current_user, record),
        can_share=_can_share_dashboard(session, current_user, record),
        can_set_default=_can_set_default_dashboard(current_user),
        is_default=bool(record.is_default),
        is_shared=active_share is not None,
        is_public=bool(record.is_default or active_share is not None or record.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE),
        is_platform_delegate_draft=record.status == DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT,
        can_publish_delegate_draft=(
            is_platform_workspace_delegate(current_user)
            and record.status == DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT
            and str(record.create_by) == _user_id(current_user)
        ),
        can_create_maintenance_draft=(
            is_platform_workspace_delegate(current_user)
            and record.node_type == "leaf"
            and record.status != DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT
            and _can_edit_dashboard(session, current_user, record)
        ),
        can_copy_to_platform_template=(
            is_platform_workspace_delegate(current_user)
            and record.node_type == "leaf"
            and record.status != DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT
            and _is_public_dashboard_for_delegate(session, current_user, record)
        ),
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
    filters = [_active_dashboard_filter(), CoreDashboard.tenant_id == _current_tenant_id(current_user)]
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

    statement = select(CoreDashboard).where(and_(*filters)).order_by(CoreDashboard.create_time.desc())
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
    tree = build_tree_generic(nodes, root_pid="root")
    return tree


def _dashboard_payload(
        session: SessionDep,
        current_user: CurrentUser,
        record: CoreDashboard,
        *,
        dashboard: QueryDashboard | None = None,
        default_context: bool = False,
        include_data: bool = True,
):
    effective_datasource = _effective_dashboard_datasource(record)
    if dashboard is not None and dashboard.datasource is not None and effective_datasource is not None:
        request_datasource = _normalize_datasource_id(dashboard.datasource)
        if request_datasource != effective_datasource:
            raise HTTPException(status_code=403, detail="Dashboard does not belong to the selected datasource")
    if effective_datasource is not None and not default_context:
        _ensure_datasource_access(session, current_user, effective_datasource)
    elif effective_datasource is None and not default_context:
        _check_dashboard_view_permission(session, current_user, record)

    result_dict = record.model_dump()
    result_dict['datasource'] = effective_datasource
    creator = _user_name(session, record.create_by)
    updater = _user_name(session, record.update_by)
    result_dict['create_name'] = creator
    result_dict['update_name'] = updater
    result_dict['can_edit'] = _can_edit_dashboard(session, current_user, record)
    result_dict['can_share'] = _can_share_dashboard(session, current_user, record)
    result_dict['can_set_default'] = _can_set_default_dashboard(current_user)
    result_dict['is_default'] = bool(record.is_default)

    canvas_view_obj = _parse_canvas_view_info(result_dict.get('canvas_view_info'))
    for item in canvas_view_obj.values():
        if not isinstance(item, dict):
            continue
        item_datasource = _chart_datasource(record, item, effective_datasource)
        if item.get('sql') is not None:
            if not include_data:
                _clear_dashboard_chart_data(item)
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
                data_result = _execute_dashboard_chart_sql(session, current_user, item_datasource, item['sql'])
            if not isinstance(item.get('data'), dict):
                item['data'] = {}
            item['data']['data'] = data_result['data']
            item['status'] = data_result['status']
            item['message'] = data_result['message']
            item['fields'] = data_result.get('fields', [])
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
                CoreDashboard.node_type == "leaf",
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
    return nodes


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
    return record


def get_create_base_info(user: CurrentUser, dashboard: CreateDashboard):
    new_id = uuid.uuid4().hex
    record = CoreDashboard(**dashboard.model_dump(exclude={"include_data"}))
    record.id = new_id
    record.tenant_id = _current_tenant_id(user)
    record.create_by = str(user.id)
    record.create_time = _now()
    return record


def _mark_platform_delegate_draft(record: CoreDashboard, user: CurrentUser):
    record.status = DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT
    record.source = DASHBOARD_SOURCE_PLATFORM_DELEGATE
    record.is_default = 0
    record.sort = 0
    record.create_by = str(user.id)
    record.update_by = str(user.id)


def create_resource(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    dashboard.datasource = _ensure_datasource_access(session, user, dashboard.datasource, required=True)
    _require_create_permission(session, user, dashboard.datasource, dashboard.pid)
    record = get_create_base_info(user, dashboard)
    if is_platform_workspace_delegate(user):
        _mark_platform_delegate_draft(record, user)
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
    record.update_by = str(user.id)
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
        _mark_platform_delegate_draft(record, user)
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
    record.update_by = str(user.id)
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
    record.update_by = str(user.id)
    record.update_time = _now()
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def list_platform_delegate_drafts(session: SessionDep, current_user: CurrentUser):
    _require_platform_delegate(current_user)
    statement = (
        select(CoreDashboard)
        .where(
            and_(
                or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None)),
                CoreDashboard.tenant_id == _current_tenant_id(current_user),
                CoreDashboard.status == DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT,
                CoreDashboard.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE,
                CoreDashboard.create_by == _user_id(current_user),
            )
        )
        .order_by(CoreDashboard.update_time.desc(), CoreDashboard.create_time.desc())
    )
    result = session.exec(statement).scalars().all()
    return [
        _dashboard_base_response(session, current_user, record, _effective_dashboard_datasource(record))
        for record in result
    ]


def load_platform_delegate_draft(session: SessionDep, dashboard: QueryDashboard, current_user: CurrentUser):
    record = _load_platform_delegate_draft_or_404(session, dashboard.id, current_user)
    return _dashboard_payload(
        session,
        current_user,
        record,
        dashboard=dashboard,
        include_data=dashboard.include_data,
    )


def update_platform_delegate_draft(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    record = _load_platform_delegate_draft_or_404(session, dashboard.id, user)
    request_datasource = _normalize_datasource_id(dashboard.datasource)
    bound_datasource = record.datasource or request_datasource
    if request_datasource is not None and record.datasource is not None and request_datasource != record.datasource:
        raise HTTPException(status_code=400, detail="Dashboard datasource cannot be changed")
    if bound_datasource is not None:
        _ensure_datasource_access(session, user, bound_datasource)
    _validate_canvas_datasources(session, user, dashboard, bound_datasource)
    record.name = dashboard.name
    record.datasource = bound_datasource
    record.pid = dashboard.pid or record.pid or "root"
    record.node_type = dashboard.node_type or record.node_type or "leaf"
    record.type = dashboard.type or record.type or "dashboard"
    record.update_by = str(user.id)
    record.update_time = _now()
    record.component_data = dashboard.component_data
    record.canvas_style_data = dashboard.canvas_style_data
    record.canvas_view_info = _sanitize_canvas_view_info(dashboard.canvas_view_info)
    record.status = DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT
    record.source = DASHBOARD_SOURCE_PLATFORM_DELEGATE
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def create_platform_delegate_maintenance_draft(
        session: SessionDep,
        user: CurrentUser,
        dashboard_id: str,
):
    _require_platform_delegate(user)
    source = _load_dashboard_or_404(session, dashboard_id, user)
    if source.node_type != "leaf":
        raise HTTPException(status_code=400, detail="Dashboard maintenance draft must come from a dashboard")
    if not _can_edit_dashboard(session, user, source):
        raise HTTPException(status_code=404, detail="Dashboard does not exist")

    existing = session.exec(
        select(CoreDashboard)
        .where(
            and_(
                or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None)),
                CoreDashboard.tenant_id == _current_tenant_id(user),
                CoreDashboard.status == DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT,
                CoreDashboard.source == DASHBOARD_SOURCE_PLATFORM_DELEGATE,
                CoreDashboard.create_by == _user_id(user),
                CoreDashboard.content_id == source.id,
            )
        )
        .order_by(CoreDashboard.update_time.desc(), CoreDashboard.create_time.desc())
    ).scalars().first()
    if existing:
        return _dashboard_base_response(session, user, existing, _effective_dashboard_datasource(existing))

    component_data, canvas_style_data, canvas_view_info = _clone_dashboard_canvas_payload(
        source.component_data,
        source.canvas_style_data,
        source.canvas_view_info,
    )
    now = _now()
    record = CoreDashboard(
        id=uuid.uuid4().hex,
        tenant_id=_current_tenant_id(user),
        name=source.name,
        pid=source.pid or "root",
        datasource=_effective_dashboard_datasource(source),
        org_id=source.org_id or "",
        level=source.level or 1,
        node_type="leaf",
        type=source.type or "dashboard",
        canvas_style_data=canvas_style_data,
        component_data=component_data,
        canvas_view_info=canvas_view_info,
        mobile_layout=source.mobile_layout or 0,
        status=DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT,
        source=DASHBOARD_SOURCE_PLATFORM_DELEGATE,
        remark="maintenance_draft",
        content_id=source.id,
        self_watermark_status=source.self_watermark_status or 0,
        is_default=0,
        sort=0,
        create_by=str(user.id),
        update_by=str(user.id),
        create_time=now,
        update_time=now,
        delete_flag=0,
        version=source.version or 3,
        check_version=source.check_version or "1",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return _dashboard_base_response(session, user, record, _effective_dashboard_datasource(record))


def publish_platform_delegate_draft(
        session: SessionDep,
        user: CurrentUser,
        draft_dashboard_id: str,
        publish_as_default: bool = False,
):
    draft = _load_platform_delegate_draft_or_404(session, draft_dashboard_id, user)
    if draft.node_type != "leaf":
        raise HTTPException(status_code=400, detail="Only dashboard drafts can be published")

    datasource_id = _effective_dashboard_datasource(draft)
    if datasource_id is not None:
        if not datasource_bound_to_tenant(session, int(datasource_id), _current_tenant_id(user)):
            raise HTTPException(status_code=403, detail="Dashboard datasource is not in current workspace")
        _ensure_datasource_access(session, user, datasource_id, required=True)

    now = _now()
    target: CoreDashboard | None = None
    if draft.content_id and draft.content_id != "0":
        candidate = session.get(CoreDashboard, draft.content_id)
        if (
            candidate
            and candidate.delete_flag != 1
            and candidate.status not in DASHBOARD_DRAFT_STATUSES
            and _same_tenant(user, candidate)
            and _can_edit_dashboard(session, user, candidate)
        ):
            target = candidate
        else:
            raise HTTPException(status_code=404, detail="Published dashboard does not exist")

    if target is None:
        target = CoreDashboard(
            id=uuid.uuid4().hex,
            tenant_id=_current_tenant_id(user),
            create_by=str(user.id),
            create_time=now,
            delete_flag=0,
        )

    target.name = draft.name
    target.pid = draft.pid or "root"
    target.datasource = datasource_id
    target.org_id = draft.org_id or ""
    target.level = draft.level or 1
    target.node_type = "leaf"
    target.type = draft.type or "dashboard"
    target.canvas_style_data = draft.canvas_style_data or "{}"
    target.component_data = draft.component_data or "[]"
    target.canvas_view_info = draft.canvas_view_info or "{}"
    target.mobile_layout = draft.mobile_layout or 0
    target.status = DASHBOARD_STATUS_ACTIVE
    target.source = DASHBOARD_SOURCE_PLATFORM_DELEGATE
    target.remark = "created_via=platform_delegate;owner_scope=workspace"
    target.self_watermark_status = draft.self_watermark_status or 0
    target.version = draft.version or 3
    target.content_id = draft.content_id if draft.content_id and draft.content_id != "0" else "0"
    target.check_version = draft.check_version or "1"
    target.update_by = str(user.id)
    target.update_time = now

    if publish_as_default and not target.is_default:
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
        target.sort = int(_first_scalar_value(max_sort_row) or 0) + 1
    target.is_default = 1 if publish_as_default else 0

    draft.delete_flag = 1
    draft.delete_time = now
    draft.delete_by = str(user.id)
    draft.update_by = str(user.id)
    draft.update_time = now
    session.add(target)
    session.add(draft)
    session.commit()
    session.refresh(target)
    return _dashboard_base_response(session, user, target, datasource_id)


def delete_platform_delegate_draft(session: SessionDep, user: CurrentUser, draft_dashboard_id: str):
    draft = _load_platform_delegate_draft_or_404(session, draft_dashboard_id, user)
    now = _now()
    draft.delete_flag = 1
    draft.delete_time = now
    draft.delete_by = str(user.id)
    draft.update_by = str(user.id)
    draft.update_time = now
    session.add(draft)
    session.commit()
    return True


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
    record.is_default = 1 if request.is_default else 0
    record.update_by = str(user.id)
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
    for index, dashboard_id in enumerate(ordered_ids):
        record = record_by_id[dashboard_id]
        record.sort = index + 1
        record.update_by = str(user.id)
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
    canvas_view_info = _clear_dashboard_payload_results(canvas_view_info)
    now = _now()
    record = CoreDashboard(
        id=uuid.uuid4().hex,
        tenant_id=DEFAULT_TENANT_ID,
        name=(name or source.name or "").strip() or source.name,
        pid="root",
        datasource=_effective_dashboard_datasource(source),
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
        content_id=source.id,
        check_version=source.check_version or "1",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return _dashboard_base_response(session, user, record, _effective_dashboard_datasource(record))


def list_platform_dashboard_templates(session: SessionDep, user: CurrentUser):
    _require_platform_delegate(user)
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
    return [
        _dashboard_base_response(session, user, record, _effective_dashboard_datasource(record))
        for record in result
    ]


def copy_platform_template_to_delegate_draft(
        session: SessionDep,
        user: CurrentUser,
        template_id: str,
        name: str = "",
):
    template = _load_platform_template_or_404(session, template_id, user)
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
        status=DASHBOARD_STATUS_PLATFORM_DELEGATE_DRAFT,
        source=DASHBOARD_SOURCE_PLATFORM_DELEGATE,
        remark=f"source_template_id={template.id}",
        self_watermark_status=template.self_watermark_status or 0,
        is_default=0,
        sort=0,
        create_by=str(user.id),
        update_by=str(user.id),
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
        datasource_id = _ensure_datasource_access(session, user, datasource_id, required=True)
        _require_create_permission(session, user, datasource_id, dashboard.pid)
        query = session.query(CoreDashboard).filter(
            and_(
                CoreDashboard.tenant_id == _current_tenant_id(user),
                CoreDashboard.datasource == datasource_id,
                or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None)),
                CoreDashboard.name == dashboard.name
            )
        )
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
    return _execute_dashboard_chart_sql(session, current_user, request.datasource, request.sql)


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
        share.update_by = str(user.id)
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
            create_by=str(user.id),
            update_by=str(user.id),
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
    for active_share in _active_shares_for_same_source(session, share):
        active_share.delete_flag = 1
        active_share.delete_time = now
        active_share.delete_by = _user_id(current_user)
        session.add(active_share)
    session.commit()
    return True


def use_shared_resource(session: SessionDep, user: CurrentUser, request: SharedDashboardUseRequest):
    share = _load_shared_dashboard_or_404(session, request.id, user)
    datasource_id = _normalize_datasource_id(share.datasource)
    if datasource_id is None or not _share_can_use(session, user, share):
        raise HTTPException(status_code=403, detail="You do not have permission to use this shared dashboard")

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
        create_by=str(user.id),
        update_by=str(user.id),
        create_time=int(time.time()),
        update_time=int(time.time()),
        delete_flag=0,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record
