"""统一 MySQL 兼容数据源生成 SQL 时的数值类型转换。"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "165platformmysqlsignedgeneration"
down_revision = "164platformhistoricalhourly"
branch_labels = None
depends_on = None


SKILL_NAME = "平台通用 SQL 日期与分组规范"
SKILL_MARKER = "<!-- platform-foundation-skill:sql-date-grouping:v1 -->"
OLD_MARKERS = (
    "<!-- platform-foundation-skill:mysql-unsigned-compat:v1 -->",
    "<!-- platform-foundation-skill:mysql-unsigned-runtime-capability:v2 -->",
)
NEW_MARKER = "<!-- platform-foundation-skill:mysql-signed-generation:v3 -->"
OLD_GUIDANCE = (
    """### MySQL/MariaDB 方言兼容

1. 当前 MySQL/MariaDB 兼容数据源不支持 `CAST(... AS UNSIGNED)` 或 `AS UNSIGNED`，需要把 YYYYMMDD 数字或其他数值转换写成当前方言已验证的 `SIGNED` 或 `DECIMAL` 形式。
2. 数据源通过 MySQL 协议接入并不代表底层代理支持全部 MySQL 类型，不能因为驱动名就假定 `UNSIGNED` 可用。
3. JSON 数值字段如果要参与聚合或比较，优先使用 `DECIMAL(...)`，不要强制转成 `UNSIGNED`。
4. 补零、分组和日期边界规则优先于数值类型优化，不要为了转换方便引入方言不兼容类型。""",
    """### MySQL/MariaDB 类型转换能力

1. 标准 MySQL/MariaDB 支持 `CAST(... AS SIGNED)` 和 `CAST(... AS UNSIGNED)`；不得在执行前全局禁止其中任一写法。
2. 通过 MySQL 协议接入的兼容引擎可能具有不同能力。只有目标数据库实际执行错误明确拒绝某种类型转换时，才根据该错误改用目标引擎支持的类型。
3. JSON 数值字段需要保留小数精度时优先使用 `DECIMAL(...)`；类型选择必须服从字段语义和目标数据库实际能力，不能为了规避未发生的兼容错误改变数值语义。
4. 补零、分组和日期边界规则与数值类型选择相互独立，不得因修复其中一项静默改变另一项。""",
    """### MySQL/MariaDB 方言兼容

1. MySQL/MariaDB 兼容数据源不支持 `CAST(... AS UNSIGNED)` 时，使用已验证的 `SIGNED`、`DECIMAL` 或无需转换的表达式。
2. JSON 数值字段参与聚合或比较时优先使用 `DECIMAL(...)`，不得因为类型转换破坏补零、分组或日期边界。""",
)
NEW_GUIDANCE = """### MySQL/MariaDB 类型转换能力

1. 生成 SQL 时统一使用 `CAST(... AS SIGNED)`；禁止生成 `CAST(... AS UNSIGNED)` 或 `AS UNSIGNED`，以兼容当前 MySQL 协议数据源的实际执行引擎。
2. `UNSIGNED` 虽是标准 MySQL/MariaDB 合法类型，但兼容引擎不一定实现它；该生成策略只约束 AI 生成 SQL，不改变用户手写 SQL 的标准方言校验。
3. JSON 数值字段需要保留小数精度时优先使用 `DECIMAL(...)`；类型选择不能破坏字段语义、补零、分组或日期边界。"""
DOWNGRADE_GUIDANCE = """### MySQL/MariaDB 方言兼容

1. MySQL/MariaDB 兼容数据源不支持 `CAST(... AS UNSIGNED)` 时，使用已验证的 `SIGNED`、`DECIMAL` 或无需转换的表达式。
2. JSON 数值字段参与聚合或比较时优先使用 `DECIMAL(...)`，不得因为类型转换破坏补零、分组或日期边界。"""


def upgrade() -> None:
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
    ).mappings().first()
    if row is None:
        raise RuntimeError("平台 MySQL SIGNED 生成规则的 Data Skill 不存在")

    prompt = str(row["prompt"] or "")
    for marker in OLD_MARKERS:
        prompt = prompt.replace(marker, NEW_MARKER)
    for guidance in OLD_GUIDANCE:
        prompt = prompt.replace(guidance, NEW_GUIDANCE)
    if NEW_GUIDANCE not in prompt:
        raise RuntimeError("平台 MySQL SIGNED 生成规则未能匹配现有 Data Skill")

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
        {"id": row["id"], "prompt": prompt},
    )
    if result.rowcount != 1:
        raise RuntimeError(f"平台 MySQL SIGNED 生成规则更新数量异常: {result.rowcount}")


def downgrade() -> None:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = replace(
                    replace(prompt, :new_marker, :old_marker),
                    :new_guidance,
                    :old_guidance
                ),
                embedding = NULL,
                embedding_signature = NULL
            WHERE tenant_id = 1
              AND type = 'DATA_SKILL'
              AND name = :name
              AND visibility_scope = 'PLATFORM_PUBLIC'
              AND COALESCE(specific_ds, FALSE) = FALSE
              AND position(:new_marker in COALESCE(prompt, '')) > 0
            """
        ),
        {
            "name": SKILL_NAME,
            "new_marker": NEW_MARKER,
            "old_marker": OLD_MARKERS[0],
            "new_guidance": NEW_GUIDANCE,
            "old_guidance": DOWNGRADE_GUIDANCE,
        },
    )
    if result.rowcount != 1:
        raise RuntimeError(f"平台 MySQL SIGNED 生成规则回滚数量异常: {result.rowcount}")
