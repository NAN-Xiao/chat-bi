"""补齐平台递归 CTE 列别名错误的通用方言兼容规则。"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "160platformrecursivealiascompat"
down_revision = "159platformrealtimesqlshape"
branch_labels = None
depends_on = None


SKILL_NAME = "平台通用 SQL 日期与分组规范"
SKILL_MARKER = "<!-- platform-foundation-skill:sql-date-grouping:v1 -->"
SECTION_MARKER = "<!-- platform-foundation-skill:recursive-alias-compat:v1 -->"

SECTION = f"""{SECTION_MARKER}
## 递归 CTE 与时间骨架兼容规则

1. 日期、小时和周序列优先使用当前数据源已经验证的非递归数字序列或日期维表；不要因为 SQL 可以被解析就默认递归 CTE 可执行。
2. 只有当前数据源能力元数据明确声明、且已有执行样例验证支持递归 CTE 时，才允许使用 `WITH RECURSIVE`。递归 CTE 必须声明完整列清单，并保证锚点分支与递归分支的列数、顺序和类型一致。
3. 如果数据库返回 `missing column aliases in recursive WITH query`、递归深度限制或同类递归 CTE 方言错误，不能只补列别名后重试；必须移除 `WITH RECURSIVE`，改用非递归数字序列、日期维表或其他已验证的时间骨架。
4. 这是一条平台通用 SQL 方言能力规则，不绑定业务表、指标、字段或具体数据源；当前数据源的能力配置和已验证样例优先。
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
                        E'\\n*<!-- platform-foundation-skill:recursive-alias-compat:v1 -->[\\s\\S]*$',
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
        raise RuntimeError(f"平台递归 CTE 列别名兼容 Skill 更新数量异常: {result.rowcount}")


def downgrade() -> None:
    result = op.get_bind().execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = regexp_replace(
                    prompt,
                    E'\\n*<!-- platform-foundation-skill:recursive-alias-compat:v1 -->[\\s\\S]*$',
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
        raise RuntimeError(f"平台递归 CTE 列别名兼容 Skill 回滚数量异常: {result.rowcount}")
