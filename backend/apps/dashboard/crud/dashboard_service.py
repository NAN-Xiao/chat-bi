from typing import Any

from fastapi import HTTPException
from orjson import orjson
from sqlalchemy import select, and_, or_, text

from apps.dashboard.models.dashboard_model import (
    CoreDashboard,
    CoreDashboardShare,
    CreateDashboard,
    QueryDashboard,
    DashboardBaseResponse,
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
from apps.datasource.crud.query_executor import execute_user_query
from apps.datasource.models.datasource import CoreDatasource
from apps.system.models.user import UserModel
from apps.system.crud.user import is_system_admin
from common.core.deps import SessionDep, CurrentUser
import uuid
import time

from common.utils.tree_utils import build_tree_generic


def _user_id(current_user: CurrentUser) -> str:
    return str(current_user.id)


DEFAULT_TENANT_ID = 1


def _current_tenant_id(current_user: CurrentUser | None) -> int:
    tenant_id = getattr(current_user, "tenant_id", None)
    return int(tenant_id or DEFAULT_TENANT_ID)


def _same_tenant(current_user: CurrentUser | None, record) -> bool:
    return int(getattr(record, "tenant_id", DEFAULT_TENANT_ID) or DEFAULT_TENANT_ID) == _current_tenant_id(current_user)


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


def _can_edit_dashboard(session: SessionDep, current_user: CurrentUser, dashboard: CoreDashboard) -> bool:
    if not _same_tenant(current_user, dashboard):
        return False
    return (
        is_system_admin(current_user)
        or str(dashboard.create_by) == _user_id(current_user)
        or _can_edit_datasource_dashboard(session, current_user, _effective_dashboard_datasource(dashboard))
    )


def _can_view_legacy_dashboard(current_user: CurrentUser, dashboard: CoreDashboard) -> bool:
    if not _same_tenant(current_user, dashboard):
        return False
    return is_system_admin(current_user) or str(dashboard.create_by) == _user_id(current_user)


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
    if not record or record.delete_flag == 1:
        raise HTTPException(status_code=404, detail="Dashboard does not exist")
    if current_user is not None and not _same_tenant(current_user, record):
        _tenant_not_found("Dashboard does not exist")
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
    return record


def _parse_canvas_view_info(canvas_view_info: str | bytes | None) -> dict:
    if not canvas_view_info:
        return {}
    try:
        return orjson.loads(canvas_view_info)
    except Exception:
        return {}


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
        origin_column=False,
    )


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
        str(getattr(share, "tenant_id", DEFAULT_TENANT_ID) or DEFAULT_TENANT_ID),
        str(share.create_by) if share.create_by is not None else None,
        share.share_type,
        share.source_dashboard_id,
        share.source_view_id if share.share_type == "chart" else None,
    )


def _active_shares_for_same_source(session: SessionDep, share: CoreDashboardShare) -> list[CoreDashboardShare]:
    filters = [
        _active_share_filter(),
        CoreDashboardShare.tenant_id == int(share.tenant_id or DEFAULT_TENANT_ID),
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
        create_time=record.create_time,
        update_time=record.update_time,
        can_edit=_can_edit_dashboard(session, current_user, record),
        is_shared=active_share is not None,
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
    active_filter = or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None))
    filters = [active_filter, CoreDashboard.tenant_id == _current_tenant_id(current_user)]
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


def load_resource(session: SessionDep, dashboard: QueryDashboard, current_user: CurrentUser):
    record = _load_dashboard_or_404(session, dashboard.id, current_user)
    effective_datasource = _effective_dashboard_datasource(record)
    if dashboard.datasource is not None and effective_datasource is not None:
        request_datasource = _normalize_datasource_id(dashboard.datasource)
        if request_datasource != effective_datasource:
            raise HTTPException(status_code=403, detail="Dashboard does not belong to the selected datasource")
    if effective_datasource is not None:
        _ensure_datasource_access(session, current_user, effective_datasource)
    else:
        _check_dashboard_view_permission(session, current_user, record)

    result_dict = record.model_dump()
    result_dict['datasource'] = effective_datasource
    creator = _user_name(session, record.create_by)
    updater = _user_name(session, record.update_by)
    result_dict['create_name'] = creator
    result_dict['update_name'] = updater
    result_dict['can_edit'] = _can_edit_dashboard(session, current_user, record)

    canvas_view_obj = _parse_canvas_view_info(result_dict.get('canvas_view_info'))
    for item in canvas_view_obj.values():
        if not isinstance(item, dict):
            continue
        item_datasource = _chart_datasource(record, item, effective_datasource)
        if item_datasource is not None and item.get('sql') is not None:
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


def get_create_base_info(user: CurrentUser, dashboard: CreateDashboard):
    new_id = uuid.uuid4().hex
    record = CoreDashboard(**dashboard.model_dump())
    record.id = new_id
    record.tenant_id = _current_tenant_id(user)
    record.create_by = str(user.id)
    record.create_time = int(time.time())
    return record


def create_resource(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    dashboard.datasource = _ensure_datasource_access(session, user, dashboard.datasource, required=True)
    _require_create_permission(session, user, dashboard.datasource, dashboard.pid)
    record = get_create_base_info(user, dashboard)
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
    record.node_type = dashboard.node_type
    record.component_data = dashboard.component_data
    record.canvas_style_data = dashboard.canvas_style_data
    record.canvas_view_info = dashboard.canvas_view_info
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
    record.canvas_view_info = dashboard.canvas_view_info
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


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
    _require_edit_permission(session, user, record)
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
    filters = [_active_share_filter(), CoreDashboardShare.tenant_id == _current_tenant_id(current_user)]
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
