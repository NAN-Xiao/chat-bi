"""ROI 看板独立 SQL 执行边界。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from sqlmodel import select

from apps.datasource.crud.sql_engine_executor import _execute_after_validation
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import check_sql_read
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
) -> dict[str, Any]:
    """集中封装底层已验证执行入口，禁止私有调用扩散到 ROI 其他模块。"""
    return _execute_after_validation(
        ds=datasource,
        sql=sql,
        origin_column=True,
        query_timeout=query_timeout,
    )


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

    is_safe, reason = check_sql_read(sql, datasource)
    if not is_safe:
        raise HTTPException(
            status_code=400,
            detail=f"ROI SQL 仅允许单条只读查询：{reason}",
        )

    started_at = time.perf_counter()
    raw = _run_validated_read(
        datasource=datasource,
        sql=sql,
        query_timeout=settings.DASHBOARD_SQL_PREVIEW_QUERY_TIMEOUT_SECONDS,
    )
    result = normalize_roi_query_result(raw)
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    response_bytes = len(
        json.dumps(result.data, ensure_ascii=False, default=str).encode("utf-8")
    )
    AppLogUtil.info(
        "ROI query completed: "
        f"tenant_id={tenant_id}, user_id={int(current_user.id)}, "
        f"datasource_id={datasource_id}, elapsed_ms={elapsed_ms}, "
        f"row_count={len(result.data)}, response_bytes={response_bytes}, "
        f"status={result.status}"
    )
    return result


__all__ = ["RoiQueryResult", "execute_roi_read_query", "normalize_roi_query_result"]
