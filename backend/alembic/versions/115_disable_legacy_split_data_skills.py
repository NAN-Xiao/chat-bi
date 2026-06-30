"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a8d7e6c5b4a3"
down_revision = "f6b8d0e2a4c5"
branch_labels = None
depends_on = None


LEGACY_MARKERS = (
    "<!-- data-skill-source:terminology:",
    "<!-- data-skill-source:data-training:",
    "<!-- data-skill-source:custom-prompt-generate-sql:",
    "<!-- data-skill-source:legacy-semantic:",
    "<!-- data-skill-source:semantic-theme:saas:",
    "<!-- legacy-data-training:",
    "<!-- legacy-terminology:",
    "<!-- legacy-sql-prompt:",
)


def upgrade() -> None:
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    conn = op.get_bind()
    conditions = " OR ".join(f"prompt LIKE :marker_{index}" for index, _marker in enumerate(LEGACY_MARKERS))
    params = {f"marker_{index}": f"%{marker}%" for index, marker in enumerate(LEGACY_MARKERS)}
    conn.execute(
        sa.text(
            f"""
            UPDATE custom_prompt
            SET active = false
            WHERE type = 'DATA_SKILL'
              AND COALESCE(active, false) = true
              AND ({conditions})
            """
        ),
        params,
    )


def downgrade() -> None:
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    return None
