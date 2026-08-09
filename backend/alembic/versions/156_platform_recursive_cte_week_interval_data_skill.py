"""补齐平台递归 CTE 列清单与动态周间隔方言约束。"""

from __future__ import annotations

import json

import sqlalchemy as sa

from alembic import op


revision = "156platformrecursivecteweek"
down_revision = "155platformmysqlunsignedcompat"
branch_labels = None
depends_on = None


SKILL_MARKER = "<!-- platform-foundation-skill:sql-date-grouping:v1 -->"
SECTION_MARKER = "<!-- platform-foundation-skill:recursive-cte-week-compat:v1 -->"
SKILL_NAME = "平台通用 SQL 日期与分组规范"

VALIDATION_RULES = [
    {
        "match": ["按日", "按天", "每日", "每周", "按周", "每小时", "按小时", "实时"],
        "forbidden_sql_patterns": [
            r"\binterval\s+(?!\d+(?:\.\d+)?\b)(?:\([^)]*\)|[^\s,()]+(?:\s*\*\s*[^\s,()]+)?)\s+week\b"
        ],
        "message": (
            "AnalyticDB 不支持 INTERVAL 后使用列或表达式的 WEEK 单位；"
            "请使用固定周边界或将周偏移转换为已验证的 DAY 偏移。"
        ),
    },
]

SECTION = f"""{SECTION_MARKER}
<!-- data-skill-sql-validation: {json.dumps(VALIDATION_RULES, ensure_ascii=False, separators=(',', ':'))} -->
## 递归 CTE 与周序列方言约束

1. 当前 AnalyticDB/MySQL 兼容数据源优先使用非递归日期、小时或数字序列。
2. 如果确需使用 `WITH RECURSIVE`，同一个 `WITH` 中每个 CTE 都必须写完整列清单，例如 `metrics(metric_date, metric_value) AS (...)`，不能只给自引用 CTE 声明列名。
3. 不得生成 `INTERVAL <列或表达式> WEEK`。周偏移应使用固定周边界，或使用 `INTERVAL (week_offset * 7) DAY`。
4. 日期/维度补零仍必须保留时间序列与维度集合的完整键骨架，再 `LEFT JOIN` 聚合结果并对适用的数值指标使用 `COALESCE(..., 0)`。
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
                        E'\\n*<!-- platform-foundation-skill:recursive-cte-week-compat:v1 -->[\\s\\S]*$',
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
        raise RuntimeError(f"平台递归 CTE/周间隔 Skill 更新数量异常: {result.rowcount}")


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = regexp_replace(
                    prompt,
                    E'\\n*<!-- platform-foundation-skill:recursive-cte-week-compat:v1 -->[\\s\\S]*$',
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
