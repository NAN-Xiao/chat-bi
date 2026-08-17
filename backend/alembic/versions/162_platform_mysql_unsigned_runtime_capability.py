"""撤销平台 Skill 对 MySQL UNSIGNED 的全局误禁用。"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "162platformmysqlunsignedruntime"
down_revision = "161platformskilltenantexclusion"
branch_labels = None
depends_on = None


SKILL_NAME = "平台通用 SQL 日期与分组规范"
OLD_SECTION_MARKER = "<!-- platform-foundation-skill:mysql-unsigned-compat:v1 -->"
NEW_SECTION_MARKER = "<!-- platform-foundation-skill:mysql-unsigned-runtime-capability:v2 -->"
OLD_GUIDANCE = """### MySQL/MariaDB 方言兼容

1. 当前 MySQL/MariaDB 兼容数据源不支持 `CAST(... AS UNSIGNED)` 或 `AS UNSIGNED`，需要把 YYYYMMDD 数字或其他数值转换写成当前方言已验证的 `SIGNED` 或 `DECIMAL` 形式。
2. 数据源通过 MySQL 协议接入并不代表底层代理支持全部 MySQL 类型，不能因为驱动名就假定 `UNSIGNED` 可用。
3. JSON 数值字段如果要参与聚合或比较，优先使用 `DECIMAL(...)`，不要强制转成 `UNSIGNED`。
4. 补零、分组和日期边界规则优先于数值类型优化，不要为了转换方便引入方言不兼容类型。"""
NEW_GUIDANCE = """### MySQL/MariaDB 类型转换能力

1. 标准 MySQL/MariaDB 支持 `CAST(... AS SIGNED)` 和 `CAST(... AS UNSIGNED)`；不得在执行前全局禁止其中任一写法。
2. 通过 MySQL 协议接入的兼容引擎可能具有不同能力。只有目标数据库实际执行错误明确拒绝某种类型转换时，才根据该错误改用目标引擎支持的类型。
3. JSON 数值字段需要保留小数精度时优先使用 `DECIMAL(...)`；类型选择必须服从字段语义和目标数据库实际能力，不能为了规避未发生的兼容错误改变数值语义。
4. 补零、分组和日期边界规则与数值类型选择相互独立，不得因修复其中一项静默改变另一项。"""


def _replace_guidance(old_marker: str, new_marker: str, old_guidance: str, new_guidance: str) -> None:
    result = op.get_bind().execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = replace(
                    replace(prompt, :old_marker, :new_marker),
                    :old_guidance,
                    :new_guidance
                ),
                embedding = NULL,
                embedding_signature = NULL
            WHERE tenant_id = 1
              AND type = 'DATA_SKILL'
              AND name = :name
              AND visibility_scope = 'PLATFORM_PUBLIC'
              AND COALESCE(specific_ds, FALSE) = FALSE
              AND position(:old_marker in COALESCE(prompt, '')) > 0
              AND position(:old_guidance in COALESCE(prompt, '')) > 0
            """
        ),
        {
            "old_marker": old_marker,
            "new_marker": new_marker,
            "old_guidance": old_guidance,
            "new_guidance": new_guidance,
            "name": SKILL_NAME,
        },
    )
    if result.rowcount != 1:
        raise RuntimeError(f"平台 MySQL 类型转换 Skill 更新数量异常: {result.rowcount}")


def upgrade() -> None:
    _replace_guidance(OLD_SECTION_MARKER, NEW_SECTION_MARKER, OLD_GUIDANCE, NEW_GUIDANCE)


def downgrade() -> None:
    _replace_guidance(NEW_SECTION_MARKER, OLD_SECTION_MARKER, NEW_GUIDANCE, OLD_GUIDANCE)
