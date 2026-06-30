"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
import json
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '547df942eb90'
down_revision = 'b40e41c67db3'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###

    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.add_column('sys_assistant', sa.Column('oid', sa.BigInteger(), nullable=True))
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE sys_assistant SET oid = 1 WHERE oid IS NULL"))
    rows = conn.execute(
        sa.text("SELECT id, configuration FROM sys_assistant WHERE type = 0 AND configuration IS NOT NULL")
    )
    for row in rows:
        try:
            config = json.loads(row.configuration) if isinstance(row.configuration, str) else row.configuration
            oid_value = config.get('oid', 1) if isinstance(config, dict) else 1
            if oid_value != 1:
                if not isinstance(oid_value, int):
                    oid_value = int(oid_value)
                conn.execute(
                    sa.text("UPDATE sys_assistant SET oid = :oid WHERE id = :id"),
                    {"oid": oid_value, "id": row.id}
                )
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_column('sys_assistant', 'oid')
    # ### Alembic 命令结束 ###
