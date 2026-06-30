"""
脚本说明：这个脚本定义系统管理用到的数据表或数据对象，便于代码和数据库对齐。
"""
from sqlalchemy import BigInteger, Column, Index, String, UniqueConstraint
from sqlmodel import Field

from common.core.models import SnowflakeBase
from common.utils.time import get_timestamp


class TenantUsageDailyModel(SnowflakeBase, table=True):
    """
    类说明：TenantUsageDailyModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_tenant_usage_daily"
    __table_args__ = (
        UniqueConstraint("tenant_id", "usage_date", "metric", name="uq_sys_tenant_usage_daily_key"),
        Index("idx_sys_tenant_usage_daily_tenant_date", "tenant_id", "usage_date"),
        Index("idx_sys_tenant_usage_daily_metric", "metric"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    usage_date: str = Field(sa_column=Column(String(10), nullable=False))
    metric: str = Field(sa_column=Column(String(128), nullable=False))
    request_count: int = Field(default=0, sa_column=Column(BigInteger(), nullable=False, server_default="0"))
    success_count: int = Field(default=0, sa_column=Column(BigInteger(), nullable=False, server_default="0"))
    failure_count: int = Field(default=0, sa_column=Column(BigInteger(), nullable=False, server_default="0"))
    total_tokens: int = Field(default=0, sa_column=Column(BigInteger(), nullable=False, server_default="0"))
    task_count: int = Field(default=0, sa_column=Column(BigInteger(), nullable=False, server_default="0"))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
