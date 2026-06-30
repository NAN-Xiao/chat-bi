"""
脚本说明：这个脚本封装数据源的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
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
    """
    是什么：normalize_identifier 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    return str(value or "").strip('"`[]').lower()


def parse_sql_statements(sql: str, ds_type: str | None) -> list[exp.Expression]:
    """
    是什么：parse_sql_statements 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    dialect = get_sqlglot_dialect(ds_type)
    statements = [stmt for stmt in sqlglot.parse(sql, dialect=dialect) if stmt is not None]
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
            if table_name and table_name not in cte_names:
                tables.add(table_name)
    return tables


def build_permission_scope(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
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
        all_field_names = {normalize_identifier(field.field_name) for field in table_fields}
        if is_normal_user(current_user):
            table_fields = get_column_permission_fields(
                session=session,
                current_user=current_user,
                table=table,
                fields=table_fields,
                contain_rules=contain_rules,
            )
        allowed_field_names = {normalize_identifier(field.field_name) for field in table_fields}
        scope[normalize_identifier(table.table_name)] = {
            "table": table,
            "fields": allowed_field_names,
            "denied_fields": all_field_names - allowed_field_names,
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


def _column_can_resolve(
        column_name: str,
        column_table: str,
        selected_aliases: dict[str, str],
        permission_scope: dict[str, dict[str, Any]],
        output_aliases: set[str] | None = None,
        cte_aliases: dict[str, set[str]] | None = None,
) -> bool:
    """
    是什么：_column_can_resolve 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    normalized_column = normalize_identifier(column_name)
    normalized_table = normalize_identifier(column_table)
    cte_aliases = cte_aliases or {}
    if not normalized_column:
        return True
    if normalized_column in (output_aliases or set()):
        return True

    if normalized_table:
        cte_fields = cte_aliases.get(normalized_table)
        if cte_fields is not None:
            return not cte_fields or normalized_column in cte_fields
        physical_table = selected_aliases.get(normalized_table)
        if physical_table is None:
            return True
        allowed_fields = permission_scope.get(physical_table, {}).get("fields", set())
        return normalized_column in allowed_fields

    selected_tables = set(selected_aliases.values())
    if not selected_tables:
        return True
    if any(
            normalized_column in permission_scope.get(table_name, {}).get("denied_fields", set())
            for table_name in selected_tables
    ):
        return False
    candidate_tables = [
        table_name
        for table_name in selected_tables
        if normalized_column in permission_scope.get(table_name, {}).get("fields", set())
    ]
    if len(candidate_tables) == 1:
        return True
    if any(not fields or normalized_column in fields for fields in cte_aliases.values()):
        return True
    return False


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
) -> None:
    """
    是什么：validate_sql_columns 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
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
        cte_columns = cte_output_columns(statement)
        for select_expr in statement.find_all(exp.Select):
            selected_aliases = selected_table_aliases(select_expr, cte_names)
            output_aliases = _select_output_aliases(select_expr)
            cte_aliases = selected_cte_aliases(select_expr, cte_columns)
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
                if not _column_can_resolve(
                        column.name,
                        column.table,
                        selected_aliases,
                        permission_scope,
                        output_aliases,
                        cte_aliases,
                ):
                    denied_columns.add(column.sql())

    restricted_star_tables = {
        table_name
        for table_name in star_tables
        if permission_scope.get(table_name, {}).get("denied_fields")
    }
    if restricted_star_tables:
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
    """
    是什么：validate_sql_scope 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
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
    """
    是什么：validate_sql_table_scope 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
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
