from typing import Any

import re

import sqlglot
from sqlglot import exp

from apps.datasource.crud.permission import get_row_permission_filters, is_normal_user
from apps.datasource.crud.query_execution import call_exec_sql_compat, execute_scoped_query
from apps.datasource.crud.sql_permission import (
    apply_row_permission_filters,
    validate_sql_scope,
    validate_sql_table_scope,
)
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import exec_sql, get_sqlglot_dialect
from common.core.config import settings
from common.core.deps import CurrentUser, SessionDep
from common.utils.utils import AppLogUtil


MAX_SQL_ROWS = settings.ANALYSIS_ASSISTANT_MAX_SQL_ROWS


def sqlglot_write_dialect(datasource: CoreDatasource) -> str | None:
    ds_type = str(getattr(datasource, "type", "") or "")
    dialect = get_sqlglot_dialect(ds_type)
    if dialect:
        return dialect
    if ds_type.casefold() in {"pg", "excel"}:
        return "postgres"
    if ds_type.casefold() in {"redshift", "kingbase"}:
        return "postgres"
    if ds_type.casefold() == "oracle":
        return "oracle"
    if ds_type.casefold() == "ck":
        return "clickhouse"
    return None


def contains_row_limit(sql: str) -> bool:
    return bool(
        re.search(r"\blimit\s+\d+\b", sql, flags=re.IGNORECASE)
        or re.search(r"\btop\s+\(?\d+\)?\b", sql, flags=re.IGNORECASE)
        or re.search(r"\bfetch\s+(?:first|next)\s+\d+\s+rows\s+only\b", sql, flags=re.IGNORECASE)
        or re.search(r"\brownum\s*<=\s*\d+\b", sql, flags=re.IGNORECASE)
    )


def clamp_common_limit_syntax(sql: str) -> str:
    def replace(match: re.Match[str]) -> str:
        value = int(match.group("value"))
        if value <= MAX_SQL_ROWS:
            return match.group(0)
        suffix = match.groupdict().get("suffix") or ""
        return f"{match.group('prefix')}{MAX_SQL_ROWS}{suffix}"

    patterns = (
        r"(?P<prefix>\blimit\s+)(?P<value>\d+)(?P<suffix>\b)(?!\s*,)",
        r"(?P<prefix>\btop\s+\(?)(?P<value>\d+)(?P<suffix>\)?\b)",
        r"(?P<prefix>\bfetch\s+(?:first|next)\s+)(?P<value>\d+)(?P<suffix>\s+rows\s+only\b)",
        r"(?P<prefix>\brownum\s*<=\s*)(?P<value>\d+)(?P<suffix>\b)",
    )
    for pattern in patterns:
        sql = re.sub(pattern, replace, sql, flags=re.IGNORECASE)
    return sql


def _limit_literal(limit: exp.Expression | None) -> exp.Literal | None:
    if limit is None:
        return None
    value = limit.args.get("expression") or limit.args.get("count")
    return value if isinstance(value, exp.Literal) else None


def enforce_max_limit(statement: exp.Expression) -> None:
    limit = statement.args.get("limit")
    if limit is None:
        if not isinstance(statement, exp.Query):
            raise ValueError("综合分析助手只允许执行查询语句")
        statement.set("limit", exp.Limit(expression=exp.Literal.number(MAX_SQL_ROWS)))
        return

    literal = _limit_literal(limit)
    if literal is None:
        return
    try:
        value = int(str(literal.this))
    except (TypeError, ValueError):
        return
    if value <= MAX_SQL_ROWS:
        return
    if "count" in limit.args:
        limit.set("count", exp.Literal.number(MAX_SQL_ROWS))
    else:
        limit.set("expression", exp.Literal.number(MAX_SQL_ROWS))


def supports_limit_wrapper(datasource: CoreDatasource) -> bool:
    ds_type = str(getattr(datasource, "type", "") or "")
    return ds_type.casefold() not in {"sqlserver", "oracle"}


def normalise_sql(sql: str, datasource: CoreDatasource | None = None) -> str:
    sql = (sql or "").strip()
    sql = re.sub(r"^```(?:sql)?", "", sql, flags=re.IGNORECASE).strip()
    sql = re.sub(r"```$", "", sql).strip()
    while sql.endswith(";"):
        sql = sql[:-1].strip()
    if not re.match(r"^(select|with)\b", sql, flags=re.IGNORECASE):
        raise ValueError("综合分析助手只允许执行 SELECT/WITH 查询")
    if ";" in sql:
        raise ValueError("综合分析助手每个数据块只允许执行一条 SELECT/WITH 查询")
    sql = clamp_common_limit_syntax(sql)
    if datasource is None:
        datasource = CoreDatasource(type="pg", name="", configuration="{}", create_by=0, recommended_config=0)
    dialect = sqlglot_write_dialect(datasource)
    try:
        statements = [statement for statement in sqlglot.parse(sql, dialect=dialect) if statement is not None]
        if len(statements) != 1:
            raise ValueError("综合分析助手每个数据块只允许执行一条 SELECT/WITH 查询")
        statement = statements[0]
        enforce_max_limit(statement)
        return statement.sql(dialect=dialect)
    except ValueError:
        raise
    except Exception as exc:
        if contains_row_limit(sql):
            return sql
        if supports_limit_wrapper(datasource):
            return f"select * from ({sql}) as analysis_query_limit limit {MAX_SQL_ROWS}"
        raise ValueError("SQL 解析失败，无法安全应用当前数据库的行数限制") from exc


def _apply_row_permissions(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
        sql: str,
        tables: list[str],
) -> str:
    if not is_normal_user(current_user):
        return sql
    filters = get_row_permission_filters(
        session=session,
        current_user=current_user,
        ds=datasource,
        tables=tables,
    )
    if not filters:
        return sql
    return normalise_sql(apply_row_permission_filters(sql, datasource, filters), datasource)


def prepare_analysis_sql(
        *,
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
        raw_sql: str,
        allowed_tables: list[str],
) -> tuple[str, bool]:
    """Normalize, permission-check, row-rewrite, and re-check one analysis SQL block."""
    sql = normalise_sql(raw_sql, datasource)
    _statements, tables_set, _permission_scope = validate_sql_scope(session, current_user, datasource, sql)
    tables = sorted(tables_set)
    unauthorized_tables = tables_set - set(allowed_tables)
    if unauthorized_tables:
        raise ValueError(f"SQL 包含无权限表：{', '.join(sorted(unauthorized_tables))}")
    before_row_permission_sql = sql
    sql = _apply_row_permissions(session, current_user, datasource, sql, tables)
    rewritten_tables = validate_sql_table_scope(session, current_user, datasource, sql)
    unauthorized_tables = rewritten_tables - set(allowed_tables)
    if unauthorized_tables:
        raise ValueError(f"SQL 包含无权限表：{', '.join(sorted(unauthorized_tables))}")
    return sql, sql != before_row_permission_sql


def execute_analysis_sql(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    datasource: CoreDatasource,
    sql: str,
    record_id: int | str | None = None,
    task_id: str | None = None,
    model_id: int | str | None = None,
    custom_agent_id: int | str | None = None,
    allow_row_permission_filter_star: bool = False,
) -> dict[str, Any]:
    """Run analysis assistant SQL through the shared scoped query executor."""
    result = execute_scoped_query(
        session=session,
        current_user=current_user,
        datasource_id=datasource.id,
        sql=sql,
        purpose="analysis_assistant",
        row_limit=settings.ANALYSIS_ASSISTANT_MAX_SQL_ROWS,
        executor=lambda ds, execute_sql_text, origin_column=False,
                        execution_timeout_seconds=None, fetch_limit=None: call_exec_sql_compat(
            exec_sql,
            ds=ds,
            sql=execute_sql_text,
            origin_column=origin_column,
            execution_timeout_seconds=execution_timeout_seconds,
            fetch_limit=fetch_limit,
        ),
        apply_row_permissions=False,
        allow_row_permission_filter_star=allow_row_permission_filter_star,
        record_id=record_id,
        task_id=task_id,
        model_id=model_id,
        custom_agent_id=custom_agent_id,
    )
    if result.get("status") == "failed":
        AppLogUtil.error(
            "analysis_assistant_sql_failed "
            f"datasource_id={getattr(datasource, 'id', None)} message={result.get('message')}"
        )
        raise ValueError(result.get("message") or "数据计算失败")
    return result
