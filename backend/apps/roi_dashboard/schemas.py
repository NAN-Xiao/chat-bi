"""ROI 专用看板接口数据结构。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LayoutSpan = Literal["full", "half", "third"]


def _strip_required(value: str, label: str, max_length: int | None = None) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{label}不能为空")
    if max_length is not None and len(stripped) > max_length:
        raise ValueError(f"{label}长度不能超过 {max_length} 个字符")
    return stripped


class RoiDashboardCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _strip_required(value, "看板名称", 64)


class RoiDashboardUpdate(BaseModel):
    name: str | None = None
    status: int | None = None
    version: int

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return None if value is None else _strip_required(value, "看板名称", 64)


class RoiChartPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    sql: str
    chart_type: str
    chart_config: dict[str, Any] = Field(default_factory=dict)
    layout_span: LayoutSpan = "full"

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _strip_required(value, "图表标题", 255)

    @field_validator("sql")
    @classmethod
    def validate_sql(cls, value: str) -> str:
        return _strip_required(value, "SQL")

    @field_validator("chart_type")
    @classmethod
    def validate_chart_type(cls, value: str) -> str:
        return _strip_required(value, "图表类型")


class RoiChartCreate(RoiChartPreviewRequest):
    sort: int = 0


class RoiChartUpdate(RoiChartCreate):
    version: int


class RoiDashboardOrderItem(BaseModel):
    id: str
    sort: int
    version: int


class RoiDashboardReorderRequest(BaseModel):
    items: list[RoiDashboardOrderItem]


class RoiChartOrderItem(BaseModel):
    id: str
    sort: int
    layout_span: LayoutSpan
    version: int


class RoiChartReorderRequest(BaseModel):
    items: list[RoiChartOrderItem]


class _RoiResponseBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator(
        "id",
        "tenant_id",
        "roi_dashboard_id",
        "create_by",
        "update_by",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def stringify_snowflake_id(cls, value: object) -> str | None:
        return None if value is None else str(value)


class RoiConfigResponse(_RoiResponseBase):
    id: str
    tenant_id: str
    datasource_id: int
    datasource_name: str | None
    version: int
    can_execute: bool
    can_edit: bool


class RoiDashboardResponse(_RoiResponseBase):
    id: str
    tenant_id: str
    name: str
    sort: int
    status: int
    version: int
    create_by: str | None
    update_by: str | None
    create_time: int
    update_time: int


class RoiChartResponse(_RoiResponseBase):
    id: str
    tenant_id: str
    roi_dashboard_id: str
    title: str
    sql: str
    chart_type: str
    chart_config: dict[str, Any]
    layout_span: LayoutSpan
    sort: int
    status: int
    version: int
    create_by: str | None
    update_by: str | None
    create_time: int
    update_time: int


class RoiChartPreviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    fields: list[str] = Field(default_factory=list)
    data: list[dict[str, Any]] = Field(default_factory=list)
    message: str = ""


class RoiChartListResponse(RoiChartResponse):
    sql: str | None
    can_execute: bool
    can_edit: bool
    error: str | None = None
    query_result: RoiChartPreviewResponse | None = None

    @model_validator(mode="after")
    def hide_sql_without_datasource_access(self):
        if not self.can_execute:
            self.sql = None
        return self
