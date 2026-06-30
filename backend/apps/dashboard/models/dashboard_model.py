from sqlmodel import SQLModel, Field
from sqlalchemy import String, Column, Text, SmallInteger, BigInteger, Integer, Index
from typing import Any, Optional, List, Literal, Dict
from pydantic import BaseModel

class CoreDashboard(SQLModel, table=True):
    __tablename__ = "core_dashboard"
    __table_args__ = (
        Index("idx_core_dashboard_tenant_id", "tenant_id"),
    )
    id: str = Field(
        sa_column=Column(String(50), nullable=False, primary_key=True)
    )
    tenant_id: int = Field(
        default=1,
        sa_column=Column(BigInteger, nullable=False, server_default="1")
    )
    name: str = Field(
        default=None,
        max_length=255,
        sa_column=Column(String(255), nullable=True)
    )
    pid: str = Field(
        default=None,
        max_length=50,
        sa_column=Column(String(50), nullable=True)
    )
    datasource: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True)
    )
    org_id: str = Field(
        default=None,
        max_length=50,
        sa_column=Column(String(50), nullable=True)
    )
    level: int = Field(
        default=None,
        sa_column=Column(Integer, nullable=True)
    )
    node_type: str = Field(
        default=None,
        max_length=255,
        sa_column=Column(String(255), nullable=True)
    )
    type: str = Field(
        default=None,
        max_length=50,
        sa_column=Column(String(50), nullable=True)
    )
    canvas_style_data: str = Field(
        default=None,
        sa_column=Column(Text, nullable=True)
    )
    component_data: str = Field(
        default=None,
        sa_column=Column(Text, nullable=True)
    )
    canvas_view_info: str = Field(
        default=None,
        sa_column=Column(Text, nullable=True)
    )
    mobile_layout: int = Field(
        default=0,
        sa_column=Column(SmallInteger, nullable=True)
    )
    status: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=True)
    )
    self_watermark_status: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=True)
    )
    is_default: int = Field(
        default=0,
        sa_column=Column(SmallInteger, nullable=False, server_default="0")
    )
    sort: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=True)
    )
    create_time: int = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True)
    )
    create_by: str = Field(
        default=None,
        max_length=255,
        sa_column=Column(String(255), nullable=True)
    )
    update_time: int = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True)
    )
    update_by: str = Field(
        default=None,
        max_length=255,
        sa_column=Column(String(255), nullable=True)
    )
    remark: str = Field(
        default=None,
        max_length=255,
        sa_column=Column(String(255), nullable=True)
    )
    source: str = Field(
        default=None,
        max_length=255,
        sa_column=Column(String(255), nullable=True)
    )
    delete_flag: int = Field(
        default=0,
        sa_column=Column(SmallInteger, nullable=True)
    )
    delete_time: int = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True)
    )
    delete_by: str = Field(
        default=None,
        max_length=255,
        sa_column=Column(String(255), nullable=True)
    )
    version: int = Field(
        default=3,
        sa_column=Column(Integer, nullable=True)
    )
    content_id: str = Field(
        default='0',
        max_length=50,
        sa_column=Column(String(50), nullable=True)
    )
    check_version: str = Field(
        default='1',
        max_length=50,
        sa_column=Column(String(50), nullable=True)
    )


class CoreDashboardShare(SQLModel, table=True):
    __tablename__ = "core_dashboard_share"
    __table_args__ = (
        Index("idx_core_dashboard_share_tenant_id", "tenant_id"),
    )
    id: str = Field(
        sa_column=Column(String(50), nullable=False, primary_key=True)
    )
    tenant_id: int = Field(
        default=1,
        sa_column=Column(BigInteger, nullable=False, server_default="1")
    )
    name: str = Field(
        default=None,
        max_length=255,
        sa_column=Column(String(255), nullable=True)
    )
    datasource: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True)
    )
    share_type: str = Field(
        default="dashboard",
        max_length=32,
        sa_column=Column(String(32), nullable=False)
    )
    source_dashboard_id: str = Field(
        default=None,
        max_length=50,
        sa_column=Column(String(50), nullable=True)
    )
    source_view_id: str = Field(
        default=None,
        max_length=50,
        sa_column=Column(String(50), nullable=True)
    )
    component_data: str = Field(
        default="[]",
        sa_column=Column(Text, nullable=True)
    )
    canvas_style_data: str = Field(
        default="{}",
        sa_column=Column(Text, nullable=True)
    )
    canvas_view_info: str = Field(
        default="{}",
        sa_column=Column(Text, nullable=True)
    )
    preview_image: str = Field(
        default=None,
        sa_column=Column(Text, nullable=True)
    )
    create_time: int = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True)
    )
    create_by: str = Field(
        default=None,
        max_length=255,
        sa_column=Column(String(255), nullable=True)
    )
    update_time: int = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True)
    )
    update_by: str = Field(
        default=None,
        max_length=255,
        sa_column=Column(String(255), nullable=True)
    )
    delete_flag: int = Field(
        default=0,
        sa_column=Column(SmallInteger, nullable=True)
    )
    delete_time: int = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True)
    )
    delete_by: str = Field(
        default=None,
        max_length=255,
        sa_column=Column(String(255), nullable=True)
    )


class DashboardBaseResponse(BaseModel):
    id: Optional[str] = None
    tenant_id: Optional[int] = None
    name: Optional[str] = None
    pid: Optional[str] = None
    datasource: Optional[int] = None
    node_type: Optional[str] = None
    leaf: Optional[bool] = False
    type: Optional[str] = None
    status: Optional[int] = None
    source: Optional[str] = None
    content_id: Optional[str] = None
    remark: Optional[str] = None
    create_by: Optional[str] = None
    update_by: Optional[str] = None
    create_time: Optional[int] = None
    update_time: Optional[int] = None
    sort: Optional[int] = 0
    can_edit: Optional[bool] = False
    can_share: Optional[bool] = False
    can_set_default: Optional[bool] = False
    is_default: Optional[bool] = False
    is_shared: Optional[bool] = False
    is_public: Optional[bool] = False
    can_copy_to_platform_template: Optional[bool] = False
    source_dashboard_id: Optional[str] = None
    source_dashboard_name: Optional[str] = None
    source_tenant_id: Optional[int] = None
    source_tenant_name: Optional[str] = None
    source_datasource_id: Optional[int] = None
    source_datasource_name: Optional[str] = None
    share_id: Optional[str] = None
    children: List['DashboardBaseResponse'] = []


class DashboardShareListResponse(BaseModel):
    id: Optional[str] = None
    tenant_id: Optional[int] = None
    name: Optional[str] = None
    datasource: Optional[int] = None
    datasource_name: Optional[str] = None
    share_type: Optional[str] = None
    source_dashboard_id: Optional[str] = None
    source_view_id: Optional[str] = None
    create_time: Optional[int] = None
    update_time: Optional[int] = None
    create_name: Optional[str] = None
    update_name: Optional[str] = None
    can_use: Optional[bool] = False
    can_delete: Optional[bool] = False
    preview_image: Optional[str] = None

class DashboardResponse(CoreDashboard):
    update_name: Optional[str] = None
    create_name: Optional[str] = None

class BaseDashboard(BaseModel):
    id: str = ''
    tenant_id: Optional[int] = None
    name: str = ''
    pid: str = ''
    datasource: Optional[int] = None
    org_id: str = ''
    type: str = ''
    node_type: str = ''
    status: Optional[int] = None
    source: Optional[str] = None
    content_id: Optional[str] = None
    level: int = 0
    create_by: int = 0
    is_default: Optional[bool] = False
    sort: Optional[int] = 0

class QueryDashboard(BaseDashboard):
    opt: str = ''
    include_data: bool = True


# dashboard create obj
class CreateDashboard(QueryDashboard):
    canvas_style_data: str =''
    component_data: str = ''
    canvas_view_info: str = ''
    description: str = ''


class DashboardPivotRequest(BaseModel):
    enabled: bool = False
    time_field: str = ''
    metric_field: str = ''
    metric_fields: List[str] = Field(default_factory=list)
    metric_aggregations: Dict[str, Literal["sum", "avg", "min", "max", "count"]] = Field(default_factory=dict)
    group_field: str = ''
    group_enabled: bool = True
    dimensions: List[Dict[str, Any]] = Field(default_factory=list)
    range_enabled: bool = True
    granularity: Literal["day", "week", "month"] = "day"
    range: Literal["source", "7d", "14d", "30d", "90d", "all", "custom"] = "source"
    custom_start: str = ''
    custom_end: str = ''
    aggregation: Literal["sum", "avg", "min", "max", "count"] = "sum"


class DashboardSqlPreview(BaseModel):
    datasource: int
    sql: str = ''
    pivot: Optional[DashboardPivotRequest] = None
    cache_only: bool = False
    force_refresh: bool = False


class DashboardDefaultRequest(BaseModel):
    dashboard_id: str
    is_default: bool = True


class DashboardDefaultSortRequest(BaseModel):
    ordered_ids: List[str]


class DashboardOrderItem(BaseModel):
    id: str
    pid: str = "root"
    sort: int = 0


class DashboardReorderRequest(BaseModel):
    scope: Literal["default", "my"] = "my"
    items: List[DashboardOrderItem]


class DashboardDefaultCopyRequest(BaseModel):
    dashboard_id: str


class DashboardPlatformTemplateCopyRequest(BaseModel):
    dashboard_id: str
    name: str = ''


class DashboardPlatformTemplateUseRequest(BaseModel):
    template_id: str = ''
    template_ids: List[str] = Field(default_factory=list)
    name: str = ''


class DashboardShareRequest(BaseModel):
    dashboard_id: str
    share_type: Literal["dashboard", "chart"] = "dashboard"
    name: str = ''
    source_view_id: str = ''
    component_data: str = ''
    canvas_style_data: str = ''
    canvas_view_info: str = ''
    preview_image: str = ''


class DashboardShareListQuery(BaseModel):
    keyword: str = ''


class SharedDashboardQuery(BaseModel):
    id: str


class SharedDashboardUseRequest(BaseModel):
    id: str


class DashboardDeliveryCreateRequest(BaseModel):
    target_tenant_id: Optional[int | str] = None
    target_tenant_public_id: str = ''
    target_datasource_id: Optional[int] = None
    source_dashboard_ids: List[str] = []
    name: str = ''
    publish_as_default: bool = True


class DashboardDeliveryChartUpdateRequest(BaseModel):
    draft_dashboard_id: str
    view_id: str
    sql: str = ''
    chart: dict[str, Any] = {}


class DashboardDeliveryOrderUpdateRequest(BaseModel):
    ordered_dashboard_ids: List[str]


class DashboardDeliveryCanvasUpdateRequest(BaseModel):
    draft_dashboard_id: str
    name: str = ''
    component_data: str = ''
    canvas_style_data: str = ''
    canvas_view_info: str = ''


class DashboardDeliveryPublishRequest(BaseModel):
    publish_as_default: bool = True


class DashboardDeliverySqlPreview(BaseModel):
    target_tenant_id: Optional[int | str] = None
    target_tenant_public_id: str = ''
    target_datasource_id: Optional[int] = None
    sql: str = ''
