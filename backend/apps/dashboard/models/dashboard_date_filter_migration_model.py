"""看板日期筛选 V2 显式迁移的不可变审计记录。"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, Index, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class CoreDashboardDateFilterMigrationAudit(SQLModel, table=True):
    """保存每个批次对一个看板的完整迁移前后画布，供 CAS 回滚使用。"""

    __tablename__ = "core_dashboard_date_filter_migration_audit"
    __table_args__ = (
        UniqueConstraint("batch_id", "dashboard_id", name="uq_dashboard_date_filter_migration_batch_dashboard"),
        Index("idx_dashboard_date_filter_migration_tenant_dashboard", "tenant_id", "dashboard_id"),
    )

    id: str = Field(sa_column=Column(String(50), primary_key=True, nullable=False))
    batch_id: str = Field(sa_column=Column(String(100), nullable=False))
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    dashboard_id: str = Field(sa_column=Column(String(50), nullable=False))
    chart_ids: str = Field(sa_column=Column(Text, nullable=False))
    classification_json: str = Field(sa_column=Column(Text, nullable=False))
    original_canvas: str = Field(sa_column=Column(Text, nullable=False))
    original_canvas_sha256: str = Field(sa_column=Column(String(64), nullable=False))
    migrated_canvas: str = Field(sa_column=Column(Text, nullable=False))
    migrated_canvas_sha256: str = Field(sa_column=Column(String(64), nullable=False))
    verification_json: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(default="applied", sa_column=Column(String(20), nullable=False, server_default="applied"))
    created_time: int = Field(sa_column=Column(BigInteger, nullable=False))
    rolled_back_time: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
