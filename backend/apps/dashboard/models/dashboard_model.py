"""
脚本说明：这个脚本定义仪表盘用到的数据表或数据对象，便于代码和数据库对齐。
"""
from sqlmodel import SQLModel, Field
from sqlalchemy import String, Column, Text, SmallInteger, BigInteger, Integer, Index, UniqueConstraint
from typing import Any, Optional, List, Literal, Dict
from pydantic import BaseModel

class CoreDashboard(SQLModel, table=True):
    """
    类说明：CoreDashboard 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
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
    external_mcp_server_id: Optional[int] = Field(
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


class CoreDashboardTree(SQLModel, table=True):
    """
    类说明：CoreDashboardTree 保存不同看板树范围下的节点位置。
    """
    __tablename__ = "core_dashboard_tree"
    __table_args__ = (
        UniqueConstraint("tenant_id", "scope", "dashboard_id", name="uq_core_dashboard_tree_scope_dashboard"),
        Index("idx_core_dashboard_tree_tenant_scope", "tenant_id", "scope"),
        Index("idx_core_dashboard_tree_dashboard", "dashboard_id"),
    )
    id: str = Field(
        sa_column=Column(String(50), nullable=False, primary_key=True)
    )
    tenant_id: int = Field(
        default=1,
        sa_column=Column(BigInteger, nullable=False, server_default="1")
    )
    scope: str = Field(
        default="my",
        max_length=32,
        sa_column=Column(String(32), nullable=False)
    )
    dashboard_id: str = Field(
        default=None,
        max_length=50,
        sa_column=Column(String(50), nullable=False)
    )
    parent_id: str = Field(
        default="root",
        max_length=50,
        sa_column=Column(String(50), nullable=False, server_default="root")
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


class CoreDashboardShare(SQLModel, table=True):
    """
    类说明：CoreDashboardShare 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
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
    """
    类说明：DashboardBaseResponse 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    id: Optional[str] = None
    tenant_id: Optional[int | str] = None
    name: Optional[str] = None
    pid: Optional[str] = None
    datasource: Optional[int] = None
    external_mcp_server_id: Optional[int | str] = None
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
    is_default_tree: Optional[bool] = False
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
    """
    类说明：DashboardShareListResponse 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
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
    """
    类说明：DashboardResponse 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    update_name: Optional[str] = None
    create_name: Optional[str] = None

class BaseDashboard(BaseModel):
    """
    类说明：BaseDashboard 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    id: str = ''
    tenant_id: Optional[int | str] = None
    name: str = ''
    pid: str = ''
    datasource: Optional[int] = None
    external_mcp_server_id: Optional[int | str] = None
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
    """
    类说明：QueryDashboard 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    opt: str = ''
    include_data: bool = True


# 仪表盘创建对象
class CreateDashboard(QueryDashboard):
    """
    类说明：CreateDashboard 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    canvas_style_data: str =''
    component_data: str = ''
    canvas_view_info: str = ''
    description: str = ''


class DashboardPivotRequest(BaseModel):
    """
    类说明：DashboardPivotRequest 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    enabled: bool = False
    client_filter_only: bool = False
    time_field: str = ''
    metric_field: str = ''
    metric_fields: List[str] = Field(default_factory=list)
    metric_aggregations: Dict[str, Literal["sum", "avg", "min", "max", "count"]] = Field(default_factory=dict)
    group_field: str = ''
    group_enabled: bool = True
    group_values: List[str] = Field(default_factory=list)
    dimensions: List[Dict[str, Any]] = Field(default_factory=list)
    range_enabled: bool = True
    granularity: Literal["day", "week", "month"] = "day"
    range: Literal["source", "7d", "14d", "30d", "90d", "all", "custom"] = "source"
    custom_start: str = ''
    custom_end: str = ''
    aggregation: Literal["sum", "avg", "min", "max", "count"] = "sum"


class DashboardSqlPreview(BaseModel):
    """
    类说明：DashboardSqlPreview 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    datasource: int
    sql: str = ''
    pivot: Optional[DashboardPivotRequest] = None
    cache_only: bool = False
    force_refresh: bool = False


class DashboardDefaultRequest(BaseModel):
    """
    类说明：DashboardDefaultRequest 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    dashboard_id: str
    is_default: bool = True


class DashboardDefaultSortRequest(BaseModel):
    """
    类说明：DashboardDefaultSortRequest 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    ordered_ids: List[str]


class DashboardOrderItem(BaseModel):
    """
    类说明：DashboardOrderItem 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    id: str
    pid: str = "root"
    sort: int = 0


class DashboardReorderRequest(BaseModel):
    """
    类说明：DashboardReorderRequest 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    scope: Literal["default", "my"] = "my"
    items: List[DashboardOrderItem]


class DashboardDefaultCopyRequest(BaseModel):
    """
    类说明：DashboardDefaultCopyRequest 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    dashboard_id: str


class DashboardPlatformTemplateCopyRequest(BaseModel):
    """
    类说明：DashboardPlatformTemplateCopyRequest 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    dashboard_id: str
    name: str = ''


class DashboardPlatformTemplateUseRequest(BaseModel):
    """
    类说明：DashboardPlatformTemplateUseRequest 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    template_id: str = ''
    template_ids: List[str] = Field(default_factory=list)
    name: str = ''


class DashboardShareRequest(BaseModel):
    """
    类说明：DashboardShareRequest 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    dashboard_id: str
    share_type: Literal["dashboard", "chart"] = "dashboard"
    name: str = ''
    source_view_id: str = ''
    component_data: str = ''
    canvas_style_data: str = ''
    canvas_view_info: str = ''
    preview_image: str = ''


class DashboardShareListQuery(BaseModel):
    """
    类说明：DashboardShareListQuery 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    keyword: str = ''


class SharedDashboardQuery(BaseModel):
    """
    类说明：SharedDashboardQuery 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    id: str


class SharedDashboardUseRequest(BaseModel):
    """
    类说明：SharedDashboardUseRequest 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    id: str


class DashboardDeliveryCreateRequest(BaseModel):
    """
    类说明：DashboardDeliveryCreateRequest 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    target_tenant_id: Optional[int | str] = None
    target_tenant_public_id: str = ''
    target_datasource_id: Optional[int] = None
    source_dashboard_ids: List[str] = []
    name: str = ''
    publish_as_default: bool = True


class DashboardDeliveryChartUpdateRequest(BaseModel):
    """
    类说明：DashboardDeliveryChartUpdateRequest 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    draft_dashboard_id: str
    view_id: str
    sql: str = ''
    chart: dict[str, Any] = {}


class DashboardDeliveryOrderUpdateRequest(BaseModel):
    """
    类说明：DashboardDeliveryOrderUpdateRequest 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    ordered_dashboard_ids: List[str]


class DashboardDeliveryCanvasUpdateRequest(BaseModel):
    """
    类说明：DashboardDeliveryCanvasUpdateRequest 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    draft_dashboard_id: str
    name: str = ''
    component_data: str = ''
    canvas_style_data: str = ''
    canvas_view_info: str = ''


class DashboardDeliveryPublishRequest(BaseModel):
    """
    类说明：DashboardDeliveryPublishRequest 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    publish_as_default: bool = True


class DashboardDeliverySqlPreview(BaseModel):
    """
    类说明：DashboardDeliverySqlPreview 表示仪表盘里的一类数据，通常用来和数据库表或业务对象对应。
    """
    target_tenant_id: Optional[int | str] = None
    target_tenant_public_id: str = ''
    target_datasource_id: Optional[int] = None
    sql: str = ''
