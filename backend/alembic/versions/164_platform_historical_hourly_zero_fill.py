"""区分历史完整小时与当天实时小时补零规则。"""

from __future__ import annotations

import json

import sqlalchemy as sa

from alembic import op


revision = "164platformhistoricalhourly"
down_revision = "163platformmetricdatecontract"
branch_labels = None
depends_on = None


SKILL_NAME = "平台通用 SQL 日期与分组规范"
SKILL_MARKER = "<!-- platform-foundation-skill:sql-date-grouping:v1 -->"
SECTION_START_MARKER = "<!-- platform-foundation-skill:daily-zero-fill:v1 -->"
SECTION_END_MARKER = "<!-- platform-foundation-skill:recursive-cte-week-compat:v1 -->"

HOURLY_MATCH = ["按小时", "每小时", "逐小时", "小时趋势", "实时趋势", "当前小时", "当前整点"]
SCALAR_HOURLY_EXEMPTIONS = ["实时总额", "实时总数", "实时合计", "单值"]
HOURLY_SCAFFOLD_PATTERN = (
    r"\b(?:hour_offsets?|hour_series|hour_spine|hour_calendar|hour_numbers|hours)\b"
    r"|\b(?:generate_series|sequence)\s*\("
)
HOUR_MAX_CLIP_PATTERN = (
    r"\bwhere\b[\s\S]{0,500}(?:\b\w+\s*\.\s*)?\b\w*hour\w*\b\s*<=\s*"
    r"(?:\b\w+\s*\.\s*)?\b\w*(?:max|latest|current)\w*\b"
)
COALESCE_ZERO_PATTERN = (
    r"\bcoalesce\s*\(\s*(?:[`\"\[]?\w+[`\"\]]?\s*\.\s*)?"
    r"[`\"\[]?\w+[`\"\]]?\s*,\s*0(?:\.0+)?\s*\)"
)

DAILY_RULES = [
    {
        "match": ["每日", "每天", "按日", "逐日"],
        "required_sql_patterns": [
            r"\{\{\s*dashboard_start_yyyymmdd\s*\}\}",
            r"\{\{\s*dashboard_end_yyyymmdd\s*\}\}",
            r"(?:\b(?:date_add|date_sub|generate_series|dateadd|sequence)\s*\(|\b(?:calendar|date_spine|date_series)\b)",
            r"\bleft\s+(?:outer\s+)?join\b",
            COALESCE_ZERO_PATTERN,
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
]

CURRENT_DAY_HOURLY_RULES = [
    {
        "match": HOURLY_MATCH,
        "allow_when": SCALAR_HOURLY_EXEMPTIONS,
        "when_question_date_scopes": ["current_day"],
        "required_scoped_max_time": True,
        "required_sql_patterns": [
            r"\{\{\s*dashboard_start_yyyymmdd\s*\}\}",
            r"\{\{\s*dashboard_end_yyyymmdd\s*\}\}",
            HOURLY_SCAFFOLD_PATTERN,
            r"\bmax\s*\(",
            r"\bleft\s+(?:outer\s+)?join\b",
            COALESCE_ZERO_PATTERN,
        ],
        "forbidden_sql_patterns": [
            r"\b(?:curdate|current_date|now|current_timestamp|current_time|localtime|localtimestamp|getdate|getutcdate|curtime|clock_timestamp)\b",
        ],
        "message": (
            "当天实时按小时趋势必须在本次日期、事件、产品和权限过滤范围内取事实 time 的最大值，"
            "并生成 00:00 到该事件小时的连续小时序列；不得全表取 MAX(time)，也不得使用数据库当前时间。"
        ),
    },
    {
        "match": HOURLY_MATCH,
        "allow_when": SCALAR_HOURLY_EXEMPTIONS,
        "when_question_date_scopes": ["current_day"],
        "when_sql_has_non_time_group_by": True,
        "required_outer_select_cross_join": True,
        "message": (
            "当天实时按小时且包含时间之外的分组维度时，必须先将连续小时序列与预期维度集合 CROSS JOIN，"
            "再 LEFT JOIN 小时聚合结果，保证每个小时与维度组合都能返回 0。"
        ),
    },
]

HISTORICAL_HOURLY_RULES = [
    {
        "match": HOURLY_MATCH,
        "allow_when": SCALAR_HOURLY_EXEMPTIONS,
        "when_question_date_scopes": ["explicit_other", "unspecified"],
        "required_complete_hour_sequence": True,
        "required_sql_patterns": [
            r"\{\{\s*dashboard_start_yyyymmdd\s*\}\}",
            r"\{\{\s*dashboard_end_yyyymmdd\s*\}\}",
            HOURLY_SCAFFOLD_PATTERN,
            r"\bleft\s+(?:outer\s+)?join\b",
            COALESCE_ZERO_PATTERN,
        ],
        "forbidden_sql_patterns": [HOUR_MAX_CLIP_PATTERN],
        "message": (
            "历史按小时查询必须生成 00:00 到 23:00 的完整 24 小时骨架，"
            "再 LEFT JOIN 聚合结果并用 COALESCE 补零；不得按事实 MAX(time) 截断历史日期。"
        ),
    },
]

VALIDATION_RULES = DAILY_RULES + CURRENT_DAY_HOURLY_RULES + HISTORICAL_HOURLY_RULES

ZERO_FILL_SECTION = f"""{SECTION_START_MARKER}
<!-- platform-foundation-skill:hourly-zero-fill:v1 -->
<!-- platform-foundation-skill:mysql-unsigned-compat:v1 -->
<!-- data-skill-sql-validation: {json.dumps(VALIDATION_RULES, ensure_ascii=False, separators=(',', ':'))} -->
## 按日和按小时结果的连续序列与补零

### 按日结果

1. 每日、每天、按日或逐日查询必须先生成包含起止边界的连续日期序列。
2. 事实数据先按最终粒度聚合，再从日期序列 `LEFT JOIN` 聚合结果，并用 `COALESCE(指标, 0)` 补齐缺失日期。
3. 包含其他分组维度时，先将日期序列与预期维度集合 `CROSS JOIN`，再回填聚合结果。

### 历史完整日按小时结果

1. 明确历史日期、已经结束的自然日和默认完整历史窗口，必须生成 `00:00` 到 `23:00` 的完整 24 小时骨架。
2. 事实数据必须先在看板起止日期以及当前事件、产品、租户、工作空间和权限范围内按小时聚合，再 `LEFT JOIN` 到小时骨架，并用 `COALESCE(指标, 0)` 补零。
3. 历史日期不得使用事实 `MAX(time)` 作为小时上界；即使最后一条事实只到 09 点，也必须返回 10:00 到 23:00 的零值。完全没有事实的历史日同样返回 24 个零值小时。
4. 历史范围包含多个完整日期时，应构造日期集合与 24 小时集合的组合骨架，保持每天 24 个小时。

### 当天实时按小时结果

1. 仅当问题日期意图为当天实时（`current_day`）时，才允许使用事实 `MAX(time)` 作为小时序列上界。
2. `MAX(time)` 必须带上与指标聚合相同的日期、事件、产品、租户、工作空间和权限过滤，只扫描本次查询范围，禁止全表取最大时间。
3. 小时序列从 `00:00` 开始并包含最大事件时间所在小时，再 `LEFT JOIN` 小时聚合结果并用 `COALESCE(指标, 0)` 补零。不得用数据库当前日期或当前时间代替事实水位。
4. 包含已完成历史日和当天的跨日范围，历史日使用完整 24 小时；只有当天部分允许截止到当天事实最大事件小时。
5. “实时总额”“实时总数”“实时合计”或明确要求单值的查询不强制生成小时序列；累计趋势仍必须返回连续小时序列。

### MySQL/MariaDB 方言兼容

1. MySQL/MariaDB 兼容数据源不支持 `CAST(... AS UNSIGNED)` 时，使用已验证的 `SIGNED`、`DECIMAL` 或无需转换的表达式。
2. JSON 数值字段参与聚合或比较时优先使用 `DECIMAL(...)`，不得因为类型转换破坏补零、分组或日期边界。

事实表筛选条件必须保留在事实聚合 CTE 或 `LEFT JOIN ... ON` 中，不能在最终 `WHERE` 中过滤右表并破坏补零结果。
""".strip()


def replace_zero_fill_section(prompt: str, replacement: str) -> str:
    start = prompt.find(SECTION_START_MARKER)
    end = prompt.find(SECTION_END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError("平台小时补零 Skill 标记缺失或顺序异常")
    return prompt[:start] + replacement.rstrip() + "\n\n" + prompt[end:]


def _update_prompt(replacement: str) -> None:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT id, prompt
            FROM custom_prompt
            WHERE tenant_id = 1
              AND type = 'DATA_SKILL'
              AND name = :name
              AND visibility_scope = 'PLATFORM_PUBLIC'
              AND COALESCE(specific_ds, FALSE) = FALSE
              AND position(:skill_marker in COALESCE(prompt, '')) > 0
            FOR UPDATE
            """
        ),
        {"name": SKILL_NAME, "skill_marker": SKILL_MARKER},
    ).mappings().one()
    updated_prompt = replace_zero_fill_section(str(row["prompt"]), replacement)
    result = bind.execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = :prompt,
                embedding = NULL,
                embedding_signature = NULL
            WHERE id = :id
            """
        ),
        {"id": row["id"], "prompt": updated_prompt},
    )
    if result.rowcount != 1:
        raise RuntimeError(f"平台历史小时补零 Skill 更新数量异常: {result.rowcount}")


def upgrade() -> None:
    _update_prompt(ZERO_FILL_SECTION)


def downgrade() -> None:
    # 回滚时恢复上一版本迁移生成的小时规则。
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    previous_path = Path(__file__).with_name("155_platform_mysql_unsigned_compatibility_data_skill.py")
    spec = spec_from_file_location("platform_hourly_previous", previous_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载上一版本平台小时补零规则")
    previous = module_from_spec(spec)
    spec.loader.exec_module(previous)
    previous_section = previous.ZERO_FILL_SECTION.replace(
        '"match":["实时","按小时","每小时","逐小时","小时趋势","当前小时","当前整点"]',
        '"match":["按小时","每小时","逐小时","小时趋势","实时趋势","当前小时","当前整点"]',
    ).replace(
        "用户要求实时、按小时、每小时、逐小时或小时趋势时",
        "用户明确要求按小时、每小时、逐小时、小时趋势、实时趋势、当前小时或当前整点时",
    )
    _update_prompt(previous_section)
