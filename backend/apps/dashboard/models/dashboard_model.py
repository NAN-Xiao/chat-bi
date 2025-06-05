from sqlmodel import SQLModel, Field
from sqlalchemy import String, Column, Text, SmallInteger, BigInteger, Integer,DateTime
from typing import Optional
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
    workspace_id: str = Field(
        default=None,
        max_length=50,
        sa_column=Column(String(50), nullable=True)
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

class DashboardResponse(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    pid: Optional[str] = None
    workspace_id: Optional[str] = None
    org_id: Optional[str] = None
    level: Optional[int] = None
    node_type: Optional[str] = None
    type: Optional[str] = None
    canvas_style_data: Optional[str] = None
    component_data: Optional[str] = None
    mobile_layout: Optional[int] = None
    status: Optional[int] = None
    self_watermark_status: Optional[int] = None
    sort: Optional[int] = None
    create_time: Optional[int] = None  # 或者用 datetime 类型
    create_by: Optional[str] = None
    update_time: Optional[int] = None  # 或者用 datetime 类型
    update_by: Optional[str] = None
    remark: Optional[str] = None
    source: Optional[str] = None
    delete_flag: Optional[int] = None
    delete_time: Optional[int] = None
    delete_by: Optional[str] = None
    version: Optional[int] = None
    content_id: Optional[str] = None
    check_version: Optional[str] = None

    class Config:
        orm_mode = True  # 允许从 ORM 对象加载

# dashboard create obj
class CreateDashboard(BaseModel):
    id: str = ''
    name: str = ''
    pid: str = ''
    workspace_id: str = ''
    org_id: str = ''
    description: str = ''
    type: str = ''
    node_type: str = ''
    canvas_style_data: str =''
    component_data: str = ''
    configuration: str = ''
    create_by: int = 0