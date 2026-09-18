"""新增仅供漏斗分析模型使用的 AnalyticDB window_funnel Data Skill。"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision = "168platformfunnelskill"
down_revision = "167platformzerofillexpression"
branch_labels = None
depends_on = None

SKILL_MARKER = "<!-- platform-foundation-skill:funnel-window-funnel:v1 -->"
SKILL_MODEL_SCOPE = '<!-- data-skill-analysis-models: ["funnel"] -->'
SKILL_NAME = "平台通用 Data Skill：AnalyticDB 漏斗分析"
SKILL_TARGET_SCOPE = "ALL"
SKILL_VISIBILITY_SCOPE = "PLATFORM_PUBLIC"
PLATFORM_TENANT_ID = 1
SKILL_DESCRIPTION = (
    "为漏斗分析模型提供 AnalyticDB MySQL window_funnel 语义、窗口规则、日期分区过滤和固定结果列示例。"
)
SKILL_PROMPT = """<!-- data-skill-analysis-models: ["funnel"] -->
<!-- platform-foundation-skill:funnel-window-funnel:v1 -->
# AnalyticDB MySQL 漏斗分析与 window_funnel 规范

本 Skill 只适用于 `analysis_model=funnel`。示例中的 `event`、`uid`、`event`、`time`、`dt`、`prod`、产品值、事件名、步骤数量和窗口秒数都是演示值；生成 SQL 时必须替换为当前漏斗配置、当前工作空间 Schema、字段角色和筛选条件，不能把示例值当作平台业务口径。

## 漏斗规则

1. `window_funnel(window_seconds, 'default', timestamp, cond_1, cond_2, ...)` 按条件参数顺序匹配步骤，并在滑动窗口内返回同一主体可完成的最大连续步骤数。
2. 每个候选首步事件都有自己的窗口起点；同一主体多次发生首步时，不能只保留最早首步后再匹配。按主体聚合后取最大完成深度。
3. 第 N 步人数必须统计 `max_depth >= N` 的主体，不能使用 `max_depth = N`，否则会漏掉继续完成后续步骤的主体。
4. `window_seconds` 必须由 `funnel.window.value` 和 `funnel.window.unit` 精确换算：分钟乘 60、小时乘 3600、天乘 86400。不得照抄示例中的 1800。
5. `window_funnel` 的 timestamp 必须使用 Schema 声明 `role=event_time` 的真实事件时间，并按 AnalyticDB 契约提供 BIGINT 秒值。`epoch_seconds` 可直接使用；`epoch_milliseconds` 必须写成 `CAST(<毫秒事件时间> / 1000 AS SIGNED)`；TIMESTAMP/DATETIME 必须通过 `TIMESTAMPDIFF(SECOND, <固定起点>, <事件时间>)` 转为秒值。YYYYMMDD 分区字段只用于起止日期过滤，不能作为步骤先后时间。
6. `mode=same_day` 是首步所在自然日约束，不等同于滚动 86400 秒；此模式必须使用自然日约束的等价逐步 CTE，不能直接套用 `window_funnel(86400, ...)`。
7. 只有当前数据源明确为支持该函数的 AnalyticDB for MySQL 时才使用原生 `window_funnel`。其他数据库或能力未确认时，使用逐步 CTE 保持相同语义。
8. 启用关联属性时不能使用原生 `window_funnel`，必须使用逐步 CTE，并在每一步按配置属性值与前一步相等进行关联，避免跨属性串联事件。
9. 先在最内层按产品、租户、权限、全局筛选和分区日期收窄事件明细，再计算漏斗。所有筛选值必须来自当前配置或授权语义层。
10. 最终一行对应一个配置步骤，固定输出 `step_order`、`step_name`、`step_count`、`step_rate`、`step_conversion_rate`、`step_dropoff_rate` 六列。
11. 当第一步人数为 0 时，三个比率都返回 `NULL`，不能把第一步转化率写成 `1.0`、流失率写成 `0.0`，避免把无样本展示成完整转化。
12. `user_depth` 主体最大深度聚合层只按配置主体分组，不能使用 `HAVING`、`QUALIFY`、`LIMIT` 或 `OFFSET` 裁剪已计算主体；业务筛选必须在进入该聚合层前应用。
13. `step_counts` 必须使用 UNION ALL 为每个配置步骤完整保留一行，集合节点和后续投影均不能通过 `WHERE`、`HAVING`、`QUALIFY`、`LIMIT`、`OFFSET` 或额外 JOIN 删除、筛选或放大步骤行。

## SQL 生成示例

以下 SQL 仅演示物理表为 `event`、主体为 `event.uid`、事件名为 `event.event`、真实事件时间 `event.time` 已按 Unix 秒存储、分区字段为 `event.dt`、产品字段为 `event.prod`、四步事件为 `pv/fav/cart/buy`、窗口为 1800 秒时的结构：

```sql
WITH dashboard_params AS (
    SELECT
        CAST({{dashboard_start_yyyymmdd}} AS SIGNED) AS start_dt,
        CAST({{dashboard_end_yyyymmdd}} AS SIGNED) AS end_dt
),
scoped_event AS (
    SELECT
        e.uid,
        e.event,
        e.`time` AS event_time
    FROM `event` AS e
    CROSS JOIN dashboard_params AS p
    WHERE e.prod = 110000038
      AND e.dt BETWEEN p.start_dt AND p.end_dt
      AND e.uid IS NOT NULL
      AND e.event IN ('pv', 'fav', 'cart', 'buy')
),
user_depth AS (
    SELECT
        uid,
        window_funnel(
            CAST(1800 AS INTEGER),
            'default',
            event_time,
            event = 'pv',
            event = 'fav',
            event = 'cart',
            event = 'buy'
        ) AS max_depth
    FROM scoped_event
    GROUP BY uid
),
step_counts AS (
    SELECT 1 AS step_order, '浏览' AS step_name,
           COUNT(CASE WHEN max_depth >= 1 THEN 1 END) AS step_count
    FROM user_depth
    UNION ALL
    SELECT 2, '收藏', COUNT(CASE WHEN max_depth >= 2 THEN 1 END)
    FROM user_depth
    UNION ALL
    SELECT 3, '加购', COUNT(CASE WHEN max_depth >= 3 THEN 1 END)
    FROM user_depth
    UNION ALL
    SELECT 4, '购买', COUNT(CASE WHEN max_depth >= 4 THEN 1 END)
    FROM user_depth
),
step_metrics AS (
    SELECT
        step_order,
        step_name,
        step_count,
        MAX(CASE WHEN step_order = 1 THEN step_count END) OVER () AS first_step_count,
        LAG(step_count) OVER (ORDER BY step_order) AS previous_step_count
    FROM step_counts
)
SELECT
    step_order,
    step_name,
    step_count,
    step_count * 1.0 / NULLIF(first_step_count, 0) AS step_rate,
    CASE
        WHEN first_step_count = 0 THEN NULL
        WHEN step_order = 1 THEN 1.0
        ELSE step_count * 1.0 / NULLIF(previous_step_count, 0)
    END AS step_conversion_rate,
    CASE
        WHEN first_step_count = 0 THEN NULL
        WHEN step_order = 1 THEN 0.0
        ELSE 1.0 - step_count * 1.0 / NULLIF(previous_step_count, 0)
    END AS step_dropoff_rate
FROM step_metrics
ORDER BY step_order;
```

生成时必须逐项替换示例中的表、字段、`prod` 值、事件条件、步骤名称、步骤数量和窗口秒数；如果当前配置没有产品筛选，不得虚构 `prod` 条件。如果当前 Schema 未声明可用的 `role=event_time` 字段，应明确报告配置缺失，不得用 `dt` 代替。
"""


def upgrade() -> None:
    bind = op.get_bind()
    datasource_ids_type = postgresql.JSONB if bind.dialect.name == "postgresql" else sa.JSON
    params = {
        "marker": SKILL_MARKER,
        "platform_tenant_id": PLATFORM_TENANT_ID,
        "name": SKILL_NAME,
        "description": SKILL_DESCRIPTION,
        "target_scope": SKILL_TARGET_SCOPE,
        "visibility_scope": SKILL_VISIBILITY_SCOPE,
        "prompt": SKILL_PROMPT.strip(),
        "datasource_ids": [],
    }
    total_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM custom_prompt
            WHERE type = 'DATA_SKILL'
              AND position(:marker in COALESCE(prompt, '')) > 0
            """
        ),
        params,
    ).scalar_one()
    platform_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM custom_prompt
            WHERE type = 'DATA_SKILL'
              AND position(:marker in COALESCE(prompt, '')) > 0
              AND tenant_id = :platform_tenant_id
              AND visibility_scope = :visibility_scope
              AND create_by IS NULL
              AND COALESCE(specific_ds, FALSE) = FALSE
            """
        ),
        params,
    ).scalar_one()
    if total_count != platform_count:
        raise RuntimeError("平台漏斗 Data Skill 标记存在非平台作用域冲突")
    if platform_count > 1:
        raise RuntimeError(f"平台漏斗 Data Skill 数量异常: {platform_count}")

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
          AND tenant_id = :platform_tenant_id
          AND visibility_scope = :visibility_scope
          AND create_by IS NULL
          AND COALESCE(specific_ds, FALSE) = FALSE
        """
    ).bindparams(sa.bindparam("datasource_ids", type_=datasource_ids_type))
    result = bind.execute(update_stmt, params)
    if result.rowcount == 1:
        return
    if platform_count == 1:
        raise RuntimeError("平台漏斗 Data Skill 更新失败")

    insert_stmt = sa.text(
        """
        INSERT INTO custom_prompt (
            tenant_id, type, create_time, name, description, target_scope,
            active, visible, ai_model_id, create_by, visibility_scope, prompt,
            embedding, embedding_signature, specific_ds, datasource_ids
        )
        VALUES (
            :platform_tenant_id, 'DATA_SKILL', NOW(), :name, :description, :target_scope,
            TRUE, TRUE, NULL, NULL, :visibility_scope, :prompt,
            NULL, NULL, FALSE, :datasource_ids
        )
        """
    ).bindparams(sa.bindparam("datasource_ids", type_=datasource_ids_type))
    bind.execute(insert_stmt, params)


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM custom_prompt
            WHERE type = 'DATA_SKILL'
              AND position(:marker in COALESCE(prompt, '')) > 0
              AND tenant_id = 1
              AND visibility_scope = 'PLATFORM_PUBLIC'
              AND create_by IS NULL
              AND COALESCE(specific_ds, FALSE) = FALSE
            """
        ).bindparams(marker=SKILL_MARKER)
    )
