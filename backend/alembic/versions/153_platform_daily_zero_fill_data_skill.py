"""强化平台按日时序 SQL 的连续日期与补零约束。"""

from __future__ import annotations

import json

import sqlalchemy as sa

from alembic import op


revision = "153platformdailyzerofill"
down_revision = "152platformsqlaliasquote"
branch_labels = None
depends_on = None


SKILL_MARKER = "<!-- platform-foundation-skill:sql-date-grouping:v1 -->"
ZERO_FILL_SECTION_MARKER = "<!-- platform-foundation-skill:daily-zero-fill:v1 -->"
SKILL_NAME = "平台通用 SQL 日期与分组规范"

ZERO_FILL_VALIDATION_RULES = [
    {
        "match": ["每日", "每天", "按日", "逐日"],
        "required_sql_patterns": [
            r"\{\{\s*dashboard_start_yyyymmdd\s*\}\}",
            r"\{\{\s*dashboard_end_yyyymmdd\s*\}\}",
            r"(?:\b(?:date_add|date_sub|generate_series|dateadd|sequence)\s*\(|\b(?:calendar|date_spine|date_series)\b)",
            r"\bleft\s+(?:outer\s+)?join\b",
            r"\bcoalesce\s*\(\s*(?:[`\"\[]?\w+[`\"\]]?\s*\.\s*)?[`\"\[]?\w+[`\"\]]?\s*,\s*0(?:\.0+)?\s*\)",
        ],
        "message": (
            "按日查询必须先生成包含起止日期的连续日期序列，再 LEFT JOIN 聚合结果，"
            "并使用 COALESCE(数值指标, 0) 补齐无数据日期；该结构不能省略或简化。"
        ),
    },
    {
        "match": ["每日", "每天", "按日", "逐日"],
        "when_sql_patterns": [r"\bgroup\s+by\b[^;]*,"],
        "required_sql_patterns": [r"\bcross\s+join\b"],
        "message": (
            "按日且包含分组维度的查询，必须先将连续日期序列与预期维度集合 CROSS JOIN，"
            "再 LEFT JOIN 聚合结果，保证每个日期与维度组合都能返回 0。"
        ),
    },
]

ZERO_FILL_SECTION = f"""{ZERO_FILL_SECTION_MARKER}
<!-- data-skill-sql-validation: {json.dumps(ZERO_FILL_VALIDATION_RULES, ensure_ascii=False, separators=(',', ':'))} -->
## 按日结果的连续日期与补零

生成每日、每天、按日或逐日时序 SQL 时，以下结构是强制约束，不得为了简化 SQL 而省略：

1. 先生成从 `{{{{dashboard_start_yyyymmdd}}}}` 到 `{{{{dashboard_end_yyyymmdd}}}}` 的连续日期序列，开始日期和结束日期都必须包含。
2. 业务事实数据必须先按最终结果粒度单独聚合，再从日期序列 `LEFT JOIN` 聚合结果。
3. 查询包含渠道、国家、平台等分组维度时，先取得当前权限和当前查询语义下的预期维度集合，再与日期序列 `CROSS JOIN`，之后按日期和维度 `LEFT JOIN` 聚合结果。
4. 无匹配事实数据的数值指标必须使用 `COALESCE(指标, 0)` 返回 `0`；只写 `COALESCE` 而不生成缺失日期行不算补零。
5. 事实表筛选条件保留在事实聚合 CTE 或 `LEFT JOIN ... ON` 中，不能在最终 `WHERE` 中过滤右表并破坏补零结果。
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
                        E'\\n*<!-- platform-foundation-skill:daily-zero-fill:v1 -->[\\s\\S]*$',
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
            "section_marker": ZERO_FILL_SECTION_MARKER,
            "section": ZERO_FILL_SECTION,
            "name": SKILL_NAME,
            "skill_marker": SKILL_MARKER,
        },
    )
    if result.rowcount != 1:
        raise RuntimeError(f"平台 SQL Skill 更新数量异常: {result.rowcount}")


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = regexp_replace(
                    prompt,
                    E'\\n*<!-- platform-foundation-skill:daily-zero-fill:v1 -->[\\s\\S]*$',
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
        {"section_marker": ZERO_FILL_SECTION_MARKER, "name": SKILL_NAME},
    )
