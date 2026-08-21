"""刷新已部署的平台通用 SQL 日期与分组规范 Data Skill。"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision = "147refreshsqlgroupingskill"
down_revision = "146sqlgroupingskill"
branch_labels = None
depends_on = None

SKILL_MARKER = "<!-- platform-foundation-skill:sql-date-grouping:v1 -->"
SKILL_NAME = "平台通用 SQL 日期与分组规范"
SKILL_TARGET_SCOPE = "ALL"
SKILL_VISIBILITY_SCOPE = "PLATFORM_PUBLIC"
SKILL_DESCRIPTION = (
    "约束日期、按日趋势、按月统计和时间分组 SQL 的生成方式，确保投影与分组表达式符合数据库方言。"
)
SKILL_PROMPT = f"""{SKILL_MARKER}
# SQL 日期与分组规范

本 Skill 是平台通用 SQL 结构规则，不提供任何业务表名、字段名、事件名或指标口径。

## 日期格式

1. 必须按数据库方言、结合当前数据源选择日期格式函数：MySQL、AnalyticDB、Doris 和 StarRocks 使用 `DATE_FORMAT(date_expr, format)`；PostgreSQL 使用 `TO_CHAR(date_expr, format)`。
2. 分区过滤或数字日期比较可以使用当前方言对应的数字日期表达式，例如 MySQL 系列使用 `DATE_FORMAT(date_expr, '%Y%m%d')`。
3. 过滤表达式可以与展示表达式采用不同格式，但不能把过滤格式直接复制为展示分组格式。
4. 日期字段、时间字段和表字段必须来自当前数据源 schema，不能凭空生成不存在的字段。

## SELECT 与 GROUP BY

1. `SELECT` 中所有非聚合日期表达式必须以完全一致的表达式出现在 `GROUP BY` 中。
2. 函数、参数、类型转换和日期格式必须完全一致，不能只保证业务语义相同。
3. 禁止 `SELECT DATE_FORMAT(date_expr, '%Y-%m-%d')`，却按 `DATE_FORMAT(date_expr, '%Y%m%d')` 分组。
5. MySQL、AnalyticDB、Doris 和 StarRocks 不得依赖同层 `SELECT` 别名进行 `GROUP BY`；应重复完整表达式，或先在子查询中计算后再按子查询字段分组。
6. `ORDER BY` 可以使用最终输出别名；方言兼容性不明确时重复完整表达式。

<!-- platform-foundation-skill:default-date-window:v1 -->
## 默认日期范围与看板参数

1. 用户明确指定日期、自然周期或相对时间范围时，严格按用户范围执行。
2. 用户未指定日期范围时，默认使用过去 7 个完整自然日。
3. 对可转存到看板的时序图，保存 SQL 时保留 `{{{{dashboard_start_yyyymmdd}}}}` 与 `{{{{dashboard_end_yyyymmdd}}}}` 日期占位符，并保存对应日期配置；执行时再由当前看板日期控件传入实际边界。
4. 指标卡只要查询或过滤日期字段，就必须使用成对看板日期 token 和完整 `date_filter`；只有完全不涉及日期字段或日期条件的全量累计指标，才可以省略 `date_filter`。固定语义（例如“今日”或“本月”）也必须通过 `date_expression` 表达，不得用固定日期字面量绕过看板日期参数。
"""


def _bind():
    return op.get_bind()


def upgrade() -> None:
    bind = _bind()
    datasource_ids_type = postgresql.JSONB if bind.dialect.name == "postgresql" else sa.JSON
    update_stmt = sa.text(
        """
        UPDATE custom_prompt
        SET tenant_id = 1,
            name = :name,
            description = :description,
            target_scope = :target_scope,
            active = TRUE,
            visible = TRUE,
            ai_model_id = NULL,
            create_by = NULL,
            visibility_scope = :visibility_scope,
            prompt = :prompt,
            embedding = NULL,
            embedding_signature = NULL,
            specific_ds = FALSE,
            datasource_ids = :datasource_ids
        WHERE type = 'DATA_SKILL'
          AND position(:marker in COALESCE(prompt, '')) > 0
        """
    ).bindparams(sa.bindparam("datasource_ids", type_=datasource_ids_type))
    bind.execute(
        update_stmt,
        {
            "marker": SKILL_MARKER,
            "name": SKILL_NAME,
            "description": SKILL_DESCRIPTION,
            "target_scope": SKILL_TARGET_SCOPE,
            "visibility_scope": SKILL_VISIBILITY_SCOPE,
            "prompt": SKILL_PROMPT.strip(),
            "datasource_ids": [],
        },
    )


def downgrade() -> None:
    # 旧内容会重新引入已知错误，降级仅回退迁移版本，不回写 Skill。
    pass
