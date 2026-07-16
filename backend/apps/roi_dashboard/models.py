"""ROI 专用看板数据模型。"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from common.core.models import SnowflakeBase


class CoreRoiWorkspaceConfig(SnowflakeBase, table=True):
    """工作空间的 ROI 数据源配置。"""

    __tablename__ = "core_roi_workspace_config"
    __table_args__ = (
        Index(
            "uq_core_roi_workspace_config_active_tenant",
            "tenant_id",
            unique=True,
            postgresql_where=text("deleted = false"),
        ),
        Index("idx_core_roi_workspace_config_tenant_id", "tenant_id"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    datasource_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    version: int = Field(
        default=1, sa_column=Column(Integer(), nullable=False, server_default="1")
    )
    create_by: int | None = Field(
        default=None, sa_column=Column(BigInteger(), nullable=True)
    )
    update_by: int | None = Field(
        default=None, sa_column=Column(BigInteger(), nullable=True)
    )
    create_time: int = Field(sa_column=Column(BigInteger(), nullable=False))
    update_time: int = Field(sa_column=Column(BigInteger(), nullable=False))
    deleted: bool = Field(
        default=False,
        sa_column=Column(Boolean(), nullable=False, server_default="false"),
    )


class CoreRoiDashboard(SnowflakeBase, table=True):
    """ROI 看板。"""

    __tablename__ = "core_roi_dashboard"
    __table_args__ = (
        Index("idx_core_roi_dashboard_tenant_id", "tenant_id"),
        Index(
            "idx_core_roi_dashboard_tenant_status_sort", "tenant_id", "status", "sort"
        ),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    name: str = Field(sa_column=Column(String(64), nullable=False))
    sort: int = Field(
        default=0, sa_column=Column(Integer(), nullable=False, server_default="0")
    )
    status: int = Field(
        default=1, sa_column=Column(Integer(), nullable=False, server_default="1")
    )
    version: int = Field(
        default=1, sa_column=Column(Integer(), nullable=False, server_default="1")
    )
    create_by: int | None = Field(
        default=None, sa_column=Column(BigInteger(), nullable=True)
    )
    update_by: int | None = Field(
        default=None, sa_column=Column(BigInteger(), nullable=True)
    )
    create_time: int = Field(sa_column=Column(BigInteger(), nullable=False))
    update_time: int = Field(sa_column=Column(BigInteger(), nullable=False))
    deleted: bool = Field(
        default=False,
        sa_column=Column(Boolean(), nullable=False, server_default="false"),
    )


class CoreRoiDashboardChart(SnowflakeBase, table=True):
    """ROI 看板图表。"""

    __tablename__ = "core_roi_dashboard_chart"
    __table_args__ = (
        CheckConstraint(
            "layout_span IN ('full','half','third')",
            name="ck_core_roi_chart_layout_span",
        ),
        Index("idx_core_roi_dashboard_chart_tenant_id", "tenant_id"),
        Index(
            "idx_core_roi_dashboard_chart_tenant_dashboard_status_sort",
            "tenant_id",
            "roi_dashboard_id",
            "status",
            "sort",
        ),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    roi_dashboard_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    title: str = Field(sa_column=Column(String(255), nullable=False))
    sql: str = Field(sa_column=Column(Text(), nullable=False))
    chart_type: str = Field(sa_column=Column(String(64), nullable=False))
    chart_config: dict = Field(sa_column=Column(JSONB, nullable=False))
    layout_span: str = Field(
        default="full",
        sa_column=Column(String(16), nullable=False, server_default="full"),
    )
    sort: int = Field(
        default=0, sa_column=Column(Integer(), nullable=False, server_default="0")
    )
    status: int = Field(
        default=1, sa_column=Column(Integer(), nullable=False, server_default="1")
    )
    version: int = Field(
        default=1, sa_column=Column(Integer(), nullable=False, server_default="1")
    )
    create_by: int | None = Field(
        default=None, sa_column=Column(BigInteger(), nullable=True)
    )
    update_by: int | None = Field(
        default=None, sa_column=Column(BigInteger(), nullable=True)
    )
    create_time: int = Field(sa_column=Column(BigInteger(), nullable=False))
    update_time: int = Field(sa_column=Column(BigInteger(), nullable=False))
    deleted: bool = Field(
        default=False,
        sa_column=Column(Boolean(), nullable=False, server_default="false"),
    )
