# -*- coding: utf-8 -*-
"""Seed flam / first_zombie datasource-scoped Data Skills."""

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

TENANT_ID = 7477202383789887488
DATASOURCE_ID = 3

DATA_SKILLS: list[dict[str, str]] = [
    {
        "name": "flam 实时数据时区与日期口径",
        "description": "flam / first_zombie 数据源的业务时区、dt 分区与实时看板 SQL 生成规则。",
        "prompt": """<!-- dashboard-refresh-policy:{"auto_refresh":true,"snapshot_max_age_hours":3} -->
<!-- data-skill-source:flam:first-zombie:timezone-realtime -->
# flam 实时数据时区与日期口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于 `event`、`user` 两张表中的日期过滤、实时看板、实时付费、在线人数、小时趋势等问题。

## 业务时区
- 业务时区为 UTC+8（Asia/Shanghai 口径）。
- MySQL 会话的 `CURDATE()`、`NOW()`、`UTC_DATE()`、`UTC_TIMESTAMP()` 可能按 UTC 返回，不能直接代表 flam 业务日。
- 生成 SQL 时如果用户说“今天”“实时”“当前小时”“截至当前整点”，必须先转换到 UTC+8 业务时间。

## 字段口径
- `time` 是毫秒时间戳。业务时间表达式使用：
  `DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR)`
- `dt` 是业务日期分区，格式为 `YYYYMMDD` 数字。
- 对实时查询，为避免跨 UTC/业务日边界漏数，`dt` 至少应覆盖业务今天及前一业务日：
  `e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y%m%d') AS SIGNED)`
- 业务今天的时间窗口使用：
  `DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) >= DATE(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR))`
  且
  `DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) < DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y-%m-%d %H:00:00')`

## 实时看板 SQL 规则
- 实时小时维度应基于 UTC+8 业务时间取小时：
  `DATE_FORMAT(DATE_FORMAT(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR), '%Y-%m-%d %H:00:00'), '%H:00')`
- 实时付费事件次数使用事件：
  `PayBuyRet`, `PayBuyRetBenifit`, `PayBuyRetSandBox`, `PayFinish`, `ServerPayLog`, `ep_pay_purchase_finish`
- 累计付费事件次数应先按业务小时聚合，再对小时做累计求和。
- 在线人数的业务字段是 `event='CCU'` 的 `ext.ed_ccu`。如果当前数据行的 `ext` 没有 `ed_ccu`，应说明数据侧缺少当前在线人数值，不要把 CCU 事件条数或空 `uid` 去重数当成真实在线人数。

## 禁止事项
- 不要在 flam 实时问题里直接用 `CURDATE()` / `NOW()` 作为业务日口径。
- 不要硬猜服务器时区；以本 Data Skill 的 UTC+8 业务时区为准。
- 不要把该时区规则套用到其他数据源。

## 实时看板持久 SQL
以下 SQL 是本 Data Skill 对 `实时看板` 已保存组件的落地配置；看板手动刷新会复用已保存 SQL，不会自动重新生成。

<!-- dashboard-sql:e3fe7e4819e64b71b76d9329a3023359 -->
```sql
SELECT DATE_FORMAT(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR), '%H:00') AS `时间`,
       MAX(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.ed_ccu')), '') AS DECIMAL(18,4))) AS `实时在线人数`
FROM `event` e
WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
               AND CAST(DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y%m%d') AS SIGNED)
  AND DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) >= DATE(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR))
  AND DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) < DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y-%m-%d %H:00:00')
  AND e.event = 'CCU'
  AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.ed_ccu')), '') IS NOT NULL
GROUP BY `时间`
ORDER BY `时间`
LIMIT 24
```

<!-- dashboard-sql:4fc570b4be7d406c9f648d9088f760bb -->
```sql
SELECT DATE_FORMAT(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR), '%H:00') AS `小时`,
       COUNT(*) AS `实时付费事件次数`
FROM `event` e
WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
               AND CAST(DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y%m%d') AS SIGNED)
  AND DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) >= DATE(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR))
  AND DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) < DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y-%m-%d %H:00:00')
  AND e.event IN ('PayBuyRet','PayBuyRetBenifit','PayBuyRetSandBox','PayFinish','ServerPayLog','ep_pay_purchase_finish')
GROUP BY `小时`
ORDER BY `小时`
LIMIT 24
```

<!-- dashboard-sql:2149b7abbc6c4cd7ad6f52379e69b15a -->
```sql
SELECT h1.`小时`,
       SUM(h2.`每小时付费事件次数`) AS `累计付费事件次数`
FROM (
    SELECT DATE_FORMAT(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR), '%H:00') AS `小时`,
           COUNT(*) AS `每小时付费事件次数`
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
                   AND CAST(DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y%m%d') AS SIGNED)
      AND DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) >= DATE(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR))
      AND DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) < DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y-%m-%d %H:00:00')
      AND e.event IN ('PayBuyRet','PayBuyRetBenifit','PayBuyRetSandBox','PayFinish','ServerPayLog','ep_pay_purchase_finish')
    GROUP BY `小时`
) h1
JOIN (
    SELECT DATE_FORMAT(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR), '%H:00') AS `小时`,
           COUNT(*) AS `每小时付费事件次数`
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
                   AND CAST(DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y%m%d') AS SIGNED)
      AND DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) >= DATE(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR))
      AND DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) < DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y-%m-%d %H:00:00')
      AND e.event IN ('PayBuyRet','PayBuyRetBenifit','PayBuyRetSandBox','PayFinish','ServerPayLog','ep_pay_purchase_finish')
    GROUP BY `小时`
) h2 ON h2.`小时` <= h1.`小时`
GROUP BY h1.`小时`
ORDER BY h1.`小时`
LIMIT 24
```""",
    },
]


def _prompt(skill: dict[str, str]) -> str:
    return (skill["prompt"] or "").strip()


def _upsert_skill(cur, *, tenant_id: int, datasource_id: int, skill: dict[str, str], now: dt.datetime) -> int:
    prompt = _prompt(skill)
    marker = prompt.splitlines()[0].strip()
    cur.execute(
        """
        SELECT id
        FROM custom_prompt
        WHERE type = 'DATA_SKILL'
          AND position(%s in COALESCE(prompt, '')) > 0
        ORDER BY id
        LIMIT 1
        """,
        (marker,),
    )
    row = cur.fetchone()
    values = (
        tenant_id,
        skill["name"][:255],
        skill["description"],
        prompt,
        Jsonb([datasource_id]),
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
            """,
            (*values, skill_id),
        )
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
        VALUES (%s, 'DATA_SKILL', %s, %s, %s, 'ALL', TRUE, TRUE, NULL, NULL, 'ADMIN_PUBLIC', %s, TRUE, %s, NULL, NULL)
        RETURNING id
        """,
        (tenant_id, now, skill["name"][:255], skill["description"], prompt, Jsonb([datasource_id])),
    )
    return int(cur.fetchone()[0])


def _save_embeddings(ids: list[int], tenant_id: int) -> int:
    if not ids:
        return 0
    export_postgres_compat_env(DB)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from sqlalchemy.orm import scoped_session, sessionmaker

    from apps.chat.curd.custom_prompt_embedding import save_custom_prompt_skill_embedding
    from common.core.db import engine

    session_maker = scoped_session(sessionmaker(bind=engine))
    return save_custom_prompt_skill_embedding(session_maker, ids, tenant_id=tenant_id)


def main() -> None:
    now = dt.datetime.now()
    ids: list[int] = []
    with psycopg.connect(**DB) as conn:
        with conn.cursor() as cur:
            for skill in DATA_SKILLS:
                ids.append(_upsert_skill(cur, tenant_id=TENANT_ID, datasource_id=DATASOURCE_ID, skill=skill, now=now))
        conn.commit()
    saved = _save_embeddings(ids, TENANT_ID)
    print(f"Upserted flam data skills: {ids}; embeddings saved: {saved}")


if __name__ == "__main__":
    main()
