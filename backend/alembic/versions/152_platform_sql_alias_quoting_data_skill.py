"""补齐平台 SQL Skill 的中文别名引用规则。"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "152platformsqlaliasquote"
down_revision = "151platformdefaultdate"
branch_labels = None
depends_on = None


SKILL_MARKER = "<!-- platform-foundation-skill:sql-date-grouping:v1 -->"
ALIAS_SECTION_MARKER = "<!-- platform-foundation-skill:sql-alias-quoting:v1 -->"
SKILL_NAME = "平台通用 SQL 日期与分组规范"
ALIAS_SECTION = f"""{ALIAS_SECTION_MARKER}
## 输出别名与后续引用

1. 中文、空格或其他特殊字符输出别名必须按当前数据库方言使用标识符引号。MySQL、AnalyticDB、Doris 和 StarRocks 使用反引号，例如 AS `注册日期`；PostgreSQL 等使用双引号。
2. 不得使用单引号引用中文字段或输出别名，因为单引号表示字符串值。
3. ORDER BY 可以引用最终输出别名，但必须保留当前方言的标识符引号；MySQL 系示例：ORDER BY `注册日期`, `地区`。
4. 同一查询块的 GROUP BY 应使用原始字段或完整表达式，不得把当前层刚定义的 SELECT 别名伪装成来源表字段。
5. 只有上游 CTE 或子查询已经真实输出中文列时，外层才能限定引用该字段；MySQL 系示例：GROUP BY `c`.`注册日期`, `c`.`地区`。
""".strip()


def upgrade() -> None:
    result = _execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = CASE
                    WHEN position(:alias_marker in COALESCE(prompt, '')) = 0
                        THEN rtrim(prompt) || E'\\n\\n' || :alias_section
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
            "alias_marker": ALIAS_SECTION_MARKER,
            "alias_section": ALIAS_SECTION,
            "name": SKILL_NAME,
            "skill_marker": SKILL_MARKER,
        },
    )
    if result is not None and result.rowcount not in (0, 1):
        raise RuntimeError(f"平台 SQL Skill 更新数量异常: {result.rowcount}")


def downgrade() -> None:
    _execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = regexp_replace(
                    prompt,
                    E'\\n*<!-- platform-foundation-skill:sql-alias-quoting:v1 -->[\\s\\S]*$',
                    ''
                ),
                embedding = NULL,
                embedding_signature = NULL
            WHERE tenant_id = 1
              AND type = 'DATA_SKILL'
              AND name = :name
              AND position(:alias_marker in COALESCE(prompt, '')) > 0
            """
        ),
        params={"alias_marker": ALIAS_SECTION_MARKER, "name": SKILL_NAME},
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
