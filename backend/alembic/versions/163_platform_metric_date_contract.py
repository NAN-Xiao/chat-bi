"""统一平台 Data Skill 的指标卡日期参数契约。"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "163platformmetricdatecontract"
down_revision = "162platformmysqlunsignedruntime"
branch_labels = None
depends_on = None


SKILL_NAME = "平台通用 SQL 日期与分组规范"
OLD_RULE = "固定语义指标卡（例如明确限定“今日”或“本月”的单值指标）保持其自身语义，不将看板日期范围强加到该指标。"
NEW_RULE = "指标卡只要查询或过滤日期字段，就必须使用成对看板日期 token 和完整 `date_filter`；只有完全不涉及日期字段或日期条件的全量累计指标，才可以省略 `date_filter`。固定语义（例如“今日”或“本月”）也必须通过 `date_expression` 表达，不得用固定日期字面量绕过看板日期参数。"


def _replace_rule(old_rule: str, new_rule: str) -> None:
    result = op.get_bind().execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = replace(prompt, :old_rule, :new_rule),
                embedding = NULL,
                embedding_signature = NULL
            WHERE tenant_id = 1
              AND type = 'DATA_SKILL'
              AND name = :name
              AND visibility_scope = 'PLATFORM_PUBLIC'
              AND COALESCE(specific_ds, FALSE) = FALSE
              AND position(:old_rule in COALESCE(prompt, '')) > 0
            """
        ),
        {"old_rule": old_rule, "new_rule": new_rule, "name": SKILL_NAME},
    )
    if result.rowcount not in (0, 1):
        raise RuntimeError(f"平台指标卡日期契约更新数量异常: {result.rowcount}")


def upgrade() -> None:
    _replace_rule(OLD_RULE, NEW_RULE)


def downgrade() -> None:
    _replace_rule(NEW_RULE, OLD_RULE)
