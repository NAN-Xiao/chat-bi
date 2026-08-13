"""收紧实时 SQL 日期函数和小时骨架形状。"""

from __future__ import annotations

import json

import sqlalchemy as sa

from alembic import op


revision = "159platformrealtimesqlshape"
down_revision = "158platformrealtimehourlyscope"
branch_labels = None
depends_on = None


SKILL_NAME = "平台通用 SQL 日期与分组规范"
SKILL_MARKER = "<!-- platform-foundation-skill:hourly-zero-fill:v1 -->"
SECTION_MARKER = "<!-- platform-foundation-skill:realtime-sql-shape:v1 -->"
VALIDATION_RULES = [
    {
        "match": ["实时"],
        "when_sql_patterns": [r"\bevent_realtime\b"],
        "forbidden_sql_patterns": [
            r"\b(?:CURDATE|CURRENT_DATE|NOW|CURRENT_TIMESTAMP|LOCALTIME|LOCALTIMESTAMP|GETDATE|GETUTCDATE|UTC_TIMESTAMP)\b"
        ],
        "message": "实时 event_realtime 查询必须使用受控业务日期范围或已确定日期，禁止使用数据库当前日期/时间函数。",
    },
    {
        "match": ["按小时", "每小时", "逐小时", "小时趋势", "实时趋势", "当前小时", "当前整点"],
        "when_sql_patterns": [r"\bevent_realtime\b"],
        "forbidden_sql_patterns": [r"\bWITH\s+RECURSIVE\b"],
        "message": "实时固定 24 小时序列优先使用非递归 0 到 23 常量序列；不要生成递归 CTE。",
    },
]

SECTION = f"""<!-- platform-foundation-skill:realtime-sql-shape:v1 -->
<!-- data-skill-sql-validation: {json.dumps(VALIDATION_RULES, ensure_ascii=False, separators=(',', ':'))} -->
## 实时 SQL 形状

1. `event_realtime` 查询必须使用受控业务日期范围或已确定的业务日期字面量，不得使用数据库当前日期/时间函数。
2. 实时固定 24 小时序列优先使用非递归 `0` 到 `23` 常量序列；不要为固定小时范围生成递归 CTE。
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
                        E'\\n*<!-- platform-foundation-skill:realtime-sql-shape:v1 -->[\\s\\S]*$',
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
        raise RuntimeError(f"平台实时 SQL 形状 Skill 更新数量异常: {result.rowcount}")


def downgrade() -> None:
    result = op.get_bind().execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = regexp_replace(
                    prompt,
                    E'\\n*<!-- platform-foundation-skill:realtime-sql-shape:v1 -->[\\s\\S]*$',
                    ''
                ),
                embedding = NULL,
                embedding_signature = NULL
            WHERE tenant_id = 1
              AND type = 'DATA_SKILL'
              AND name = :name
              AND visibility_scope = 'PLATFORM_PUBLIC'
              AND position(:section_marker in COALESCE(prompt, '')) > 0
            """
        ),
        {"section_marker": SECTION_MARKER, "name": SKILL_NAME},
    )
    if result.rowcount != 1:
        raise RuntimeError(f"平台实时 SQL 形状 Skill 回滚数量异常: {result.rowcount}")
