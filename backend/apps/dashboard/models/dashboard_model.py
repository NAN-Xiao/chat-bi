from sqlmodel import SQLModel, Field
from sqlalchemy import String, Column, Text, SmallInteger, BigInteger, Integer, DateTime
from typing import Optional, List, Literal
from pydantic import BaseModel

class CoreDashboard(SQLModel, table=True):
    __tablename__ = "core_dashboard"
    id: str = Field(
        sa_column=Column(String(50), nullable=False, primary_key=True)
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
    id: str = Field(
        sa_column=Column(String(50), nullable=False, primary_key=True)
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
    name: Optional[str] = None
    pid: Optional[str] = None
    datasource: Optional[int] = None
    node_type: Optional[str] = None
    leaf: Optional[bool] = False
    type: Optional[str] = None
    create_time: Optional[int] = None
    update_time: Optional[int] = None
    can_edit: Optional[bool] = False
    can_share: Optional[bool] = False
    is_shared: Optional[bool] = False
    share_id: Optional[str] = None
    children: List['DashboardBaseResponse'] = []


class DashboardShareListResponse(BaseModel):
    id: Optional[str] = None
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
    name: str = ''
    pid: str = ''
    datasource: Optional[int] = None
    org_id: str = ''
    type: str = ''
    node_type: str = ''
    level: int = 0
    create_by: int = 0

class QueryDashboard(BaseDashboard):
    opt: str = ''
    refresh_data: bool = False


# dashboard create obj
class CreateDashboard(QueryDashboard):
    canvas_style_data: str =''
    component_data: str = ''
    canvas_view_info: str = ''
    description: str = ''


class DashboardSqlPreview(BaseModel):
    datasource: int
    sql: str = ''


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
