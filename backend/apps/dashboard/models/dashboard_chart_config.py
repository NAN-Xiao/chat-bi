"""看板图表 V2 配置和日期筛选请求模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


DateParameterType = Literal["date", "yyyymmdd_number", "yyyymmdd_text", "timestamp"]
DashboardChartConfigStatus = Literal["none", "v2", "legacy", "migration_required", "invalid"]


class DashboardDateFilterConfig(BaseModel):
    """canvas_view_info 中保存的独立日期筛选配置。"""

    enabled: bool = True
    parameter_type: DateParameterType = Field(alias="parameterType")
    expression: dict[str, Any]

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class DashboardDateFilterRequest(BaseModel):
    """sql_preview 使用的日期请求；自定义范围只在本次请求生效。"""

    parameter_type: DateParameterType
    expression: dict[str, Any] | None = None
    custom_start: str = ""
    custom_end: str = ""

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class DashboardChartConfigResolution:
    """单个图表日期配置的确定性解析结果。"""

    status: DashboardChartConfigStatus
    date_filter: DashboardDateFilterRequest | None
    error_type: str = ""
    reason: str = ""
