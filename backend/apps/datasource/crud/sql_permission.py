from typing import Any

import sqlglot
from sqlglot import exp
from sqlalchemy import and_

from apps.datasource.crud.permission import (
    get_column_permission_fields,
    get_user_permission_rules,
    get_user_scoped_table_ids,
    is_normal_user,
)
from apps.datasource.models.datasource import CoreDatasource, CoreField, CoreTable
from apps.db.db import get_sqlglot_dialect
from common.core.deps import CurrentUser, SessionDep


def normalize_identifier(value: str | None) -> str:
    return str(value or "").strip('"`[]').lower()


def parse_sql_statements(sql: str, ds_type: str | None) -> list[exp.Expression]:
    dialect = get_sqlglot_dialect(ds_type)
    statements = [stmt for stmt in sqlglot.parse(sql, dialect=dialect) if stmt is not None]
    if not statements:
        raise ValueError("SQL 解析失败，无法确认查询范围")
    return statements


def extract_physical_tables(statements: list[exp.Expression]) -> set[str]:
    tables: set[str] = set()
    for stmt in statements:
        cte_names = {
            normalize_identifier(cte.alias_or_name)
            for cte in stmt.find_all(exp.CTE)
            if cte.alias_or_name
        }
        for table in stmt.find_all(exp.Table):
            table_name = normalize_identifier(table.name)
            if table_name and table_name not in cte_names:
                tables.add(table_name)
    return tables


def build_permission_scope(
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
        scope[normalize_identifier(table.table_name)] = {
            "table": table,
            "fields": {normalize_identifier(field.field_name) for field in table_fields},
        }
    return scope


def selected_table_aliases(select_expr: exp.Select, cte_names: set[str] | None = None) -> dict[str, str]:
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


def _column_can_resolve(
        column_name: str,
        column_table: str,
        selected_aliases: dict[str, str],
        permission_scope: dict[str, dict[str, Any]],
) -> bool:
    normalized_column = normalize_identifier(column_name)
    normalized_table = normalize_identifier(column_table)
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
        physical_table = selected_aliases.get(normalize_identifier(parent.table))
        return {physical_table} if physical_table else set()
    return set(selected_aliases.values())


def validate_sql_columns(
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
            normalize_identifier(cte.alias_or_name)
            for cte in statement.find_all(exp.CTE)
            if cte.alias_or_name
        }
        for select_expr in statement.find_all(exp.Select):
            selected_aliases = selected_table_aliases(select_expr, cte_names)
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


def validate_sql_scope(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
        sql: str,
) -> tuple[list[exp.Expression], set[str], dict[str, dict[str, Any]]]:
    statements = parse_sql_statements(sql, datasource.type)
    actual_tables = extract_physical_tables(statements)
    if not actual_tables:
        raise ValueError("SQL 解析失败，无法确认查询表范围")

    permission_scope = build_permission_scope(session, current_user, datasource)
    unauthorized_tables = actual_tables - set(permission_scope.keys())
    if unauthorized_tables:
        raise ValueError(f"SQL 包含无权限表：{', '.join(sorted(unauthorized_tables))}")

    validate_sql_columns(statements, permission_scope, current_user)
    return statements, actual_tables, permission_scope


def validate_sql_table_scope(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
        sql: str,
) -> set[str]:
    statements = parse_sql_statements(sql, datasource.type)
    actual_tables = extract_physical_tables(statements)
    if not actual_tables:
        raise ValueError("SQL 解析失败，无法确认查询表范围")

    permission_scope = build_permission_scope(session, current_user, datasource)
    unauthorized_tables = actual_tables - set(permission_scope.keys())
    if unauthorized_tables:
        raise ValueError(f"SQL 包含无权限表：{', '.join(sorted(unauthorized_tables))}")
    return actual_tables


def parse_condition_expression(filter_sql: str, ds_type: str | None) -> exp.Expression:
    dialect = get_sqlglot_dialect(ds_type)
    wrapped_sql = f"select 1 where {filter_sql}"
    statement = sqlglot.parse_one(wrapped_sql, dialect=dialect)
    where_expr = statement.args.get("where")
    if where_expr is None or where_expr.this is None:
        raise ValueError("行权限过滤条件解析失败")
    return where_expr.this


def apply_row_permission_filters(
        sql: str,
        datasource: CoreDatasource,
        filters: list[dict[str, Any]],
) -> str:
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
        if not isinstance(node, exp.Table):
            return node
        table_name = normalize_identifier(node.name)
        filter_sql = filter_by_table.get(table_name)
        if not filter_sql:
            return node

        alias_name = node.alias_or_name or node.name
        table_without_alias = node.copy()
        table_without_alias.set("alias", None)
        condition = parse_condition_expression(filter_sql, datasource.type)
        filtered_select = exp.select("*").from_(table_without_alias).where(condition)
        return exp.Subquery(
            this=filtered_select,
            alias=exp.TableAlias(this=exp.to_identifier(alias_name)),
        )

    rewritten = [statement.transform(_rewrite_table) for statement in statements]
    return "; ".join(statement.sql(dialect=get_sqlglot_dialect(datasource.type)) for statement in rewritten)
