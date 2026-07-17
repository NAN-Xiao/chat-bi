"""ROI 看板独立 SQL 执行边界。"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import sqlparse
from fastapi import HTTPException
from sqlparse import tokens as sqlparse_tokens
from sqlmodel import select

from apps.datasource.crud.sql_engine_executor import _execute_after_validation
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import (
    DANGEROUS_PATTERNS,
    get_dangerous_functions,
    normalize_sql_safety_ds_type,
    normalize_sql_function_name,
    supports_controlled_query_timeout,
)
from apps.roi_dashboard.models import CoreRoiWorkspaceConfig
from apps.roi_dashboard.permissions import (
    has_roi_datasource_access,
    require_roi_workspace_admin,
)
from common.core.config import settings
from common.core.deps import CurrentUser, SessionDep
from common.utils.utils import AppLogUtil


@dataclass(slots=True)
class RoiQueryResult:
    """ROI 查询的稳定返回结构，不附加普通看板权限或行数限制。"""

    status: str
    fields: list[str] = field(default_factory=list)
    data: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""


def _load_active_roi_config(
    session: SessionDep,
    tenant_id: int,
) -> CoreRoiWorkspaceConfig:
    config = session.exec(
        select(CoreRoiWorkspaceConfig).where(
            CoreRoiWorkspaceConfig.tenant_id == tenant_id,
            CoreRoiWorkspaceConfig.deleted.is_(False),
        )
    ).first()
    if config is None:
        raise HTTPException(status_code=409, detail="当前工作空间尚未配置 ROI 数据源")
    return config


def _run_validated_read(
    *,
    datasource: CoreDatasource,
    sql: str,
    query_timeout: int,
    max_result_rows: int | None,
) -> dict[str, Any]:
    """集中封装底层已验证执行入口，禁止私有调用扩散到 ROI 其他模块。"""
    return _execute_after_validation(
        ds=datasource,
        sql=sql,
        origin_column=True,
        query_timeout=query_timeout,
        max_result_rows=max_result_rows,
        require_controlled_timeout=True,
        skip_read_validation=True,
    )


ROI_TIMEOUT_SUPPORTED_TYPES = frozenset(
    {"pg", "mysql", "sqlserver", "dm", "doris", "starrocks", "kingbase"}
)

_ROI_FORBIDDEN_KEYWORDS = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "CREATE",
        "DROP",
        "ALTER",
        "TRUNCATE",
        "MERGE",
        "COPY",
        "REPLACE",
        "GRANT",
        "REVOKE",
        "USE",
        "SET",
        "CALL",
        "INTO",
    }
)

_ROI_INCOMPLETE_TRAILING_KEYWORDS = frozenset(
    {
        "SELECT",
        "WITH",
        "FROM",
        "JOIN",
        "ON",
        "WHERE",
        "GROUP",
        "ORDER",
        "BY",
        "HAVING",
        "LIMIT",
        "OFFSET",
        "UNION",
        "AS",
        "WHEN",
        "THEN",
        "ELSE",
    }
)

_ROI_DANGEROUS_READ_PATTERNS = (
    r"\bNEXT\s+VALUE\s+FOR\b",
    r"\.\s*NEXTVAL\b",
)


def _validate_roi_read_sql_tokens(sql: str, datasource: CoreDatasource) -> None:
    """不解析数据库方言，以词法边界和数据库只读事务双重保护。"""
    statements = [statement for statement in sqlparse.parse(sql) if str(statement).strip()]
    if len(statements) != 1:
        raise ValueError("SQL 必须且只能包含一条语句")

    significant_tokens = []
    for token in statements[0].flatten():
        if token.is_whitespace or token.ttype in sqlparse_tokens.Comment:
            continue
        significant_tokens.append(token)
    if not significant_tokens:
        raise ValueError("SQL 不能为空")

    first_keyword = significant_tokens[0].normalized.upper()
    if first_keyword not in {"SELECT", "WITH"}:
        raise ValueError("SQL 根语句不是只读查询")
    if significant_tokens[-1].normalized.upper() in _ROI_INCOMPLETE_TRAILING_KEYWORDS:
        raise ValueError("SQL 查询结构不完整")

    searchable_parts: list[str] = []
    for token in significant_tokens:
        if token.ttype in sqlparse_tokens.Literal.String:
            searchable_parts.append("''")
            continue
        normalized = token.normalized.upper()
        if normalized in _ROI_FORBIDDEN_KEYWORDS:
            raise ValueError(f"SQL 包含写操作或命令：{normalized}")
        searchable_parts.append(token.value)

    searchable_sql = " ".join(searchable_parts)
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, searchable_sql, re.IGNORECASE):
            raise ValueError("SQL 包含危险读取模式")
    for pattern in _ROI_DANGEROUS_READ_PATTERNS:
        if re.search(pattern, searchable_sql, re.IGNORECASE):
            raise ValueError("SQL 包含序列取值副作用")

    dangerous_functions = {
        normalize_sql_function_name(name)
        for name in get_dangerous_functions(datasource.type)
    }
    dangerous_functions.add("nextval")
    for function_name in dangerous_functions:
        if re.search(
            rf"(?<![\w$]){re.escape(function_name)}\s*\(",
            searchable_sql,
            re.IGNORECASE,
        ):
            raise ValueError("SQL 包含危险函数")


def validate_roi_read_sql(sql: str, datasource: CoreDatasource) -> None:
    """不解析数据库方言，只校验 ROI 原始 SQL 的单条只读边界。"""
    _validate_roi_read_sql_tokens(sql, datasource)


def _normalize_rows(raw: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    raw_rows = list(raw.get("data") or raw.get("rows") or [])
    raw_fields = raw.get("fields") or raw.get("columns") or []
    fields = [str(value) for value in raw_fields]
    if raw_rows and isinstance(raw_rows[0], dict):
        rows = [dict(row) for row in raw_rows]
        if not fields:
            fields = [str(value) for value in rows[0].keys()]
        return fields, rows

    rows = [
        {
            fields[index] if index < len(fields) else str(index): value
            for index, value in enumerate(row)
        }
        for row in raw_rows
    ]
    return fields, rows


def normalize_roi_query_result(raw: dict[str, Any]) -> RoiQueryResult:
    status = str(raw.get("status") or "success")
    fields, rows = _normalize_rows(raw)
    return RoiQueryResult(
        status=status,
        fields=fields,
        data=rows,
        message=str(raw.get("message") or ""),
    )


def execute_roi_read_query(
    session: SessionDep,
    current_user: CurrentUser,
    sql: str,
) -> RoiQueryResult:
    """按 ROI 专用授权执行原始只读 SQL，不套用普通查询权限与截断。"""
    context = require_roi_workspace_admin(current_user)
    tenant_id = int(context.management_tenant_id)
    config = _load_active_roi_config(session, tenant_id)
    datasource_id = int(config.datasource_id)
    if not has_roi_datasource_access(session, current_user, datasource_id):
        raise HTTPException(status_code=403, detail="当前账号无此数据源权限")

    datasource = session.get(CoreDatasource, datasource_id)
    if datasource is None:
        raise HTTPException(status_code=409, detail="ROI 数据源不存在或已停用")

    started_at = time.perf_counter()
    try:
        validate_roi_read_sql(sql, datasource)
        datasource_type = normalize_sql_safety_ds_type(datasource.type)
        if (
            datasource_type not in ROI_TIMEOUT_SUPPORTED_TYPES
            or not supports_controlled_query_timeout(datasource.type)
        ):
            detail = (
                "当前数据源类型不支持受控且无截断 ROI 查询"
                if datasource_type == "es"
                else "当前数据源类型不支持受控查询超时"
            )
            raise HTTPException(
                status_code=400,
                detail=detail,
            )
        raw = _run_validated_read(
            datasource=datasource,
            sql=sql,
            query_timeout=settings.DASHBOARD_SQL_PREVIEW_QUERY_TIMEOUT_SECONDS,
            max_result_rows=None,
        )
    except HTTPException:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        AppLogUtil.warning(
            "ROI query failed: "
            f"tenant_id={tenant_id}, user_id={int(current_user.id)}, "
            f"datasource_id={datasource_id}, elapsed_ms={elapsed_ms}, status=failed"
        )
        raise
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        AppLogUtil.warning(
            "ROI query failed: "
            f"tenant_id={tenant_id}, user_id={int(current_user.id)}, "
            f"datasource_id={datasource_id}, elapsed_ms={elapsed_ms}, status=failed, "
            f"error_type={type(exc).__name__}"
        )
        raise HTTPException(
            status_code=400,
            detail="ROI SQL 仅允许单条只读查询或查询执行失败",
        ) from exc
    result = normalize_roi_query_result(raw)
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    response_bytes = len(
        json.dumps(result.data, ensure_ascii=False, default=str).encode("utf-8")
    )
    log_message = (
        "ROI query completed: "
        f"tenant_id={tenant_id}, user_id={int(current_user.id)}, "
        f"datasource_id={datasource_id}, elapsed_ms={elapsed_ms}, "
        f"row_count={len(result.data)}, response_bytes={response_bytes}, "
        f"status={result.status}"
    )
    if result.status == "success":
        AppLogUtil.info(log_message)
    else:
        AppLogUtil.warning(log_message)
    return result


__all__ = [
    "RoiQueryResult",
    "execute_roi_read_query",
    "normalize_roi_query_result",
    "validate_roi_read_sql",
]
