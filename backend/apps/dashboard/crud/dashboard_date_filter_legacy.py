"""迁移期 V1 日期配置读取器。

该模块只负责把完整旧结构转换为内存中的 V2 请求，不写回画布，也不猜测缺失配置。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from apps.dashboard.crud.dashboard_date_filter import (
    has_dashboard_date_filter_parameters,
    resolve_dashboard_date_expression,
    validate_dashboard_date_parameter_sql,
)
from apps.dashboard.models.dashboard_chart_config import (
    DashboardChartConfigResolution,
    DashboardDateFilterConfig,
    DashboardDateFilterRequest,
)


MIGRATION_REQUIRED_ERROR = "dashboard_date_filter_migration_required"
INVALID_TEMPLATE_ERROR = "dashboard_date_filter_invalid_template"


def _resolution(
    status: str,
    date_filter: DashboardDateFilterRequest | None = None,
    *,
    error_type: str = "",
    reason: str = "",
) -> DashboardChartConfigResolution:
    return DashboardChartConfigResolution(
        status=status,  # type: ignore[arg-type]
        date_filter=date_filter,
        error_type=error_type,
        reason=reason,
    )


def _pivot(view_info: Mapping[str, Any]) -> dict[str, Any]:
    value = view_info.get("pivot")
    return value if isinstance(value, dict) else {}


def _validate_expression(expression: Any) -> bool:
    try:
        resolve_dashboard_date_expression(expression, today=date(2026, 1, 1))
    except (TypeError, ValueError):
        return False
    return True


def _request_from_v2(sql: str, raw_filter: Any) -> DashboardChartConfigResolution:
    try:
        config = DashboardDateFilterConfig.model_validate(raw_filter)
    except Exception:
        return _resolution(
            "invalid",
            error_type=INVALID_TEMPLATE_ERROR,
            reason="invalid_v2_date_filter",
        )
    if config.enabled is not True or not _validate_expression(config.expression):
        return _resolution(
            "invalid",
            error_type=INVALID_TEMPLATE_ERROR,
            reason="disabled_or_invalid_v2_date_filter",
        )
    parameter_error = validate_dashboard_date_parameter_sql(sql, config.parameter_type)
    if parameter_error:
        return _resolution(
            "invalid",
            error_type=INVALID_TEMPLATE_ERROR,
            reason=parameter_error,
        )
    return _resolution(
        "v2",
        DashboardDateFilterRequest(
            parameter_type=config.parameter_type,
            expression=config.expression,
        ),
    )


def _request_from_v1(sql: str, pivot: dict[str, Any]) -> DashboardChartConfigResolution:
    parameter_type = pivot.get("date_parameter_type")
    expression = pivot.get("date_expression")
    if not parameter_type or expression is None:
        return _resolution(
            "migration_required",
            error_type=MIGRATION_REQUIRED_ERROR,
            reason="incomplete_legacy_date_filter",
        )
    parameter_error = validate_dashboard_date_parameter_sql(sql, str(parameter_type))
    if parameter_error or not _validate_expression(expression):
        return _resolution(
            "invalid",
            error_type=INVALID_TEMPLATE_ERROR,
            reason=parameter_error or "invalid_legacy_date_expression",
        )
    try:
        request = DashboardDateFilterRequest(
            parameter_type=parameter_type,
            expression=expression,
        )
    except Exception:
        return _resolution(
            "invalid",
            error_type=INVALID_TEMPLATE_ERROR,
            reason="invalid_legacy_date_filter",
        )
    return _resolution("legacy", request)


def resolve_dashboard_chart_date_filter(
    view_info: Mapping[str, Any] | None,
    *,
    allow_legacy: bool,
) -> DashboardChartConfigResolution:
    """解析单图表日期配置，旧结构只允许确定性读取。"""

    if not isinstance(view_info, Mapping):
        return _resolution("none")
    sql = str(view_info.get("sql") or "")
    has_tokens = has_dashboard_date_filter_parameters(sql)
    raw_v2 = view_info.get("dateFilter")
    config_version = view_info.get("configVersion")
    if config_version == 2:
        if raw_v2 is None:
            return _resolution(
                "migration_required" if has_tokens else "none",
                error_type=MIGRATION_REQUIRED_ERROR if has_tokens else "",
                reason="missing_v2_date_filter" if has_tokens else "",
            )
        return _request_from_v2(sql, raw_v2)
    if raw_v2 is not None:
        return _resolution(
            "invalid",
            error_type=INVALID_TEMPLATE_ERROR,
            reason="date_filter_requires_config_version_2",
        )
    if not has_tokens:
        return _resolution("none")
    if not allow_legacy:
        return _resolution(
            "migration_required",
            error_type=MIGRATION_REQUIRED_ERROR,
            reason="legacy_reader_disabled",
        )
    return _request_from_v1(sql, _pivot(view_info))
