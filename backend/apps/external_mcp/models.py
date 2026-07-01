"""
脚本说明：这个脚本定义第三方 MCP 外部数据源接入配置相关的数据表。
"""
from sqlalchemy import BigInteger, Boolean, Column, Index, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from common.core.models import SnowflakeBase
from common.utils.time import get_timestamp


class CoreExternalMcpServer(SnowflakeBase, table=True):
    """
    类说明：CoreExternalMcpServer 表示一个第三方 MCP 数据源配置。
    """
    __tablename__ = "core_external_mcp_server"
    __table_args__ = (
        UniqueConstraint("name", name="uq_core_external_mcp_server_name"),
        Index("idx_core_external_mcp_server_status", "status"),
    )

    name: str = Field(sa_column=Column(String(128), nullable=False))
    endpoint: str = Field(sa_column=Column(Text(), nullable=False))
    description: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    auth_type: str = Field(default="bearer", sa_column=Column(String(32), nullable=False, server_default="bearer"))
    auth_header_name: str = Field(
        default="Authorization",
        sa_column=Column(String(128), nullable=False, server_default="Authorization"),
    )
    auth_token: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    server_name: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    server_version: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    status: int = Field(default=1, sa_column=Column(BigInteger(), nullable=False, server_default="1"))
    credential_configured: bool = Field(
        default=False,
        sa_column=Column(Boolean(), nullable=False, server_default="false"),
    )
    create_by: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    update_by: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)


class CoreExternalMcpTenantBinding(SnowflakeBase, table=True):
    """
    类说明：CoreExternalMcpTenantBinding 表示工作空间与第三方 MCP 数据源的绑定关系。
    """
    __tablename__ = "core_external_mcp_tenant_binding"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_core_external_mcp_tenant_binding_tenant"),
        UniqueConstraint("tenant_id", "external_mcp_server_id", name="uq_core_external_mcp_tenant_binding_pair"),
        Index("idx_core_external_mcp_tenant_binding_server", "external_mcp_server_id"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    external_mcp_server_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    create_by: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
