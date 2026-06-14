import base64

from fastapi import HTTPException
from orjson import orjson
from sqlalchemy import select, and_, or_, text

from apps.chat.curd.chat import get_chart_data_ds
from apps.dashboard.models.dashboard_model import CoreDashboard, CreateDashboard, QueryDashboard, DashboardBaseResponse, \
    DashboardSqlPreview
from apps.datasource.crud.permission import get_accessible_datasource_ids, has_datasource_access
from apps.datasource.models.datasource import CoreDatasource
from apps.system.models.user import UserModel
from common.core.deps import SessionDep, CurrentUser
import uuid
import time

from common.utils.tree_utils import build_tree_generic


def _user_id(current_user: CurrentUser) -> str:
    return str(current_user.id)


def _can_edit_dashboard(current_user: CurrentUser, dashboard: CoreDashboard) -> bool:
    return bool(current_user.isAdmin)


def _can_view_legacy_dashboard(current_user: CurrentUser, dashboard: CoreDashboard) -> bool:
    return bool(current_user.isAdmin) or str(dashboard.create_by) == _user_id(current_user)


def _require_create_permission(current_user: CurrentUser):
    if not current_user.isAdmin:
        raise HTTPException(status_code=403, detail="Only project administrators can maintain dashboards")


def _require_edit_permission(current_user: CurrentUser, dashboard: CoreDashboard):
    if not _can_edit_dashboard(current_user, dashboard):
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


def _load_dashboard_or_404(session: SessionDep, dashboard_id: str) -> CoreDashboard:
    record = session.get(CoreDashboard, dashboard_id)
    if not record or record.delete_flag == 1:
        raise HTTPException(status_code=404, detail="Dashboard does not exist")
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


def _dashboard_base_response(current_user: CurrentUser, record: CoreDashboard,
                             datasource: int | None = None) -> DashboardBaseResponse:
    return DashboardBaseResponse(
        id=record.id,
        name=record.name,
        pid=record.pid,
        datasource=record.datasource if datasource is None else datasource,
        node_type=record.node_type,
        leaf=record.node_type == 'leaf',
        type=record.type,
        create_time=record.create_time,
        update_time=record.update_time,
        can_edit=_can_edit_dashboard(current_user, record),
    )


def list_resource(session: SessionDep, dashboard: QueryDashboard, current_user: CurrentUser):
    active_filter = or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None))
    filters = [active_filter]
    datasource_id = _normalize_datasource_id(dashboard.datasource)
    if datasource_id is not None:
        _ensure_datasource_access(session, current_user, datasource_id)
    elif not current_user.isAdmin:
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
    nodes = [_dashboard_base_response(current_user, record, datasource_id) for record in result]
    tree = build_tree_generic(nodes, root_pid="root")
    return tree


def load_resource(session: SessionDep, dashboard: QueryDashboard, current_user: CurrentUser):
    record = _load_dashboard_or_404(session, dashboard.id)
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
    result_dict['can_edit'] = _can_edit_dashboard(current_user, record)

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
            elif not has_datasource_access(session, current_user, item_datasource):
                data_result = {
                    'status': 'failed',
                    'data': [],
                    'fields': [],
                    'message': 'You do not have permission to access this datasource',
                }
            else:
                data_result = get_chart_data_ds(session, item_datasource, item['sql'])
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
    record.create_by = str(user.id)
    record.create_time = int(time.time())
    return record


def create_resource(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    _require_create_permission(user)
    dashboard.datasource = _ensure_datasource_access(session, user, dashboard.datasource, required=True)
    record = get_create_base_info(user, dashboard)
    session.add(record)
    session.flush()
    session.refresh(record)
    session.commit()
    return record


def update_resource(session: SessionDep, user: CurrentUser, dashboard: QueryDashboard):
    record = _load_dashboard_or_404(session, dashboard.id)
    _require_edit_permission(user, record)
    if record.datasource:
        _ensure_datasource_access(session, user, record.datasource)
    record.name = dashboard.name
    record.update_by = str(user.id)
    record.update_time = int(time.time())
    session.add(record)
    session.commit()
    return record


def create_canvas(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    _require_create_permission(user)
    dashboard.datasource = _ensure_datasource_access(session, user, dashboard.datasource, required=True)
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
    return record


def update_canvas(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    record = _load_dashboard_or_404(session, dashboard.id)
    _require_edit_permission(user, record)
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
    return record


def validate_name(session: SessionDep,user: CurrentUser,  dashboard: QueryDashboard) -> bool:
    if not dashboard.opt:
        raise ValueError("opt is required")
    datasource_id = _normalize_datasource_id(dashboard.datasource)


    if dashboard.opt in ('newLeaf', 'newFolder'):
        _require_create_permission(user)
        datasource_id = _ensure_datasource_access(session, user, datasource_id, required=True)
        query = session.query(CoreDashboard).filter(
            and_(
                CoreDashboard.datasource == datasource_id,
                or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None)),
                CoreDashboard.name == dashboard.name
            )
        )
    elif dashboard.opt in ('updateLeaf', 'updateFolder', 'rename'):
        if not dashboard.id:
            raise ValueError("id is required for update operation")
        record = _load_dashboard_or_404(session, dashboard.id)
        _require_edit_permission(user, record)
        datasource_id = record.datasource or datasource_id
        query = session.query(CoreDashboard).filter(
            and_(
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
    coreDashboard = session.get(CoreDashboard, resource_id)
    if not coreDashboard:
        raise ValueError(f"Resource with id {resource_id} does not exist")
    _require_edit_permission(current_user, coreDashboard)
    if coreDashboard.datasource:
        _ensure_datasource_access(session, current_user, coreDashboard.datasource)
    sql = text("DELETE FROM core_dashboard WHERE id = :resource_id")
    result = session.execute(sql, {"resource_id": resource_id})
    session.commit()
    return result.rowcount > 0


def preview_sql(session: SessionDep, request: DashboardSqlPreview):
    if not request.sql or not request.sql.strip():
        return {
            "status": "failed",
            "fields": [],
            "data": [],
            "message": "SQL不能为空",
        }
    return get_chart_data_ds(session, request.datasource, request.sql)
