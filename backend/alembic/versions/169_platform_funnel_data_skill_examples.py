"""更新平台漏斗 Data Skill 的候选首步与 AnalyticDB 兼容示例。"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "169platformfunnelexamples"
down_revision = "168platformfunnelskill"
branch_labels = None
depends_on = None

SKILL_MARKER = "<!-- platform-foundation-skill:funnel-window-funnel:v1 -->"
PLATFORM_TENANT_ID = 1
SKILL_VISIBILITY_SCOPE = "PLATFORM_PUBLIC"

OLD_RULE = "13. `step_counts` 必须使用 UNION ALL 为每个配置步骤完整保留一行，集合节点和后续投影均不能通过 `WHERE`、`HAVING`、`QUALIFY`、`LIMIT`、`OFFSET` 或额外 JOIN 删除、筛选或放大步骤行。"
NEW_RULE = OLD_RULE + "\n14. MySQL/AnalyticDB 不得在 `step_counts` 聚合结果上使用 MAX/LAG 值窗口函数，即 `MAX(...) OVER (...)` 或 `LAG(...) OVER (...)`；使用 `step_counts` 标量子查询或等价单行关联取得第一步和上一步人数，避免 `SemanticError`。"

OLD_STEP_METRICS = """step_metrics AS (
    SELECT
        step_order,
        step_name,
        step_count,
        MAX(CASE WHEN step_order = 1 THEN step_count END) OVER () AS first_step_count,
        LAG(step_count) OVER (ORDER BY step_order) AS previous_step_count
    FROM step_counts
)"""

NEW_STEP_METRICS = """step_metrics AS (
    SELECT
        sc.step_order,
        sc.step_name,
        sc.step_count,
        (SELECT first_sc.step_count
         FROM step_counts AS first_sc
         WHERE first_sc.step_order = 1) AS first_step_count,
        (SELECT previous_sc.step_count
         FROM step_counts AS previous_sc
         WHERE previous_sc.step_order = sc.step_order - 1) AS previous_step_count
    FROM step_counts AS sc
)"""

NEGATIVE_EXAMPLES = """
## 反向错误示例

以下写法会在 MySQL/AnalyticDB 的聚合结果上使用不兼容的 MAX/LAG 值窗口函数，可能触发 `1815 SemanticError`，禁止生成：

```sql
SELECT
    step_order,
    MAX(CASE WHEN step_order = 1 THEN step_count END) OVER () AS first_step_count,
    LAG(step_count) OVER (ORDER BY step_order) AS previous_step_count
FROM step_counts;
```

以下逐步 CTE 先把每个主体压缩成唯一最早首步，会漏掉“早期首步未转化、后续首步在窗口内完成”的主体，禁止生成：

```sql
step_1 AS (
    SELECT
        entity_id,
        MIN(event_time) AS first_step_time,
        MIN(event_time) AS step_time
    FROM scoped_events
    WHERE event_name = 'step_a'
    GROUP BY entity_id
)
```

正确的逐步 CTE 应为每个候选首步保留一行，再在后续步骤按 `entity_id + first_step_time` 匹配，并最终按主体取最大完成深度。
""".strip()

FINAL_GUIDANCE = "生成时必须逐项替换示例中的表、字段、`prod` 值、事件条件、步骤名称、步骤数量和窗口秒数"


def _updated_prompt(prompt: str) -> str:
    if all(
        item in prompt
        for item in (NEW_RULE, "## 正向示例", NEW_STEP_METRICS, NEGATIVE_EXAMPLES)
    ):
        return prompt
    required = (OLD_RULE, "## SQL 生成示例", OLD_STEP_METRICS, FINAL_GUIDANCE)
    missing = [item for item in required if item not in prompt]
    if missing:
        raise RuntimeError("平台漏斗 Data Skill 旧版结构与预期不一致，无法安全更新")
    updated = prompt.replace(OLD_RULE, NEW_RULE, 1)
    updated = updated.replace("## SQL 生成示例", "## 正向示例", 1)
    updated = updated.replace(OLD_STEP_METRICS, NEW_STEP_METRICS, 1)
    return updated.replace(FINAL_GUIDANCE, NEGATIVE_EXAMPLES + "\n\n" + FINAL_GUIDANCE, 1)


def _previous_prompt(prompt: str) -> str:
    updated = prompt.replace(NEGATIVE_EXAMPLES + "\n\n", "", 1)
    updated = updated.replace(NEW_STEP_METRICS, OLD_STEP_METRICS, 1)
    updated = updated.replace("## 正向示例", "## SQL 生成示例", 1)
    return updated.replace(NEW_RULE, OLD_RULE, 1)


def _replace_prompt(transform) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, prompt
            FROM custom_prompt
            WHERE type = 'DATA_SKILL'
              AND position(:marker in COALESCE(prompt, '')) > 0
              AND tenant_id = :platform_tenant_id
              AND visibility_scope = :visibility_scope
              AND create_by IS NULL
              AND COALESCE(specific_ds, FALSE) = FALSE
            FOR UPDATE
            """
        ),
        {
            "marker": SKILL_MARKER,
            "platform_tenant_id": PLATFORM_TENANT_ID,
            "visibility_scope": SKILL_VISIBILITY_SCOPE,
        },
    ).mappings().all()
    if len(rows) != 1:
        raise RuntimeError(f"平台漏斗 Data Skill 数量异常: {len(rows)}")
    row = rows[0]
    updated = transform(str(row["prompt"] or ""))
    if updated == row["prompt"]:
        return
    bind.execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET prompt = :prompt,
                embedding = NULL,
                embedding_signature = NULL
            WHERE id = :id
            """
        ),
        {"id": row["id"], "prompt": updated},
    )


def upgrade() -> None:
    _replace_prompt(_updated_prompt)


def downgrade() -> None:
    _replace_prompt(_previous_prompt)
