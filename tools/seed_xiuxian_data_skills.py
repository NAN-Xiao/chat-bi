# -*- coding: utf-8 -*-
"""幂等写入修仙数据源的工作空间级 Data Skill。"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from core_system_db import core_system_db_config, export_postgres_compat_env

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"


DB = core_system_db_config()
TENANT_ID = 7482727237662281728
DATASOURCE_ID = 6

DATA_SKILLS: list[dict[str, str]] = [
    {
        "name": "修仙业务日期与按日聚合口径",
        "description": "规范修仙数据源 event、user 表中 YYYYMMDD 数字分区字段 dt 的过滤、聚合和输出格式。",
        "prompt": """<!-- data-skill-source:xiuxian:date-partition-aggregation -->
# 修仙业务日期与按日聚合口径

## 适用范围

- 仅适用于当前修仙工作空间的数据源，datasource_id=6。
- 适用于 `event`、`user` 表中按业务日期过滤、按日聚合和日期趋势展示的问题。

## 字段语义

- `dt` 是 `YYYYMMDD` 格式的整数业务日期分区字段，不是普通数值指标。
- SQL 的日期筛选、分组和排序必须继续使用原始整数 `dt`，以保留分区裁剪能力和自然日期顺序。
- 当 `dt` 出现在 SELECT 结果中时，必须转换为 `YYYY-MM-DD` 文本，并使用稳定字段别名 `dt`。

## SQL 规则

- WHERE 使用原始字段，例如 `e.dt BETWEEN 20260616 AND 20260715`；不要在 WHERE 中对 `dt` 包裹 `STR_TO_DATE`。
- 用户未指定日期窗口时，以相关明细表的最大可用业务日期为结束日期，默认查询最近 28 个自然日。
- 按日聚合使用 `GROUP BY e.dt`，并使用 `ORDER BY e.dt`。
- SELECT 输出使用 `DATE_FORMAT(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS dt`。
- 表格中的 `dt` 展示为 `YYYY-MM-DD`；趋势图横轴绑定 `dt`，不要把它作为数值轴或添加千分位。
- 计数、金额等指标保持各自的数值类型，不要因为日期格式化而转成文本。

## 最近 30 个完整自然日窗口

- 仅当问题明确要求最近 30 个完整自然日，并且当前数据每天稳定产出完整分区时，才使用昨天作为结束日期。
- 起止日期均包含在内；昨天减 29 天到昨天，共覆盖 30 个自然日。

```sql
WITH bounds AS (
    SELECT
        CAST(
            DATE_FORMAT(
                DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 DAY), INTERVAL 29 DAY),
                '%Y%m%d'
            ) AS SIGNED
        ) AS start_dt,
        CAST(
            DATE_FORMAT(
                DATE_SUB(CURDATE(), INTERVAL 1 DAY),
                '%Y%m%d'
            ) AS SIGNED
        ) AS end_dt
)
```

- 后续 CTE 必须通过 `JOIN bounds b` 或 `CROSS JOIN bounds b` 引用边界，并使用 `e.dt BETWEEN b.start_dt AND b.end_dt` 过滤原始整数分区字段。
- 不得在计算 `MAX(dt)` 的同一查询层的 `WHERE` 中再次使用 `MAX(dt)`，也不得生成 `WHERE dt >= 包含 MAX(dt) 的表达式`。
- 如果数据可能延迟、停更或存在未来分区，必须改用下方以最大可用业务日期为锚点的标准聚合 SQL。

## 标准聚合 SQL

```sql
WITH bounds AS (
    SELECT MAX(e.dt) AS end_dt
    FROM `event` e
)
SELECT
    DATE_FORMAT(
        STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'),
        '%Y-%m-%d'
    ) AS dt,
    COUNT(*) AS total_count
FROM `event` e
CROSS JOIN bounds b
WHERE e.dt BETWEEN
      CAST(
          DATE_FORMAT(
              DATE_SUB(STR_TO_DATE(CAST(b.end_dt AS CHAR), '%Y%m%d'), INTERVAL 27 DAY),
              '%Y%m%d'
          ) AS SIGNED
      )
      AND b.end_dt
  AND e.event = 'ClickTenDraw'
GROUP BY e.dt
ORDER BY e.dt;
```

## 禁止事项

- 不要直接 `SELECT dt` 后把八位日期交给前端按数值展示。
- 不要只依赖字段名猜测日期；本 Data Skill 只声明当前数据源已经确认的 `event.dt`、`user.dt` 语义。
- 不要把本口径传播到其他数据源。
""",
    }
]


def _upsert_skill(cur, *, skill: dict[str, str], now: dt.datetime) -> int:
    prompt = skill["prompt"].strip()
    marker = prompt.splitlines()[0].strip()
    lock_key = f"{TENANT_ID}:{DATASOURCE_ID}:{marker}"
    cur.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (lock_key,),
    )
    cur.execute(
        """
        SELECT id
        FROM custom_prompt
        WHERE tenant_id = %s
          AND type = 'DATA_SKILL'
          AND specific_ds = TRUE
          AND datasource_ids = %s::jsonb
          AND position(%s in COALESCE(prompt, '')) > 0
        ORDER BY id
        LIMIT 1
        """,
        (TENANT_ID, Jsonb([DATASOURCE_ID]), marker),
    )
    row = cur.fetchone()
    values = (
        TENANT_ID,
        skill["name"][:255],
        skill["description"],
        prompt,
        Jsonb([DATASOURCE_ID]),
    )
    if row:
        skill_id = int(row[0])
        cur.execute(
            """
            UPDATE custom_prompt
            SET tenant_id = %s,
                name = %s,
                description = %s,
                target_scope = 'ALL',
                active = TRUE,
                visible = TRUE,
                ai_model_id = NULL,
                visibility_scope = 'ADMIN_PUBLIC',
                create_by = NULL,
                prompt = %s,
                specific_ds = TRUE,
                datasource_ids = %s,
                embedding = NULL,
                embedding_signature = NULL
            WHERE id = %s
              AND tenant_id = %s
              AND type = 'DATA_SKILL'
              AND specific_ds = TRUE
              AND datasource_ids = %s::jsonb
            """,
            (*values, skill_id, TENANT_ID, Jsonb([DATASOURCE_ID])),
        )
        if cur.rowcount != 1:
            raise RuntimeError(f"Data Skill 作用域已变化，拒绝更新: {skill_id}")
        return skill_id

    cur.execute(
        """
        INSERT INTO custom_prompt (
            tenant_id,
            type,
            create_time,
            name,
            description,
            target_scope,
            active,
            visible,
            ai_model_id,
            create_by,
            visibility_scope,
            prompt,
            specific_ds,
            datasource_ids,
            embedding,
            embedding_signature
        )
        VALUES (%s, 'DATA_SKILL', %s, %s, %s, 'ALL', TRUE, TRUE, NULL, NULL,
                'ADMIN_PUBLIC', %s, TRUE, %s, NULL, NULL)
        RETURNING id
        """,
        (
            TENANT_ID,
            now,
            skill["name"][:255],
            skill["description"],
            prompt,
            Jsonb([DATASOURCE_ID]),
        ),
    )
    return int(cur.fetchone()[0])


def _save_embeddings(ids: list[int]) -> int:
    export_postgres_compat_env(DB)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from sqlalchemy.orm import scoped_session, sessionmaker

    from apps.chat.curd.custom_prompt_embedding import save_custom_prompt_skill_embedding
    from common.core.db import engine

    session_maker = scoped_session(sessionmaker(bind=engine))
    return save_custom_prompt_skill_embedding(session_maker, ids, tenant_id=TENANT_ID)


def main() -> None:
    now = dt.datetime.now()
    with psycopg.connect(**DB) as conn:
        with conn.cursor() as cur:
            ids = [_upsert_skill(cur, skill=skill, now=now) for skill in DATA_SKILLS]
        conn.commit()
    saved = _save_embeddings(ids)
    if saved != len(ids):
        raise RuntimeError(
            f"Data Skill embedding 保存不完整: 期望 {len(ids)}，实际 {saved}"
        )
    print(f"修仙 Data Skills 已写入: {ids}; embeddings 已保存: {saved}")


if __name__ == "__main__":
    main()
