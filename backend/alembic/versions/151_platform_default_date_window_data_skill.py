"""补齐平台基础日期 Skill 的默认日期范围规则。"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "151platformdefaultdate"
down_revision = "150dashboarddatefilteraudit"
branch_labels = None
depends_on = None


SKILL_MARKER = "<!-- platform-foundation-skill:sql-date-grouping:v1 -->"
DATE_SECTION_MARKER = "<!-- platform-foundation-skill:default-date-window:v1 -->"
SKILL_NAME = "平台通用 SQL 日期与分组规范"
DATE_SECTION = f"""{DATE_SECTION_MARKER}
## 默认日期范围与看板参数

1. 用户明确指定日期、自然周期或相对时间范围时，严格按用户范围执行。
2. 用户未指定日期范围时，默认使用过去 7 个完整自然日。
3. 对可转存到看板的时序图，保存 SQL 时保留 `{{{{dashboard_start_yyyymmdd}}}}` 与 `{{{{dashboard_end_yyyymmdd}}}}` 日期占位符，并保存对应日期配置；执行时再由当前看板日期控件传入实际边界。
4. 固定语义指标卡（例如明确限定“今日”或“本月”的单值指标）保持其自身语义，不将看板日期范围强加到该指标。
""".strip()


def upgrade() -> None:
    result = _execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = CASE
                    WHEN position(:date_marker in COALESCE(prompt, '')) = 0
                        THEN rtrim(prompt) || E'\\n\\n' || :date_section
                    ELSE prompt
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
        params={
            "date_marker": DATE_SECTION_MARKER,
            "date_section": DATE_SECTION,
            "name": SKILL_NAME,
            "skill_marker": SKILL_MARKER,
        },
    )
    if result is not None and result.rowcount not in (0, 1):
        raise RuntimeError(f"平台基础日期 Skill 更新数量异常: {result.rowcount}")


def downgrade() -> None:
    _execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = regexp_replace(
                    prompt,
                    E'\\n*<!-- platform-foundation-skill:default-date-window:v1 -->[\\s\\S]*$',
                    ''
                ),
                embedding = NULL,
                embedding_signature = NULL
            WHERE tenant_id = 1
              AND type = 'DATA_SKILL'
              AND name = :name
              AND position(:date_marker in COALESCE(prompt, '')) > 0
            """
        ),
        params={"date_marker": DATE_SECTION_MARKER, "name": SKILL_NAME},
    )


def _execute(statement: sa.TextClause, *, params: dict[str, str]):
    if _offline_mode():
        bound = statement.bindparams(
            *(
                sa.bindparam(name, value=value, literal_execute=True)
                for name, value in params.items()
            )
        )
        op.execute(bound)
        return None
    return op.get_bind().execute(statement, params)


def _offline_mode() -> bool:
    try:
        return bool(op.get_context().as_sql)
    except (AttributeError, NameError):
        return False
