"""补齐平台时间骨架与事实表聚合性能约束。"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "157platformtimescaffoldperf"
down_revision = "156platformrecursivecteweek"
branch_labels = None
depends_on = None


SKILL_MARKER = "<!-- platform-foundation-skill:sql-date-grouping:v1 -->"
SECTION_MARKER = "<!-- platform-foundation-skill:time-scaffold-performance:v1 -->"
SKILL_NAME = "平台通用 SQL 日期与分组规范"

SECTION = f"""{SECTION_MARKER}
## 时间骨架与事实表性能约束

1. 事实明细表必须先在独立 CTE 或子查询中使用明确的日期/分区范围过滤，并按目标时间粒度完成聚合。
2. 不得把物理事实表直接按日期、小时或周范围 JOIN 到时间骨架；应将已聚合的结果再 `LEFT JOIN` 到日期、小时或周骨架。
3. 周序列、日期序列或小时序列的骨架只负责生成完整键集合，不得承担事实明细扫描和重复范围匹配。
""".strip()


def upgrade() -> None:
    result = op.get_bind().execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = CASE
                    WHEN position(:section_marker in COALESCE(prompt, '')) = 0
                        THEN rtrim(prompt) || E'\\n\\n' || :section
                    ELSE regexp_replace(
                        prompt,
                        E'\\n*<!-- platform-foundation-skill:time-scaffold-performance:v1 -->[\\s\\S]*$',
                        E'\\n\\n' || :section
                    )
                END,
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
            "section_marker": SECTION_MARKER,
            "section": SECTION,
            "name": SKILL_NAME,
            "skill_marker": SKILL_MARKER,
        },
    )
    if result.rowcount != 1:
        raise RuntimeError(f"平台时间骨架性能 Skill 更新数量异常: {result.rowcount}")


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = regexp_replace(
                    prompt,
                    E'\\n*<!-- platform-foundation-skill:time-scaffold-performance:v1 -->[\\s\\S]*$',
                    ''
                ),
                embedding = NULL,
                embedding_signature = NULL
            WHERE tenant_id = 1
              AND type = 'DATA_SKILL'
              AND name = :name
              AND position(:section_marker in COALESCE(prompt, '')) > 0
            """
        ),
        {"section_marker": SECTION_MARKER, "name": SKILL_NAME},
    )
