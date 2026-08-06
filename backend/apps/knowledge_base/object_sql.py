"""SQL AST object extraction used by knowledge reference projection."""

from __future__ import annotations

from collections.abc import Iterable

import sqlglot
from sqlglot import exp

from apps.datasource.crud.semantic_object_key import DeclaredObjectPath
from common.sql_json_paths import extract_json_accesses, normalize_json_path


class SqlObjectExtractionError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def extract_sql_object_paths(
    sql_values: Iterable[str],
    *,
    dialect: str,
) -> list[DeclaredObjectPath]:
    paths: list[DeclaredObjectPath] = []
    for sql in sql_values:
        try:
            statements = [item for item in sqlglot.parse(sql, read=dialect) if item is not None]
        except Exception as exc:
            raise SqlObjectExtractionError(
                "KNOWLEDGE_SQL_PARSE_FAILED",
                "SQL 示例无法按当前数据源方言解析。",
            ) from exc
        if len(statements) != 1:
            raise SqlObjectExtractionError(
                "KNOWLEDGE_SQL_PARSE_FAILED",
                "SQL 示例必须是一条查询语句。",
            )
        statement = statements[0]
        entries = table_entries(statement)
        paths.extend(path for path, _alias in entries)
        for column in statement.find_all(exp.Column):
            table = column_table(column, select_table_entries(nearest_select(column)))
            if table is None or not column.name or column.name == "*":
                continue
            paths.append(
                DeclaredObjectPath(
                    object_type="FIELD",
                    catalog=table.catalog,
                    schema=table.schema,
                    table=table.table,
                    field=str(column.name),
                )
            )
        for select in statement.find_all(exp.Select):
            extraction = extract_json_accesses(select, dialect=dialect, current_select_only=True)
            if extraction.issues:
                raise SqlObjectExtractionError(
                    "KNOWLEDGE_JSON_PATH_DYNAMIC",
                    "SQL 中的 JSON Path 必须是静态可解析路径。",
                )
            for access in extraction.accesses:
                table = column_table(access, select_table_entries(select), qualifier=access.table_alias)
                if table is None:
                    continue
                paths.append(
                    DeclaredObjectPath(
                        object_type="JSON_PATH",
                        catalog=table.catalog,
                        schema=table.schema,
                        table=table.table,
                        field=access.source_field,
                        json_path=normalize_json_path(access.json_path),
                    )
                )
    return paths


def table_entries(statement: exp.Expression) -> list[tuple[DeclaredObjectPath, str]]:
    ctes = {str(item.alias_or_name).casefold() for item in statement.find_all(exp.CTE)}
    result: list[tuple[DeclaredObjectPath, str]] = []
    for table in statement.find_all(exp.Table):
        name = str(table.name or "").strip()
        if not name or (not table.db and not table.catalog and name.casefold() in ctes):
            continue
        path = DeclaredObjectPath(
            object_type="TABLE",
            catalog=str(table.catalog or "").strip() or None,
            schema=str(table.db or "").strip() or None,
            table=name,
        )
        result.append((path, str(table.alias_or_name or name).strip().casefold()))
    return result


def select_table_entries(select: exp.Select | None) -> list[tuple[DeclaredObjectPath, str]]:
    if select is None:
        return []
    entries: list[tuple[DeclaredObjectPath, str]] = []
    sources: list[exp.Expression] = []
    from_clause = select.args.get("from_")
    if isinstance(from_clause, exp.From) and from_clause.this is not None:
        sources.append(from_clause.this)
    sources.extend(
        join.this
        for join in select.args.get("joins") or []
        if isinstance(join, exp.Join) and join.this is not None
    )
    for source in sources:
        if isinstance(source, exp.Table):
            entries.extend(table_entries(source))
    return entries


def nearest_select(node: exp.Expression) -> exp.Select | None:
    current = node.parent
    while current is not None:
        if isinstance(current, exp.Select):
            return current
        current = current.parent
    return None


def column_table(
    column: exp.Column | object,
    entries: list[tuple[DeclaredObjectPath, str]],
    *,
    qualifier: str | None = None,
) -> DeclaredObjectPath | None:
    name = str(qualifier if qualifier is not None else getattr(column, "table", "") or "").strip().casefold()
    if not name and len(entries) == 1:
        return entries[0][0]
    for path, alias in entries:
        if name in {alias, str(path.table or "").casefold()}:
            return path
    return None
