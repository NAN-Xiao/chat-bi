"""补齐平台 SQL Skill 的 MySQL/MariaDB UNSIGNED 兼容规则。"""

from __future__ import annotations

import json

import sqlalchemy as sa

from alembic import op


revision = "155platformmysqlunsignedcompat"
down_revision = "154platformhourlyzerofill"
branch_labels = None
depends_on = None


SKILL_MARKER = "<!-- platform-foundation-skill:sql-date-grouping:v1 -->"
ZERO_FILL_SECTION_MARKER = "<!-- platform-foundation-skill:daily-zero-fill:v1 -->"
HOURLY_ZERO_FILL_SECTION_MARKER = "<!-- platform-foundation-skill:hourly-zero-fill:v1 -->"
MYSQL_UNSIGNED_SECTION_MARKER = "<!-- platform-foundation-skill:mysql-unsigned-compat:v1 -->"
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
        "when_sql_has_non_time_group_by": True,
        "required_outer_select_cross_join": True,
        "message": (
            "按日且包含时间之外的分组维度时，必须先将连续日期序列与预期维度集合 CROSS JOIN，"
            "再 LEFT JOIN 聚合结果，保证每个日期与维度组合都能返回 0。"
        ),
    },
    {
        "match": ["实时", "按小时", "每小时", "逐小时", "小时趋势", "当前小时", "当前整点"],
        "allow_when": ["总额", "总数", "合计", "单值"],
        "required_sql_patterns": [
            r"\{\{\s*dashboard_start_yyyymmdd\s*\}\}",
            r"\{\{\s*dashboard_end_yyyymmdd\s*\}\}",
            r"\b(?:hour_offsets?|hour_series|hour_spine|hour_calendar|hour_numbers|hours)\b|\b(?:generate_series|sequence)\s*\(",
            r"\bmax\s*\(",
            r"\bleft\s+(?:outer\s+)?join\b",
            r"\bcoalesce\s*\(\s*(?:[`\"\[]?\w+[`\"\]]?\s*\.\s*)?[`\"\[]?\w+[`\"\]]?\s*,\s*0(?:\.0+)?\s*\)",
        ],
        "forbidden_sql_patterns": [
            r"\b(?:curdate|current_date|now|current_timestamp|current_time|localtime|localtimestamp|getdate|getutcdate|curtime|clock_timestamp)\b",
        ],
        "message": (
            "实时按小时趋势必须从当前数据源配置的事实 time 字段取当天最大事件时间，"
            "并生成 00:00 到该事件小时的连续小时序列，"
            "再 LEFT JOIN 小时聚合结果，并使用 COALESCE(数值指标, 0) 补齐无数据小时；"
            "不得使用数据库当前日期或当前时间函数；"
            "实时总额、总数、合计或明确单值查询不适用此规则。"
        ),
    },
    {
        "match": ["实时", "按小时", "每小时", "逐小时", "小时趋势", "当前小时", "当前整点"],
        "allow_when": ["总额", "总数", "合计", "单值"],
        "when_sql_has_non_time_group_by": True,
        "required_outer_select_cross_join": True,
        "message": (
            "实时按小时且包含时间之外的分组维度时，必须先将连续小时序列与预期维度集合 CROSS JOIN，"
            "再 LEFT JOIN 小时聚合结果，保证每个小时与维度组合都能返回 0。"
        ),
    },
]

ZERO_FILL_SECTION = f"""{ZERO_FILL_SECTION_MARKER}
{HOURLY_ZERO_FILL_SECTION_MARKER}
{MYSQL_UNSIGNED_SECTION_MARKER}
<!-- data-skill-sql-validation: {json.dumps(ZERO_FILL_VALIDATION_RULES, ensure_ascii=False, separators=(',', ':'))} -->
## 按日和实时按小时结果的连续序列与补零

### 按日结果

生成每日、每天、按日或逐日时序 SQL 时，以下结构是强制约束：

1. 先生成从 `{{{{dashboard_start_yyyymmdd}}}}` 到 `{{{{dashboard_end_yyyymmdd}}}}` 的连续日期序列，开始日期和结束日期都必须包含。
2. 业务事实数据必须先按最终结果粒度单独聚合，再从日期序列 `LEFT JOIN` 聚合结果。
3. 结果粒度包含时间字段之外的任意分组维度时，先取得当前权限和查询语义下的预期维度集合，再与日期序列 `CROSS JOIN`，之后按日期和维度 `LEFT JOIN` 聚合结果。渠道、国家、平台、服务器、地区等都只是维度示例，不是固定字段清单。
4. 无匹配事实数据的数值指标必须使用 `COALESCE(指标, 0)` 返回 `0`；只写 `COALESCE` 而不生成缺失日期行不算补零。

### 实时按小时结果

1. 用户要求实时、按小时、每小时、逐小时或小时趋势时，先在 `{{{{dashboard_start_yyyymmdd}}}}` 到 `{{{{dashboard_end_yyyymmdd}}}}` 的事实范围内，对当前数据源 Schema 配置的事实 `time` 字段取 `MAX`，再生成当天 `00:00` 到该最大事件时间所在小时的连续小时序列，并包含该小时。不得使用 `CURRENT_DATE`、`CURRENT_TIMESTAMP`、`NOW` 或其他数据库当前日期/时间函数。
2. 小时字段、实时表、时区和事实过滤条件必须来自当前数据源 Schema 与 Data Skill，不得套用其他数据源的字段名或时区。
3. 事实数据先按小时和最终结果粒度聚合；小时序列上界与指标聚合必须使用同一事实日期范围，再从连续小时序列 `LEFT JOIN`，并用 `COALESCE(指标, 0)` 补齐没有数据的小时。
4. 如果结果粒度包含时间字段之外的任意分组维度，先将连续小时序列与预期维度集合 `CROSS JOIN`，再 `LEFT JOIN` 小时聚合结果。
5. “实时总额”“实时总数”“实时合计”或明确要求单值的查询不强制生成小时序列；累计趋势仍必须返回连续小时序列。

### MySQL/MariaDB 方言兼容

1. 当前 MySQL/MariaDB 兼容数据源不支持 `CAST(... AS UNSIGNED)` 或 `AS UNSIGNED`，需要把 YYYYMMDD 数字或其他数值转换写成当前方言已验证的 `SIGNED` 或 `DECIMAL` 形式。
2. 数据源通过 MySQL 协议接入并不代表底层代理支持全部 MySQL 类型，不能因为驱动名就假定 `UNSIGNED` 可用。
3. JSON 数值字段如果要参与聚合或比较，优先使用 `DECIMAL(...)`，不要强制转成 `UNSIGNED`。
4. 补零、分组和日期边界规则优先于数值类型优化，不要为了转换方便引入方言不兼容类型。

事实表筛选条件必须保留在事实聚合 CTE 或 `LEFT JOIN ... ON` 中，不能在最终 `WHERE` 中过滤右表并破坏补零结果。
""".strip()


def upgrade() -> None:
    result = op.get_bind().execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = CASE
                    WHEN position(:unsigned_marker in COALESCE(prompt, '')) = 0
                        THEN rtrim(prompt) || E'\\n\\n' || :section
                    ELSE regexp_replace(
                        prompt,
                        E'\\n*<!-- platform-foundation-skill:mysql-unsigned-compat:v1 -->[\\s\\S]*$',
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
            "unsigned_marker": MYSQL_UNSIGNED_SECTION_MARKER,
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
                    E'\\n*<!-- platform-foundation-skill:mysql-unsigned-compat:v1 -->[\\s\\S]*$',
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
        {"section_marker": MYSQL_UNSIGNED_SECTION_MARKER, "name": SKILL_NAME},
    )
