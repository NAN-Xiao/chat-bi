"""
脚本说明：这个脚本新增第三方 MCP 外部数据源配置、工作空间绑定和 MCP 看板归属字段。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b7c8d9e0f1a2"
down_revision = "f3a9d2c7b6e1"
branch_labels = None
depends_on = None

CHATMON_EXTERNAL_MCP_ID = 7485000000000000001
FLAM_TENANT_ID = 7477202383789887488
CHATMON_DASHBOARD_ID = "e7305389ebd24f94b12235519dd0d859"
XIAONAN_USER_ID = 7471612174524223488


def _bind():
    """
    是什么：_bind 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    """
    return op.get_bind()


def _inspector():
    """
    是什么：_inspector 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    """
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 检查表是否存在。
    """
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 检查列是否存在。
    """
    if not _has_table(table_name):
        return False
    return column_name in {column["name"] for column in _inspector().get_columns(table_name)}


def _has_index(table_name: str, index_name: str) -> bool:
    """
    是什么：_has_index 检查索引是否存在。
    """
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _now_ms() -> int:
    """
    是什么：_now_ms 生成迁移写入用的毫秒时间戳。
    """
    row = _bind().execute(sa.text("SELECT CAST(EXTRACT(EPOCH FROM CURRENT_TIMESTAMP) * 1000 AS BIGINT)")).scalar()
    return int(row or 0)


def upgrade() -> None:
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    """
    if not _has_table("core_external_mcp_server"):
        op.create_table(
            "core_external_mcp_server",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("endpoint", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("auth_type", sa.String(length=32), nullable=False, server_default="bearer"),
            sa.Column("auth_header_name", sa.String(length=128), nullable=False, server_default="Authorization"),
            sa.Column("auth_token", sa.Text(), nullable=True),
            sa.Column("server_name", sa.String(length=128), nullable=True),
            sa.Column("server_version", sa.String(length=64), nullable=True),
            sa.Column("status", sa.BigInteger(), nullable=False, server_default="1"),
            sa.Column("credential_configured", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("create_by", sa.BigInteger(), nullable=True),
            sa.Column("update_by", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.Column("update_time", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name", name="uq_core_external_mcp_server_name"),
        )
    if not _has_index("core_external_mcp_server", "idx_core_external_mcp_server_status"):
        op.create_index("idx_core_external_mcp_server_status", "core_external_mcp_server", ["status"])

    if not _has_table("core_external_mcp_tenant_binding"):
        op.create_table(
            "core_external_mcp_tenant_binding",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("external_mcp_server_id", sa.BigInteger(), nullable=False),
            sa.Column("create_by", sa.BigInteger(), nullable=True),
            sa.Column("create_time", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", name="uq_core_external_mcp_tenant_binding_tenant"),
            sa.UniqueConstraint(
                "tenant_id",
                "external_mcp_server_id",
                name="uq_core_external_mcp_tenant_binding_pair",
            ),
        )
    if not _has_index("core_external_mcp_tenant_binding", "idx_core_external_mcp_tenant_binding_server"):
        op.create_index(
            "idx_core_external_mcp_tenant_binding_server",
            "core_external_mcp_tenant_binding",
            ["external_mcp_server_id"],
        )

    if _has_table("core_dashboard") and not _has_column("core_dashboard", "external_mcp_server_id"):
        op.add_column("core_dashboard", sa.Column("external_mcp_server_id", sa.BigInteger(), nullable=True))
    if _has_table("core_dashboard") and not _has_index("core_dashboard", "idx_core_dashboard_external_mcp"):
        op.create_index("idx_core_dashboard_external_mcp", "core_dashboard", ["external_mcp_server_id"])

    now = _now_ms()
    _bind().execute(
        sa.text(
            """
            INSERT INTO core_external_mcp_server (
                id,
                name,
                endpoint,
                description,
                auth_type,
                auth_header_name,
                auth_token,
                server_name,
                server_version,
                status,
                credential_configured,
                create_by,
                update_by,
                create_time,
                update_time
            )
            VALUES (
                :id,
                :name,
                :endpoint,
                :description,
                'bearer',
                'Authorization',
                NULL,
                :server_name,
                :server_version,
                1,
                FALSE,
                :user_id,
                :user_id,
                :now,
                :now
            )
            ON CONFLICT (name) DO UPDATE SET
                endpoint = EXCLUDED.endpoint,
                description = EXCLUDED.description,
                server_name = EXCLUDED.server_name,
                server_version = EXCLUDED.server_version,
                status = EXCLUDED.status,
                update_by = EXCLUDED.update_by,
                update_time = EXCLUDED.update_time
            """
        ),
        {
            "id": CHATMON_EXTERNAL_MCP_ID,
            "name": "ChatMon 告警 MCP",
            "endpoint": "https://chatmon-test.elex-tech.com/mcp",
            "description": "第三方 ChatMon 告警 MCP 外部数据源",
            "server_name": "game-chat-alerts",
            "server_version": "1.28.1",
            "user_id": XIAONAN_USER_ID,
            "now": now,
        },
    )

    _bind().execute(
        sa.text(
            """
            INSERT INTO core_external_mcp_tenant_binding (
                id,
                tenant_id,
                external_mcp_server_id,
                create_by,
                create_time
            )
            VALUES (
                :id,
                :tenant_id,
                :external_mcp_server_id,
                :user_id,
                :now
            )
            ON CONFLICT (tenant_id) DO UPDATE SET
                external_mcp_server_id = EXCLUDED.external_mcp_server_id,
                create_by = EXCLUDED.create_by,
                create_time = EXCLUDED.create_time
            """
        ),
        {
            "id": 7485000000000000002,
            "tenant_id": FLAM_TENANT_ID,
            "external_mcp_server_id": CHATMON_EXTERNAL_MCP_ID,
            "user_id": XIAONAN_USER_ID,
            "now": now,
        },
    )

    if _has_table("core_dashboard") and _has_column("core_dashboard", "external_mcp_server_id"):
        _bind().execute(
            sa.text(
                """
                UPDATE core_dashboard
                SET
                    tenant_id = :tenant_id,
                    datasource = NULL,
                    external_mcp_server_id = :external_mcp_server_id,
                    source = 'external_mcp',
                    update_by = :user_id,
                    update_time = CAST(EXTRACT(EPOCH FROM CURRENT_TIMESTAMP) AS BIGINT)
                WHERE id = :dashboard_id
                """
            ),
            {
                "tenant_id": FLAM_TENANT_ID,
                "external_mcp_server_id": CHATMON_EXTERNAL_MCP_ID,
                "user_id": str(XIAONAN_USER_ID),
                "dashboard_id": CHATMON_DASHBOARD_ID,
            },
        )


def downgrade() -> None:
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    """
    if _has_table("core_dashboard") and _has_index("core_dashboard", "idx_core_dashboard_external_mcp"):
        op.drop_index("idx_core_dashboard_external_mcp", table_name="core_dashboard")
    if _has_table("core_dashboard") and _has_column("core_dashboard", "external_mcp_server_id"):
        op.drop_column("core_dashboard", "external_mcp_server_id")
    if _has_table("core_external_mcp_tenant_binding"):
        if _has_index("core_external_mcp_tenant_binding", "idx_core_external_mcp_tenant_binding_server"):
            op.drop_index(
                "idx_core_external_mcp_tenant_binding_server",
                table_name="core_external_mcp_tenant_binding",
            )
        op.drop_table("core_external_mcp_tenant_binding")
    if _has_table("core_external_mcp_server"):
        if _has_index("core_external_mcp_server", "idx_core_external_mcp_server_status"):
            op.drop_index("idx_core_external_mcp_server_status", table_name="core_external_mcp_server")
        op.drop_table("core_external_mcp_server")
