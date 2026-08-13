"""收窄平台实时按小时规则的意图匹配范围。"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "158platformrealtimehourlyscope"
down_revision = "157platformtimescaffoldperf"
branch_labels = None
depends_on = None


SKILL_NAME = "平台通用 SQL 日期与分组规范"
SKILL_MARKER = "<!-- platform-foundation-skill:hourly-zero-fill:v1 -->"
OLD_HOURLY_MATCH = '"match":["实时","按小时","每小时","逐小时","小时趋势","当前小时","当前整点"]'
NEW_HOURLY_MATCH = '"match":["按小时","每小时","逐小时","小时趋势","实时趋势","当前小时","当前整点"]'
OLD_HOURLY_GUIDANCE = "用户要求实时、按小时、每小时、逐小时或小时趋势时"
NEW_HOURLY_GUIDANCE = "用户明确要求按小时、每小时、逐小时、小时趋势、实时趋势、当前小时或当前整点时"


def upgrade() -> None:
    result = op.get_bind().execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = replace(
                    replace(prompt, :old_match, :new_match),
                    :old_guidance,
                    :new_guidance
                ),
                embedding = NULL,
                embedding_signature = NULL
            WHERE tenant_id = 1
              AND type = 'DATA_SKILL'
              AND name = :name
              AND visibility_scope = 'PLATFORM_PUBLIC'
              AND COALESCE(specific_ds, FALSE) = FALSE
              AND position(:skill_marker in COALESCE(prompt, '')) > 0
            """
        ),
        {
            "old_match": OLD_HOURLY_MATCH,
            "new_match": NEW_HOURLY_MATCH,
            "old_guidance": OLD_HOURLY_GUIDANCE,
            "new_guidance": NEW_HOURLY_GUIDANCE,
            "name": SKILL_NAME,
            "skill_marker": SKILL_MARKER,
        },
    )
    if result.rowcount != 1:
        raise RuntimeError(f"平台实时按小时 Skill 更新数量异常: {result.rowcount}")


def downgrade() -> None:
    result = op.get_bind().execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = replace(
                    replace(prompt, :new_match, :old_match),
                    :new_guidance,
                    :old_guidance
                ),
                embedding = NULL,
                embedding_signature = NULL
            WHERE tenant_id = 1
              AND type = 'DATA_SKILL'
              AND name = :name
              AND visibility_scope = 'PLATFORM_PUBLIC'
              AND COALESCE(specific_ds, FALSE) = FALSE
              AND position(:skill_marker in COALESCE(prompt, '')) > 0
            """
        ),
        {
            "new_match": NEW_HOURLY_MATCH,
            "old_match": OLD_HOURLY_MATCH,
            "new_guidance": NEW_HOURLY_GUIDANCE,
            "old_guidance": OLD_HOURLY_GUIDANCE,
            "name": SKILL_NAME,
            "skill_marker": SKILL_MARKER,
        },
    )
    if result.rowcount != 1:
        raise RuntimeError(f"平台实时按小时 Skill 回滚数量异常: {result.rowcount}")
