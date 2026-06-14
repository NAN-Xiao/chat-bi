from typing import Any

from fastapi import HTTPException
from orjson import orjson
from sqlalchemy import select, and_, or_, text
import sqlglot
from sqlglot import exp

from apps.dashboard.models.dashboard_model import CoreDashboard, CreateDashboard, QueryDashboard, DashboardBaseResponse, \
    DashboardSqlPreview
from apps.datasource.crud.permission import (
    PROJECT_ROLE_EDITOR,
    get_accessible_datasource_ids,
    get_column_permission_fields,
    get_row_permission_filters,
    get_user_scoped_table_ids,
    get_user_permission_rules,
    has_datasource_access,
    has_datasource_role,
    is_normal_user,
)
from apps.datasource.models.datasource import CoreDatasource
from apps.datasource.models.datasource import CoreTable, CoreField
from apps.db.db import exec_sql, get_sqlglot_dialect
from apps.system.models.user import UserModel
from apps.system.crud.user import is_system_admin
from common.core.deps import SessionDep, CurrentUser
from common.utils.data_format import DataFormat
from common.utils.utils import SQLBotLogUtil
import uuid
import time

from common.utils.tree_utils import build_tree_generic


def _user_id(current_user: CurrentUser) -> str:
    return str(current_user.id)


def _can_edit_datasource_dashboard(session: SessionDep, current_user: CurrentUser, datasource_id: int | None) -> bool:
    if datasource_id is None:
        return is_system_admin(current_user)
    return has_datasource_role(session, current_user, datasource_id, PROJECT_ROLE_EDITOR)


def _can_create_datasource_dashboard(session: SessionDep, current_user: CurrentUser, datasource_id: int | None) -> bool:
    if datasource_id is None:
        return is_system_admin(current_user)
    return has_datasource_access(session, current_user, datasource_id)


def _can_edit_dashboard(session: SessionDep, current_user: CurrentUser, dashboard: CoreDashboard) -> bool:
    return (
        is_system_admin(current_user)
        or str(dashboard.create_by) == _user_id(current_user)
        or _can_edit_datasource_dashboard(session, current_user, _effective_dashboard_datasource(dashboard))
    )


def _can_view_legacy_dashboard(current_user: CurrentUser, dashboard: CoreDashboard) -> bool:
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

    parent = _load_dashboard_or_404(session, parent_id)
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


def _failed_chart_result(message: str) -> dict[str, Any]:
    return {
        'status': 'failed',
        'data': [],
        'fields': [],
        'message': message,
    }


def _normalize_identifier(value: str | None) -> str:
    return str(value or "").strip('"`[]').lower()


def _parse_sql_statements(sql: str, ds_type: str | None) -> list[exp.Expression]:
    dialect = get_sqlglot_dialect(ds_type)
    statements = [stmt for stmt in sqlglot.parse(sql, dialect=dialect) if stmt is not None]
    if not statements:
        raise ValueError("SQL 解析失败，无法确认查询范围")
    return statements


def _extract_physical_tables(statements: list[exp.Expression]) -> set[str]:
    tables: set[str] = set()
    for stmt in statements:
        cte_names = {
            _normalize_identifier(cte.alias_or_name)
            for cte in stmt.find_all(exp.CTE)
            if cte.alias_or_name
        }
        for table in stmt.find_all(exp.Table):
            table_name = _normalize_identifier(table.name)
            if table_name and table_name not in cte_names:
                tables.add(table_name)
    return tables


def _build_dashboard_permission_scope(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
) -> dict[str, dict[str, Any]]:
    tables = session.query(CoreTable).filter(
        and_(CoreTable.ds_id == datasource.id, CoreTable.checked == True)
    ).all()
    table_ids = [table.id for table in tables]
    fields_by_table: dict[int, list[CoreField]] = {}
    if table_ids:
        fields = session.query(CoreField).filter(
            and_(CoreField.table_id.in_(table_ids), CoreField.checked == True)
        ).all()
        for field in fields:
            fields_by_table.setdefault(int(field.table_id), []).append(field)

    contain_rules = get_user_permission_rules(session, current_user, datasource.id) if is_normal_user(current_user) else []
    scoped_table_ids = get_user_scoped_table_ids(session, current_user, datasource.id, contain_rules)
    scope: dict[str, dict[str, Any]] = {}
    for table in tables:
        if scoped_table_ids is not None and int(table.id) not in scoped_table_ids:
            continue
        table_fields = fields_by_table.get(int(table.id), [])
        if is_normal_user(current_user):
            table_fields = get_column_permission_fields(
                session=session,
                current_user=current_user,
                table=table,
                fields=table_fields,
                contain_rules=contain_rules,
            )
        scope[_normalize_identifier(table.table_name)] = {
            "table": table,
            "fields": {_normalize_identifier(field.field_name) for field in table_fields},
        }
    return scope


def _selected_table_aliases(select_expr: exp.Select, cte_names: set[str] | None = None) -> dict[str, str]:
    aliases: dict[str, str] = {}
    cte_names = cte_names or set()
    sources = []
    from_expr = select_expr.args.get("from_")
    if from_expr and from_expr.this is not None:
        sources.append(from_expr.this)
    for join in select_expr.args.get("joins") or []:
        if join.this is not None:
            sources.append(join.this)

    for source in sources:
        if not isinstance(source, exp.Table):
            continue
        table_name = _normalize_identifier(source.name)
        if not table_name or table_name in cte_names:
            continue
        aliases[_normalize_identifier(source.alias_or_name or source.name)] = table_name
        aliases[table_name] = table_name
    return aliases


def _column_can_resolve(
        column_name: str,
        column_table: str,
        selected_aliases: dict[str, str],
        permission_scope: dict[str, dict[str, Any]],
) -> bool:
    normalized_column = _normalize_identifier(column_name)
    normalized_table = _normalize_identifier(column_table)
    if not normalized_column:
        return True

    if normalized_table:
        physical_table = selected_aliases.get(normalized_table)
        if physical_table is None:
            return True
        allowed_fields = permission_scope.get(physical_table, {}).get("fields", set())
        return normalized_column in allowed_fields

    selected_tables = set(selected_aliases.values())
    if not selected_tables:
        return True
    candidate_tables = [
        table_name
        for table_name in selected_tables
        if normalized_column in permission_scope.get(table_name, {}).get("fields", set())
    ]
    return len(candidate_tables) == 1


def _star_uses_table_scope(star: exp.Star, selected_aliases: dict[str, str]) -> set[str]:
    parent = star.parent
    if isinstance(parent, exp.Column) and parent.table:
        physical_table = selected_aliases.get(_normalize_identifier(parent.table))
        return {physical_table} if physical_table else set()
    return set(selected_aliases.values())


def _validate_sql_columns(
        statements: list[exp.Expression],
        permission_scope: dict[str, dict[str, Any]],
        current_user: CurrentUser,
) -> None:
    if not is_normal_user(current_user):
        return

    denied_columns: set[str] = set()
    star_tables: set[str] = set()
    for statement in statements:
        cte_names = {
            _normalize_identifier(cte.alias_or_name)
            for cte in statement.find_all(exp.CTE)
            if cte.alias_or_name
        }
        for select_expr in statement.find_all(exp.Select):
            selected_aliases = _selected_table_aliases(select_expr, cte_names)
            for star in select_expr.find_all(exp.Star):
                if isinstance(star.parent, exp.Count):
                    continue
                if isinstance(star.parent, exp.Column) and isinstance(star.parent.parent, exp.Count):
                    continue
                star_tables.update(_star_uses_table_scope(star, selected_aliases))

            for column in select_expr.find_all(exp.Column):
                if isinstance(column.this, exp.Star):
                    continue
                if not _column_can_resolve(column.name, column.table, selected_aliases, permission_scope):
                    denied_columns.add(column.sql())

    if star_tables:
        raise ValueError(
            "SQL 使用了 SELECT *，无法安全应用字段权限；请显式选择授权字段"
        )
    if denied_columns:
        raise ValueError(f"SQL 包含无权限字段：{', '.join(sorted(denied_columns))}")


def _parse_condition_expression(filter_sql: str, ds_type: str | None) -> exp.Expression:
    dialect = get_sqlglot_dialect(ds_type)
    wrapped_sql = f"select 1 where {filter_sql}"
    statement = sqlglot.parse_one(wrapped_sql, dialect=dialect)
    where_expr = statement.args.get("where")
    if where_expr is None or where_expr.this is None:
        raise ValueError("行权限过滤条件解析失败")
    return where_expr.this


def _apply_row_permission_filters(
        sql: str,
        datasource: CoreDatasource,
        filters: list[dict[str, Any]],
) -> str:
    filter_by_table = {
        _normalize_identifier(item.get("table")): str(item.get("filter") or "").strip()
        for item in filters
        if item.get("table") and str(item.get("filter") or "").strip()
    }
    if not filter_by_table:
        return sql

    statements = _parse_sql_statements(sql, datasource.type)

    for table_name, filter_sql in filter_by_table.items():
        try:
            _parse_condition_expression(filter_sql, datasource.type)
        except Exception as exc:
            raise ValueError(f"行权限过滤条件无法安全解析：{table_name}") from exc

    def _rewrite_table(node: exp.Expression):
        if not isinstance(node, exp.Table):
            return node
        table_name = _normalize_identifier(node.name)
        filter_sql = filter_by_table.get(table_name)
        if not filter_sql:
            return node

        alias_name = node.alias_or_name or node.name
        table_without_alias = node.copy()
        table_without_alias.set("alias", None)
        condition = _parse_condition_expression(filter_sql, datasource.type)
        filtered_select = exp.select("*").from_(table_without_alias).where(condition)
        return exp.Subquery(
            this=filtered_select,
            alias=exp.TableAlias(this=exp.to_identifier(alias_name)),
        )

    rewritten = [statement.transform(_rewrite_table) for statement in statements]
    return "; ".join(statement.sql(dialect=get_sqlglot_dialect(datasource.type)) for statement in rewritten)


def _execute_dashboard_chart_sql(
        session: SessionDep,
        current_user: CurrentUser,
        datasource_id: int,
        sql: str,
) -> dict[str, Any]:
    json_result: dict[str, Any] = {'status': 'success', 'fields': [], 'data': [], 'message': ''}
    try:
        datasource = session.get(CoreDatasource, datasource_id)
        if datasource is None:
            return _failed_chart_result("项目不存在")
        if not has_datasource_access(session, current_user, datasource_id):
            return _failed_chart_result("You do not have permission to access this datasource")

        statements = _parse_sql_statements(sql, datasource.type)
        actual_tables = _extract_physical_tables(statements)
        if not actual_tables:
            return _failed_chart_result("SQL 解析失败，无法确认查询表范围")

        permission_scope = _build_dashboard_permission_scope(session, current_user, datasource)
        unauthorized_tables = actual_tables - set(permission_scope.keys())
        if unauthorized_tables:
            return _failed_chart_result(f"SQL 包含无权限表：{', '.join(sorted(unauthorized_tables))}")
        _validate_sql_columns(statements, permission_scope, current_user)

        execute_sql_text = sql
        if is_normal_user(current_user):
            row_filters = get_row_permission_filters(
                session=session,
                current_user=current_user,
                ds=datasource,
                tables=sorted(actual_tables),
            )
            if row_filters:
                execute_sql_text = _apply_row_permission_filters(sql, datasource, row_filters)
                rewritten_statements = _parse_sql_statements(execute_sql_text, datasource.type)
                rewritten_tables = _extract_physical_tables(rewritten_statements)
                if not rewritten_tables or not rewritten_tables.issubset(set(permission_scope.keys())):
                    return _failed_chart_result("行权限 SQL 重写后表范围校验失败")

        result = exec_sql(ds=datasource, sql=execute_sql_text, origin_column=False)
        data = DataFormat.convert_large_numbers_in_object_array(result.get('data'))
        data = DataFormat.normalize_qualified_sql_column_keys_in_object_array(data)
        json_result['fields'] = list(data[0].keys()) if data else result.get('fields', [])
        json_result['data'] = data
        return json_result
    except Exception as e:
        SQLBotLogUtil.error(f"Dashboard chart SQL permission check failed: {e}")
        json_result['status'] = 'failed'
        json_result['message'] = f"{e}"
        return json_result


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


def _dashboard_base_response(session: SessionDep, current_user: CurrentUser, record: CoreDashboard,
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
        can_edit=_can_edit_dashboard(session, current_user, record),
    )


def list_resource(session: SessionDep, dashboard: QueryDashboard, current_user: CurrentUser):
    active_filter = or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None))
    filters = [active_filter]
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
    nodes = [_dashboard_base_response(session, current_user, record, datasource_id) for record in result]
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
    record = _load_dashboard_or_404(session, dashboard.id)
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
    record = _load_dashboard_or_404(session, dashboard.id)
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
                CoreDashboard.datasource == datasource_id,
                or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None)),
                CoreDashboard.name == dashboard.name
            )
        )
    elif dashboard.opt in ('updateLeaf', 'updateFolder', 'rename'):
        if not dashboard.id:
            raise ValueError("id is required for update operation")
        record = _load_dashboard_or_404(session, dashboard.id)
        _require_edit_permission(session, user, record)
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
    _require_edit_permission(session, current_user, coreDashboard)
    if coreDashboard.datasource:
        _ensure_datasource_access(session, current_user, coreDashboard.datasource)
    sql = text("DELETE FROM core_dashboard WHERE id = :resource_id")
    result = session.execute(sql, {"resource_id": resource_id})
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
