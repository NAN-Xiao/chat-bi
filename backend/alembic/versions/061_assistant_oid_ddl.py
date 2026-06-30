"""迁移脚本：061_assistant_oid_ddl

迁移版本 ID： 547df942eb90
上一版本： b40e41c67db3
创建时间： 2026-01-09 15:02:19.891766
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
    是什么：upgrade 是 backend/alembic/versions/061_assistant_oid_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/061_assistant_oid_ddl.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('sys_assistant', 'oid')
    # ### Alembic 命令结束 ###
