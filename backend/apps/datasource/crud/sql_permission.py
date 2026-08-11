"""
脚本说明：这个脚本封装数据源的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
import re
from enum import Enum
from typing import Any

import sqlglot
from sqlglot import exp
from sqlalchemy import and_

from apps.datasource.crud.permission import (
    get_column_permission_scope,
    get_user_permission_rules,
    get_user_scoped_table_ids,
    is_normal_user,
)
from apps.datasource.crud.permission_errors import SqlPermissionScopeError, SqlSchemaScopeError
from apps.datasource.models.datasource import CoreDatasource, CoreField, CoreTable
from apps.db.db import get_sqlglot_dialect
from common.core.deps import CurrentUser, SessionDep
from common.sql_json_paths import extract_json_accesses, json_paths_intersect


def normalize_identifier(value: str | None) -> str:
    """
    是什么：normalize_identifier 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    return str(value or "").strip('"`[]').lower()


def parse_sql_statements(
        sql: str,
        ds_type: str | None,
        *,
        fallback_to_generic: bool = False,
) -> list[exp.Expression]:
    """
    是什么：parse_sql_statements 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    dialect = get_sqlglot_dialect(ds_type)
    try:
        statements = [stmt for stmt in sqlglot.parse(sql, dialect=dialect) if stmt is not None]
    except sqlglot.errors.ParseError:
        if not fallback_to_generic or not dialect:
            raise
        statements = [stmt for stmt in sqlglot.parse(sql) if stmt is not None]
    if not statements:
        raise ValueError("SQL 解析失败，无法确认查询范围")
    return statements


def extract_physical_tables(statements: list[exp.Expression]) -> set[str]:
    """
    是什么：extract_physical_tables 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    tables: set[str] = set()
    for stmt in statements:
        cte_names = {
            normalize_identifier(cte.alias_or_name)
            for cte in stmt.find_all(exp.CTE)
            if cte.alias_or_name
        }
        for table in stmt.find_all(exp.Table):
            table_name = normalize_identifier(table.name)
            is_unqualified_cte_reference = (
                table_name in cte_names
                and not normalize_identifier(table.db)
                and not normalize_identifier(table.catalog)
            )
            if table_name and not is_unqualified_cte_reference:
                tables.add(table_name)
    return tables


def build_permission_scope(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
        *,
        apply_user_permission_scope: bool = True,
        enforce_for_scope_admin: bool = False,
) -> dict[str, dict[str, Any]]:
    """
    是什么：build_permission_scope 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存数据源需要的东西，让后续流程能继续往下走。
    """
    tables = session.query(CoreTable).filter(
        and_(CoreTable.ds_id == datasource.id, CoreTable.checked == True)
    ).all()
    table_ids = [table.id for table in tables]
    fields_by_table: dict[int, list[CoreField]] = {}
    if table_ids:
        fields = session.query(CoreField).filter(
            CoreField.table_id.in_(table_ids)
        ).all()
        for field in fields:
            fields_by_table.setdefault(int(field.table_id), []).append(field)

    user_permissions_apply = apply_user_permission_scope and (
        enforce_for_scope_admin or is_normal_user(current_user)
    )
    contain_rules = (
        get_user_permission_rules(
            session,
            current_user,
            datasource.id,
            enforce_for_scope_admin=enforce_for_scope_admin,
        )
        if user_permissions_apply
        else []
    )
    scoped_table_ids = (
        get_user_scoped_table_ids(
            session,
            current_user,
            datasource.id,
            contain_rules,
            enforce_for_scope_admin=enforce_for_scope_admin,
        )
        if user_permissions_apply
        else None
    )
    scope: dict[str, dict[str, Any]] = {}
    for table in tables:
        if scoped_table_ids is not None and int(table.id) not in scoped_table_ids:
            continue
        all_table_fields = fields_by_table.get(int(table.id), [])
        table_fields = [field for field in all_table_fields if field.checked]
        all_field_names = {normalize_identifier(field.field_name) for field in all_table_fields}
        if user_permissions_apply:
            column_scope = get_column_permission_scope(
                session=session,
                current_user=current_user,
                table=table,
                fields=table_fields,
                contain_rules=contain_rules,
            )
            table_fields = column_scope.fields
        else:
            column_scope = None
        allowed_field_names = {normalize_identifier(field.field_name) for field in table_fields}
        scope[normalize_identifier(table.table_name)] = {
            "table": table,
            "fields": allowed_field_names,
            "known_fields": all_field_names,
            "denied_fields": all_field_names - allowed_field_names,
            "denied_json_paths": column_scope.denied_json_paths if column_scope else {},
        }
    return scope


def selected_table_aliases(select_expr: exp.Select, cte_names: set[str] | None = None) -> dict[str, str]:
    """
    是什么：selected_table_aliases 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
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
        table_name = normalize_identifier(source.name)
        if not table_name or table_name in cte_names:
            continue
        aliases[normalize_identifier(source.alias_or_name or source.name)] = table_name
        aliases[table_name] = table_name
    return aliases


def cte_output_columns(statement: exp.Expression) -> dict[str, set[str]]:
    """
    是什么：cte_output_columns 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    cte_columns: dict[str, set[str]] = {}
    for cte in statement.find_all(exp.CTE):
        cte_name = normalize_identifier(cte.alias_or_name)
        if not cte_name:
            continue
        columns: set[str] = set()
        cte_selects = list(cte.this.find_all(exp.Select))
        cte_selects.sort(key=lambda item: 0 if any(expr.alias for expr in item.expressions) else 1)
        for cte_select in cte_selects:
            for item in cte_select.expressions:
                column_name = normalize_identifier(item.alias_or_name)
                if column_name and column_name != "*":
                    columns.add(column_name)
            if not columns:
                columns.update(_values_source_columns(cte_select))
            if columns:
                break
        cte_columns[cte_name] = columns
    return cte_columns


def _values_source_columns(select_expr: exp.Select) -> set[str]:
    """
    是什么：_values_source_columns 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    from_expr = select_expr.args.get("from_")
    source = from_expr.this if from_expr is not None else None
    if not isinstance(source, exp.Values):
        return set()
    alias = source.args.get("alias")
    if not isinstance(alias, exp.TableAlias):
        return set()
    return {
        normalize_identifier(column.name)
        for column in alias.args.get("columns") or []
        if normalize_identifier(column.name)
    }


def selected_cte_aliases(
        select_expr: exp.Select,
        cte_columns: dict[str, set[str]] | None = None,
) -> dict[str, set[str]]:
    """
    是什么：selected_cte_aliases 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    cte_columns = cte_columns or {}
    aliases: dict[str, set[str]] = {}
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
        table_name = normalize_identifier(source.name)
        if table_name not in cte_columns:
            continue
        source_alias = normalize_identifier(source.alias_or_name or source.name)
        aliases[source_alias] = cte_columns[table_name]
        aliases[table_name] = cte_columns[table_name]
    return aliases


class _ColumnResolution(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    UNKNOWN = "unknown"


def _column_resolution(
        column_name: str,
        column_table: str,
        selected_aliases: dict[str, str],
        permission_scope: dict[str, dict[str, Any]],
        output_aliases: set[str] | None = None,
        cte_aliases: dict[str, set[str]] | None = None,
) -> _ColumnResolution:
    """
    是什么：判断字段是已授权、受限，还是当前 Schema 中不存在。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：保留权限拒绝与 Schema 修复之间的明确边界。
    """
    normalized_column = normalize_identifier(column_name)
    normalized_table = normalize_identifier(column_table)
    cte_aliases = cte_aliases or {}
    if not normalized_column:
        return _ColumnResolution.ALLOWED
    if normalized_column in (output_aliases or set()):
        return _ColumnResolution.ALLOWED

    if normalized_table:
        cte_fields = cte_aliases.get(normalized_table)
        if cte_fields is not None:
            return (
                _ColumnResolution.ALLOWED
                if not cte_fields or normalized_column in cte_fields
                else _ColumnResolution.UNKNOWN
            )
        physical_table = selected_aliases.get(normalized_table)
        if physical_table is None:
            return _ColumnResolution.UNKNOWN
        table_scope = permission_scope.get(physical_table, {})
        if normalized_column in table_scope.get("fields", set()):
            return _ColumnResolution.ALLOWED
        if normalized_column in table_scope.get("denied_fields", set()):
            return _ColumnResolution.DENIED
        if table_scope.get("unknown_fields_are_denied"):
            return _ColumnResolution.DENIED
        return _ColumnResolution.UNKNOWN

    selected_tables = set(selected_aliases.values())
    if not selected_tables:
        return _ColumnResolution.ALLOWED
    if any(
            normalized_column in permission_scope.get(table_name, {}).get("denied_fields", set())
            for table_name in selected_tables
    ):
        return _ColumnResolution.DENIED
    if any(
            permission_scope.get(table_name, {}).get("unknown_fields_are_denied")
            for table_name in selected_tables
    ):
        known_in_selected_scope = any(
            normalized_column in permission_scope.get(table_name, {}).get("fields", set())
            for table_name in selected_tables
        )
        if not known_in_selected_scope:
            return _ColumnResolution.DENIED
    candidate_tables = [
        table_name
        for table_name in selected_tables
        if normalized_column in permission_scope.get(table_name, {}).get("fields", set())
    ]
    if len(candidate_tables) == 1:
        return _ColumnResolution.ALLOWED
    if any(not fields or normalized_column in fields for fields in cte_aliases.values()):
        return _ColumnResolution.ALLOWED
    return _ColumnResolution.UNKNOWN


def _star_uses_table_scope(star: exp.Star, selected_aliases: dict[str, str]) -> set[str]:
    """
    是什么：_star_uses_table_scope 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    parent = star.parent
    if isinstance(parent, exp.Column) and parent.table:
        physical_table = selected_aliases.get(normalize_identifier(parent.table))
        return {physical_table} if physical_table else set()
    return set(selected_aliases.values())


def _nearest_select(node: exp.Expression) -> exp.Select | None:
    """
    是什么：_nearest_select 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    parent = node.parent
    while parent is not None:
        if isinstance(parent, exp.Select):
            return parent
        parent = parent.parent
    return None


def _is_in_current_select_scope(node: exp.Expression, select_expr: exp.Select) -> bool:
    """
    是什么：_is_in_current_select_scope 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return _nearest_select(node) is select_expr


def _select_output_aliases(select_expr: exp.Select) -> set[str]:
    """
    是什么：_select_output_aliases 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    aliases: set[str] = set()
    for item in select_expr.expressions:
        alias = normalize_identifier(item.alias)
        if alias:
            aliases.add(alias)
    return aliases


def validate_sql_columns(
        statements: list[exp.Expression],
        permission_scope: dict[str, dict[str, Any]],
        current_user: CurrentUser,
        *,
        enforce: bool = False,
        dialect: str | None = None,
) -> None:
    """
    是什么：validate_sql_columns 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if not enforce and not is_normal_user(current_user):
        return

    denied_columns: set[str] = set()
    unknown_columns: set[str] = set()
    denied_json_paths: set[str] = set()
    star_tables: set[str] = set()
    for statement in statements:
        cte_names = {
            normalize_identifier(cte.alias_or_name)
            for cte in statement.find_all(exp.CTE)
            if cte.alias_or_name
        }
        cte_columns = cte_output_columns(statement)
        for select_expr in statement.find_all(exp.Select):
            selected_aliases = selected_table_aliases(select_expr, cte_names)
            output_aliases = _select_output_aliases(select_expr)
            cte_aliases = selected_cte_aliases(select_expr, cte_columns)
            json_extraction = extract_json_accesses(
                select_expr,
                dialect=dialect or "mysql",
                current_select_only=True,
            )
            consumed_column_ids = set(json_extraction.consumed_column_ids)
            for access in json_extraction.accesses:
                normalized_source = normalize_identifier(access.source_field)
                normalized_alias = normalize_identifier(access.table_alias)
                physical_table = selected_aliases.get(normalized_alias) if normalized_alias else None
                if physical_table is None:
                    candidates = {
                        table_name
                        for table_name in set(selected_aliases.values())
                        if normalized_source in permission_scope.get(table_name, {}).get("denied_json_paths", {})
                    }
                    physical_table = next(iter(candidates)) if len(candidates) == 1 else None
                restrictions = permission_scope.get(physical_table or "", {}).get("denied_json_paths", {})
                for denied_path in restrictions.get(normalized_source, set()):
                    if json_paths_intersect(access.json_path, denied_path):
                        denied_columns.add(access.source_field)
                        denied_json_paths.add(access.json_path)

            for issue in json_extraction.issues:
                normalized_source = normalize_identifier(issue.source_field)
                normalized_alias = normalize_identifier(issue.table_alias)
                physical_table = selected_aliases.get(normalized_alias) if normalized_alias else None
                candidate_tables = {physical_table} if physical_table else set(selected_aliases.values())
                if any(
                        normalized_source in permission_scope.get(table_name, {}).get("denied_json_paths", {})
                        for table_name in candidate_tables
                ):
                    denied_columns.add(issue.source_field or "JSON")
                    denied_json_paths.add("<dynamic>")
            for star in select_expr.find_all(exp.Star):
                if not _is_in_current_select_scope(star, select_expr):
                    continue
                if isinstance(star.parent, exp.Count):
                    continue
                if isinstance(star.parent, exp.Column) and isinstance(star.parent.parent, exp.Count):
                    continue
                star_tables.update(_star_uses_table_scope(star, selected_aliases))

            for column in select_expr.find_all(exp.Column):
                if not _is_in_current_select_scope(column, select_expr):
                    continue
                if isinstance(column.this, exp.Star):
                    continue
                if id(column) in consumed_column_ids:
                    resolution = _column_resolution(
                            column.name,
                            column.table,
                            selected_aliases,
                            permission_scope,
                            output_aliases,
                            cte_aliases,
                    )
                    if resolution is _ColumnResolution.DENIED:
                        denied_columns.add(column.sql())
                    elif resolution is _ColumnResolution.UNKNOWN:
                        unknown_columns.add(column.sql())
                    continue
                normalized_column = normalize_identifier(column.name)
                normalized_table = normalize_identifier(column.table)
                physical_table = selected_aliases.get(normalized_table) if normalized_table else None
                candidate_tables = {physical_table} if physical_table else set(selected_aliases.values())
                if any(
                        normalized_column in permission_scope.get(table_name, {}).get("denied_json_paths", {})
                        for table_name in candidate_tables
                ):
                    denied_columns.add(column.sql())
                    denied_json_paths.add("$")
                    continue
                resolution = _column_resolution(
                        column.name,
                        column.table,
                        selected_aliases,
                        permission_scope,
                        output_aliases,
                        cte_aliases,
                )
                if resolution is _ColumnResolution.DENIED:
                    denied_columns.add(column.sql())
                elif resolution is _ColumnResolution.UNKNOWN:
                    unknown_columns.add(column.sql())

    restricted_star_tables = {
        table_name
        for table_name in star_tables
        if permission_scope.get(table_name, {}).get("denied_fields")
        or permission_scope.get(table_name, {}).get("denied_json_paths")
    }
    if restricted_star_tables:
        raise SqlPermissionScopeError(
            "SQL 使用了 SELECT *，无法安全应用字段权限；请显式选择授权字段"
            , rule_type="json_path" if any(
                permission_scope.get(table_name, {}).get("denied_json_paths")
                for table_name in restricted_star_tables
            ) else "column"
        )
    if denied_columns:
        raise SqlPermissionScopeError(
            f"SQL 包含无权限字段：{', '.join(sorted(denied_columns))}",
            fields=denied_columns,
            json_paths=denied_json_paths,
            rule_type="json_path" if denied_json_paths else "column",
        )
    if unknown_columns:
        raise SqlSchemaScopeError(
            f"SQL 引用了当前 Schema 中不存在或无法解析的字段：{', '.join(sorted(unknown_columns))}",
            fields=unknown_columns,
        )


def _raise_for_unavailable_tables(
        session: SessionDep,
        datasource: CoreDatasource,
        unavailable_tables: set[str],
        *,
        unknown_tables_are_denied: bool = False,
) -> None:
    if not unavailable_tables:
        return
    known_tables = {
        normalize_identifier(table_name)
        for (table_name,) in session.query(CoreTable.table_name).filter(
            CoreTable.ds_id == datasource.id
        ).all()
    }
    denied_tables = unavailable_tables & known_tables
    if denied_tables or unknown_tables_are_denied:
        denied_tables = unavailable_tables if unknown_tables_are_denied else denied_tables
        raise SqlPermissionScopeError(
            f"SQL 包含无权限表：{', '.join(sorted(denied_tables))}",
            tables=denied_tables,
            rule_type="table",
        )
    raise SqlSchemaScopeError(
        f"SQL 引用了当前 Schema 中不存在的表：{', '.join(sorted(unavailable_tables))}",
        tables=unavailable_tables,
    )


def validate_sql_scope(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
        sql: str,
        *,
        apply_user_permission_scope: bool = True,
        enforce_for_scope_admin: bool = False,
) -> tuple[list[exp.Expression], set[str], dict[str, dict[str, Any]]]:
    """
    是什么：validate_sql_scope 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
    statements = parse_sql_statements(sql, datasource.type)
    actual_tables = extract_physical_tables(statements)
    if not actual_tables:
        raise ValueError("SQL 解析失败，无法确认查询表范围")

    permission_scope = build_permission_scope(
        session,
        current_user,
        datasource,
        apply_user_permission_scope=apply_user_permission_scope,
        enforce_for_scope_admin=enforce_for_scope_admin,
    )
    unauthorized_tables = actual_tables - set(permission_scope.keys())
    _raise_for_unavailable_tables(session, datasource, unauthorized_tables)

    validate_sql_columns(
        statements,
        permission_scope,
        current_user,
        dialect=get_sqlglot_dialect(datasource.type),
    )
    return statements, actual_tables, permission_scope


def validate_sql_table_scope(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
        sql: str,
        *,
        apply_user_permission_scope: bool = True,
        enforce_for_scope_admin: bool = False,
        allow_empty_tables: bool = False,
) -> set[str]:
    """
    是什么：validate_sql_table_scope 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
    statements = parse_sql_statements(sql, datasource.type, fallback_to_generic=True)
    actual_tables = extract_physical_tables(statements)
    if not actual_tables:
        if allow_empty_tables:
            return set()
        raise ValueError("SQL 解析失败，无法确认查询表范围")

    permission_scope = build_permission_scope(
        session,
        current_user,
        datasource,
        apply_user_permission_scope=apply_user_permission_scope,
        enforce_for_scope_admin=enforce_for_scope_admin,
    )
    unauthorized_tables = actual_tables - set(permission_scope.keys())
    _raise_for_unavailable_tables(
        session,
        datasource,
        unauthorized_tables,
        unknown_tables_are_denied=True,
    )
    return actual_tables


def parse_condition_expression(filter_sql: str, ds_type: str | None) -> exp.Expression:
    """
    是什么：parse_condition_expression 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    dialect = get_sqlglot_dialect(ds_type)
    wrapped_sql = f"select 1 where {filter_sql}"
    statement = sqlglot.parse_one(wrapped_sql, dialect=dialect)
    where_expr = statement.args.get("where")
    if where_expr is None or where_expr.this is None:
        raise ValueError("行权限过滤条件解析失败")
    return where_expr.this


class RowPermissionRelation(str, Enum):
    DISJOINT = "disjoint"
    OVERLAP = "overlap"
    UNKNOWN = "unknown"


class _TruthValue(str, Enum):
    FALSE = "false"
    TRUE = "true"
    UNKNOWN = "unknown"


def _literal_value(node: exp.Expression) -> Any:
    if isinstance(node, exp.Literal):
        if node.is_string:
            return str(node.this)
        try:
            return int(node.this)
        except (TypeError, ValueError):
            try:
                return float(node.this)
            except (TypeError, ValueError):
                return str(node.this)
    if isinstance(node, exp.Null):
        return None
    return _MISSING


_MISSING = object()


def _normalized_scalar(value: Any) -> Any:
    return value.casefold() if isinstance(value, str) else value


def _merge_assignment(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any] | None:
    merged = dict(left)
    for field_name, value in right.items():
        if field_name in merged and _normalized_scalar(merged[field_name]) != _normalized_scalar(value):
            return None
        merged[field_name] = value
    return merged


def _finite_denied_assignments(node: exp.Expression) -> list[dict[str, Any]] | None:
    """把有限 EQ/IN 禁止条件展开为字段赋值；其他形态交给 fail-closed。"""
    if isinstance(node, exp.Paren):
        return _finite_denied_assignments(node.this)
    if isinstance(node, exp.EQ) and isinstance(node.this, exp.Column):
        value = _literal_value(node.expression)
        if value is _MISSING:
            return None
        return [{normalize_identifier(node.this.name): value}]
    if isinstance(node, exp.In) and isinstance(node.this, exp.Column) and not node.args.get("query"):
        values = [_literal_value(item) for item in node.expressions]
        if any(value is _MISSING for value in values):
            return None
        return [{normalize_identifier(node.this.name): value} for value in values]
    if isinstance(node, exp.And):
        left = _finite_denied_assignments(node.this)
        right = _finite_denied_assignments(node.expression)
        if left is None or right is None:
            return None
        merged: list[dict[str, Any]] = []
        for left_assignment in left:
            for right_assignment in right:
                assignment = _merge_assignment(left_assignment, right_assignment)
                if assignment is not None:
                    merged.append(assignment)
        return merged
    if isinstance(node, exp.Or):
        left = _finite_denied_assignments(node.this)
        right = _finite_denied_assignments(node.expression)
        if left is None or right is None:
            return None
        return [*left, *right]
    return None


def _sql_like_matches(value: Any, pattern: Any) -> bool | None:
    if not isinstance(value, str) or not isinstance(pattern, str):
        return None
    parts: list[str] = []
    escaped = False
    for char in pattern:
        if escaped:
            parts.append(re.escape(char))
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "%":
            parts.append(".*")
        elif char == "_":
            parts.append(".")
        else:
            parts.append(re.escape(char))
    if escaped:
        parts.append(re.escape("\\"))
    return re.fullmatch("".join(parts), value, flags=re.IGNORECASE | re.DOTALL) is not None


def _column_assignment_value(
        node: exp.Expression,
        assignment: dict[str, Any],
        aliases: set[str],
) -> Any:
    if not isinstance(node, exp.Column):
        return _MISSING
    qualifier = normalize_identifier(node.table)
    if qualifier and qualifier not in aliases:
        return _MISSING
    return assignment.get(normalize_identifier(node.name), _MISSING)


def _truth_not(value: _TruthValue) -> _TruthValue:
    if value == _TruthValue.TRUE:
        return _TruthValue.FALSE
    if value == _TruthValue.FALSE:
        return _TruthValue.TRUE
    return _TruthValue.UNKNOWN


def _evaluate_query_predicate(
        node: exp.Expression,
        assignment: dict[str, Any],
        aliases: set[str],
) -> _TruthValue:
    if isinstance(node, exp.Paren):
        return _evaluate_query_predicate(node.this, assignment, aliases)
    if isinstance(node, exp.And):
        left = _evaluate_query_predicate(node.this, assignment, aliases)
        right = _evaluate_query_predicate(node.expression, assignment, aliases)
        if _TruthValue.FALSE in {left, right}:
            return _TruthValue.FALSE
        if left == right == _TruthValue.TRUE:
            return _TruthValue.TRUE
        return _TruthValue.UNKNOWN
    if isinstance(node, exp.Or):
        left = _evaluate_query_predicate(node.this, assignment, aliases)
        right = _evaluate_query_predicate(node.expression, assignment, aliases)
        if _TruthValue.TRUE in {left, right}:
            return _TruthValue.TRUE
        if left == right == _TruthValue.FALSE:
            return _TruthValue.FALSE
        return _TruthValue.UNKNOWN
    if isinstance(node, exp.Not):
        return _truth_not(_evaluate_query_predicate(node.this, assignment, aliases))

    if isinstance(node, (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)):
        left = _column_assignment_value(node.this, assignment, aliases)
        right = _literal_value(node.expression)
        if left is _MISSING or right is _MISSING:
            return _TruthValue.UNKNOWN
        left_value = _normalized_scalar(left)
        right_value = _normalized_scalar(right)
        try:
            if isinstance(node, exp.EQ):
                result = left_value == right_value
            elif isinstance(node, exp.NEQ):
                result = left_value != right_value
            elif isinstance(node, exp.GT):
                result = left_value > right_value
            elif isinstance(node, exp.GTE):
                result = left_value >= right_value
            elif isinstance(node, exp.LT):
                result = left_value < right_value
            else:
                result = left_value <= right_value
        except TypeError:
            return _TruthValue.UNKNOWN
        return _TruthValue.TRUE if result else _TruthValue.FALSE

    if isinstance(node, exp.In) and not node.args.get("query"):
        value = _column_assignment_value(node.this, assignment, aliases)
        candidates = [_literal_value(item) for item in node.expressions]
        if value is _MISSING or any(item is _MISSING for item in candidates):
            return _TruthValue.UNKNOWN
        normalized = _normalized_scalar(value)
        result = normalized in {_normalized_scalar(item) for item in candidates}
        return _TruthValue.TRUE if result else _TruthValue.FALSE

    if isinstance(node, exp.Like):
        value = _column_assignment_value(node.this, assignment, aliases)
        pattern = _literal_value(node.expression)
        matched = _sql_like_matches(value, pattern)
        if matched is None:
            return _TruthValue.UNKNOWN
        if node.args.get("negate"):
            matched = not matched
        return _TruthValue.TRUE if matched else _TruthValue.FALSE

    return _TruthValue.UNKNOWN


def analyze_row_permission_relation(
        sql: str,
        datasource: CoreDatasource,
        constraints: list[dict[str, Any]],
) -> RowPermissionRelation:
    """判断原始查询是否可能读取任一正向禁止条件命中的行。"""
    if not constraints:
        return RowPermissionRelation.DISJOINT
    statements = parse_sql_statements(sql, datasource.type)
    table_nodes: dict[str, list[exp.Table]] = {}
    for statement in statements:
        cte_names = {
            normalize_identifier(cte.alias_or_name)
            for cte in statement.find_all(exp.CTE)
            if cte.alias_or_name
        }
        for table in statement.find_all(exp.Table):
            table_name = normalize_identifier(table.name)
            if (
                table_name in cte_names
                and not normalize_identifier(table.db)
                and not normalize_identifier(table.catalog)
            ):
                continue
            table_nodes.setdefault(table_name, []).append(table)

    saw_unknown = False
    for constraint in constraints:
        table_name = normalize_identifier(constraint.get("table"))
        nodes = table_nodes.get(table_name, [])
        if not nodes:
            continue
        try:
            denied_expression = parse_condition_expression(
                str(constraint.get("deny_sql") or ""),
                datasource.type,
            )
        except Exception:
            saw_unknown = True
            continue
        assignments = _finite_denied_assignments(denied_expression)
        if assignments is None or not assignments:
            saw_unknown = True
            continue
        for table in nodes:
            select_expr = _nearest_select(table)
            where_expr = select_expr.args.get("where") if select_expr is not None else None
            if where_expr is None or where_expr.this is None:
                return RowPermissionRelation.OVERLAP
            aliases = {
                normalize_identifier(table_name),
                normalize_identifier(table.alias_or_name),
            }
            for assignment in assignments:
                relation = _evaluate_query_predicate(where_expr.this, assignment, aliases)
                if relation != _TruthValue.FALSE:
                    return RowPermissionRelation.OVERLAP
    return RowPermissionRelation.UNKNOWN if saw_unknown else RowPermissionRelation.DISJOINT


def apply_row_permission_filters(
        sql: str,
        datasource: CoreDatasource,
        filters: list[dict[str, Any]],
) -> str:
    """
    是什么：apply_row_permission_filters 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    filter_by_table = {
        normalize_identifier(item.get("table")): str(item.get("filter") or "").strip()
        for item in filters
        if item.get("table") and str(item.get("filter") or "").strip()
    }
    if not filter_by_table:
        return sql

    statements = parse_sql_statements(sql, datasource.type)

    for table_name, filter_sql in filter_by_table.items():
        try:
            parse_condition_expression(filter_sql, datasource.type)
        except Exception as exc:
            raise ValueError(f"行权限过滤条件无法安全解析：{table_name}") from exc

    def _rewrite_table(node: exp.Expression):
        """
        是什么：_rewrite_table 是一个可以复用的小步骤，负责数据源相关的一件事。
        谁调用：外层函数 apply_row_permission_filters 跑到对应步骤时会调用它。
        做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        if isinstance(node, exp.Table):
            table_name = normalize_identifier(node.name)
            alias_name = node.alias_or_name or node.name
            filter_sql = filter_by_table.get(table_name) or filter_by_table.get(normalize_identifier(alias_name))
            if not filter_sql:
                return node

            source = node.copy()
            source.set("alias", None)
        elif isinstance(node, exp.Subquery):
            alias_name = node.alias_or_name
            filter_sql = filter_by_table.get(normalize_identifier(alias_name))
            if not alias_name or not filter_sql:
                return node
            source = node.copy()
        else:
            return node

        condition = parse_condition_expression(filter_sql, datasource.type)
        filtered_select = exp.select("*").from_(source).where(condition)
        return exp.Subquery(
            this=filtered_select,
            alias=exp.TableAlias(this=exp.to_identifier(alias_name)),
        )

    rewritten = [statement.transform(_rewrite_table) for statement in statements]
    return "; ".join(statement.sql(dialect=get_sqlglot_dialect(datasource.type)) for statement in rewritten)
