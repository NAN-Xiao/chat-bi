# -*- coding: utf-8 -*-
"""幂等写入修仙数据源的工作空间级 Data Skill。"""

from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.types.json import Jsonb

from core_system_db import core_system_db_config, export_postgres_compat_env
from xiuxian_dashboard_skill_catalog import (
    EXPECTED_VIEW_IDS,
    MAX_PROMPT_CHARS,
    TOPICS,
    build_topic_prompt,
    validate_catalog,
    validate_prompt_length,
)

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"


DB = core_system_db_config()
TENANT_ID = 7482727237662281728
DATASOURCE_ID = 6
PUBLISH_LOCK_KEY = f"xiuxian-data-skills:{TENANT_ID}:{DATASOURCE_ID}"

_LEGACY_DATA_SKILLS: list[dict[str, str]] = [
    {
        "name": "修仙业务日期与按日聚合口径",
        "description": "规范修仙数据源 event、user 表中 YYYYMMDD 数字分区字段 dt 的过滤、聚合和输出格式。",
        "prompt": """<!-- data-skill-source:xiuxian:date-partition-aggregation -->
<!-- data-skill-sql-validation:[
  {
    "forbidden_sql_patterns":[
      "\\\\bMAX\\\\s*\\\\(\\\\s*(?:`?[A-Za-z_][A-Za-z0-9_]*`?\\\\s*\\\\.\\\\s*)?`?dt`?\\\\s*\\\\)"
    ],
    "message":"修仙数据源禁止使用 MAX(dt) 扫描最大业务日期；请根据用户时间范围或默认最近 28 天直接生成 dt 分区边界。"
  },
  {
    "forbidden_sql_patterns":[
      "\\\\bWITH\\\\s+(?:RECURSIVE\\\\s+)?`?bounds`?\\\\s*(?:\\\\([^)]*\\\\)\\\\s*)?AS\\\\s*\\\\(",
      "\\\\b(?:CROSS\\\\s+JOIN|JOIN|FROM)\\\\s+`?bounds`?\\\\b"
    ],
    "message":"修仙数据源禁止使用 bounds CTE 关联事件或快照大表；请把动态日期表达式直接写入每个表别名自己的 dt 分区条件。"
  }
] -->
# 修仙业务日期与按日聚合口径

## 适用范围

- 仅适用于当前修仙工作空间的数据源，datasource_id=6。
- 适用于 `event`、`user` 表中按业务日期过滤、按日聚合和日期趋势展示的问题。

## 字段语义

- `dt` 是 `YYYYMMDD` 格式的整数业务日期分区字段，不是普通数值指标。
- SQL 的日期筛选、分组和排序必须继续使用原始整数 `dt`，以保留分区裁剪能力和自然日期顺序。
- 当 `dt` 出现在 SELECT 结果中时，必须转换为 `YYYY-MM-DD` 文本，并使用稳定字段别名 `dt`。

## SQL 规则

- WHERE 使用原始字段，例如 `WHERE e.dt BETWEEN 20260616 AND 20260715`；不要在 WHERE 中对 `dt` 包裹 `STR_TO_DATE`。
- 按日聚合使用 `GROUP BY e.dt`，并使用 `ORDER BY e.dt`。
- SELECT 输出使用 `DATE_FORMAT(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS dt`。
- 表格中的 `dt` 展示为 `YYYY-MM-DD`；趋势图横轴绑定 `dt`，不要把它作为数值轴或添加千分位。
- 计数、金额等指标保持各自的数值类型，不要因为日期格式化而转成文本。

## 日期窗口规则

- 用户指定绝对起止日期时，直接将用户日期转换为 `YYYYMMDD` 整数边界。
- 用户指定相对日期窗口时，根据用户要求的窗口长度动态计算边界，结束日期默认为昨天。
- 用户未指定日期窗口时，默认查询截至昨天的最近 28 个自然日。
- 起止日期均包含。最近 `N` 个完整自然日使用当前日期减 `N` 天作为开始日期、当前日期减 1 天作为结束日期。
- 下面 SQL 只展示一种相对日期边界写法；其中 29 天是示例参数，不表示固定查询范围，必须按用户问题替换。
- 动态边界必须直接写入每个大表别名自己的 `WHERE` 或 `JOIN ON` 分区条件，禁止先生成单行 `bounds` CTE 后再通过 `JOIN` / `CROSS JOIN` 引用。

```sql
WHERE e.dt BETWEEN
    CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 29 DAY), '%Y%m%d') AS SIGNED)
    AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
```

- 后续每个读取 `event`、`user` 等大表的 CTE 都必须在自身的 `WHERE` 或 `JOIN ON` 中直接限制对应别名的原始整数 `dt` 分区字段。
- 禁止使用 `MAX(dt)`、`MAX(e.dt)` 或其它 `MAX(<别名>.dt)` 聚合扫描最大业务日期；也不得通过额外聚合或扫描日期字段来推断查询边界。日期边界必须来自用户问题或上述默认窗口。
- 当前窗口没有业务分区时，明确返回当前窗口无数据；不得回退为全历史无界扫描。

## 禁止事项

- 不要直接 `SELECT dt` 后把八位日期交给前端按数值展示。
- 不得为确定日期边界对 `event` 或 `user` 额外执行日期聚合扫描，包括 `MAX(dt)` 最大分区探测。
- 不要只依赖字段名猜测日期；本 Data Skill 只声明当前数据源已经确认的 `event.dt`、`user.dt` 语义。
- 不要把本口径传播到其他数据源。
""",
    },
]


DATE_PARTITION_SKILL = _LEGACY_DATA_SKILLS[0]
LEGACY_PAYMENT_MARKER = (
    "<!-- data-skill-source:xiuxian:paybuyret-monetization-arppu -->"
)
SERVERPAYLOG_MARKER = (
    "<!-- data-skill-source:xiuxian:serverpaylog-monetization-arppu -->"
)
EMPTY_DASHBOARD_VIEW_ID = "1e4e34743f2d47dfa1c2948742b93a50"
DATA_SKILLS: list[dict[str, str]] = [DATE_PARTITION_SKILL]

SERVERPAYLOG_VALIDATION = """<!-- data-skill-sql-validation:[
  {
    "match":["收入","流水","付费金额","付费用户","ARPU","arpu","ARPPU","arppu"],
    "required_sql_contains":["ServerPayLog","$.money"],
    "forbidden_sql_contains":["PayBuyRet","ed_money","paytotal"],
    "message":"修仙收入、ARPU 和 ARPPU 必须使用 ServerPayLog 的 personal.money 与去重 uid；PayBuyRet、ed_money 和 paytotal 不能作为真实收入来源。"
  },
  {
    "match":["付费用户","ARPU","arpu","ARPPU","arppu"],
    "required_sql_patterns":[
      "COUNT\\\\s*\\\\(\\\\s*DISTINCT\\\\s+(?:`?\\\\w+`?\\\\s*\\\\.\\\\s*)?`?uid`?\\\\s*\\\\)"
    ],
    "message":"修仙收入、ARPU 和 ARPPU 必须使用 ServerPayLog 的 personal.money 与去重 uid；PayBuyRet、ed_money 和 paytotal 不能作为真实收入来源。"
  }
] -->"""


def dashboard_sql_block(view_id: str, sql: str) -> str:
    """把一个推荐看板抽屉保存为可追溯 SQL 块。"""

    return f"<!-- dashboard-sql:{view_id} -->\n```sql\n{sql.strip()}\n```"


def _index_dashboard_drawers(dashboards: Sequence[Any]) -> dict[str, Any]:
    drawers: dict[str, Any] = {}
    for dashboard in dashboards:
        if int(dashboard.tenant_id) != TENANT_ID or int(dashboard.datasource) != DATASOURCE_ID:
            raise ValueError(f"看板 {dashboard.id} 不属于修仙工作空间 datasource 6")
        for drawer in dashboard.drawers:
            view_id = str(drawer.view_id)
            if view_id in drawers:
                raise ValueError(f"推荐看板抽屉 view id 重复：{view_id}")
            if not drawer.sql.strip() and view_id != EMPTY_DASHBOARD_VIEW_ID:
                raise ValueError(f"推荐看板抽屉 SQL 为空：{view_id}")
            drawers[view_id] = drawer
    if set(drawers) != set(EXPECTED_VIEW_IDS):
        missing = sorted(set(EXPECTED_VIEW_IDS).difference(drawers))
        extra = sorted(set(drawers).difference(EXPECTED_VIEW_IDS))
        raise ValueError(f"推荐看板抽屉与 Skill 目录不一致：missing={missing}, extra={extra}")
    return drawers


def _topic_marker(slug: str) -> str:
    if slug == "serverpaylog-revenue":
        return SERVERPAYLOG_MARKER
    return f"<!-- data-skill-source:xiuxian:dashboard:{slug} -->"


def _topic_authority(topic_slug: str) -> str:
    if topic_slug != "serverpaylog-revenue":
        return ""
    return """
## 权威交易字段
- 真实交易事件固定为 `event = 'ServerPayLog'`。
- 收入金额使用 `personal.money`，订单号使用 `personal.orderId`，商品使用 `personal.productid`。
- 付费用户使用 `COUNT(DISTINCT uid)`；ARPPU 分母为付费用户，ARPU 分母为同期 UserActive 活跃用户。
- PayBuyRet 只描述支付流程事件，不得作为真实收入、订单、付费用户或 ARPU/ARPPU 来源。
""".strip()


def build_data_skills(dashboards: Sequence[Any]) -> list[dict[str, str]]:
    """从完整推荐看板快照生成 1 条基础 Skill 和 12 条主题 Skill。"""

    validate_catalog()
    drawers = _index_dashboard_drawers(dashboards)
    skills = [dict(DATE_PARTITION_SKILL)]
    for topic in TOPICS:
        effective_topic = replace(
            topic,
            view_ids=tuple(
                view_id
                for view_id in topic.view_ids
                if view_id != EMPTY_DASHBOARD_VIEW_ID
            ),
        )
        blocks = [
            dashboard_sql_block(view_id, drawers[view_id].sql)
            for view_id in effective_topic.view_ids
        ]
        marker = _topic_marker(topic.slug)
        sections = [marker]
        if topic.slug == "serverpaylog-revenue":
            sections.append(SERVERPAYLOG_VALIDATION)
        sections.extend(
            [
                build_topic_prompt(effective_topic),
                "## 工作空间边界\n仅适用于修仙工作空间 datasource_id=6；不得传播到其他工作空间或数据源。",
            ]
        )
        authority = _topic_authority(topic.slug)
        if authority:
            sections.append(authority)
        sections.extend(blocks)
        prompt = "\n\n".join(sections).strip()
        validate_prompt_length(prompt)
        if len(blocks) > 6 or len(prompt) > MAX_PROMPT_CHARS:
            raise ValueError(f"Skill 体积超限: {topic.slug}")
        skills.append(
            {
                "name": topic.name,
                "description": topic.description,
                "prompt": prompt,
            }
        )
    if len(skills) != 13:
        raise ValueError(f"修仙工作空间 Skill 数量必须为 13，实际为 {len(skills)}")
    return skills


def _find_skill_by_marker(cur: Any, marker: str) -> tuple[Any, ...] | None:
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
    return cur.fetchone()


def _upsert_skill(cur, *, skill: dict[str, str], now: dt.datetime) -> int:
    prompt = skill["prompt"].strip()
    marker = prompt.splitlines()[0].strip()
    lock_key = f"{TENANT_ID}:{DATASOURCE_ID}:{marker}"
    cur.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (lock_key,),
    )
    row = _find_skill_by_marker(cur, marker)
    if row is None and marker == SERVERPAYLOG_MARKER:
        row = _find_skill_by_marker(cur, LEGACY_PAYMENT_MARKER)
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


def upsert_skills(
    cur: Any,
    skills: Sequence[dict[str, str]],
    *,
    now: dt.datetime | None = None,
) -> list[int]:
    """在同一事务游标中批量幂等写入主题 Skill。"""

    write_time = now or dt.datetime.now()
    return [_upsert_skill(cur, skill=skill, now=write_time) for skill in skills]


def backup_existing_skills(
    cur: Any,
    markers: Sequence[str],
) -> dict[str, list[dict[str, Any]]]:
    """快照目标 Skill 完整记录及用户启用偏好。"""

    normalized_markers = [str(marker).strip() for marker in markers if str(marker).strip()]
    cur.execute(
        """
        SELECT to_jsonb(cp)
        FROM custom_prompt cp
        WHERE cp.tenant_id = %s
          AND cp.type = 'DATA_SKILL'
          AND cp.specific_ds = TRUE
          AND cp.datasource_ids = %s::jsonb
          AND EXISTS (
              SELECT 1
              FROM unnest(%s::text[]) AS marker(value)
              WHERE position(marker.value in COALESCE(cp.prompt, '')) > 0
          )
        ORDER BY cp.id
        """,
        (TENANT_ID, Jsonb([DATASOURCE_ID]), normalized_markers),
    )
    skills = [dict(row[0]) for row in cur.fetchall()]
    skill_ids = [int(skill["id"]) for skill in skills]
    cur.execute(
        """
        SELECT to_jsonb(pref)
        FROM custom_prompt_user_preference pref
        WHERE pref.tenant_id = %s
          AND pref.custom_prompt_id = ANY(%s)
        ORDER BY pref.id
        """,
        (TENANT_ID, skill_ids),
    )
    preferences = [dict(row[0]) for row in cur.fetchall()]
    return {"skills": skills, "preferences": preferences}


_RESTORE_SKILL_COLUMNS = (
    "tenant_id",
    "type",
    "create_time",
    "name",
    "description",
    "target_scope",
    "active",
    "visible",
    "ai_model_id",
    "create_by",
    "visibility_scope",
    "prompt",
    "embedding",
    "embedding_signature",
    "specific_ds",
    "datasource_ids",
)
_RESTORE_JSONB_COLUMNS = frozenset({"datasource_ids"})


def _restore_skill_value(column: str, value: Any) -> Any:
    if column in _RESTORE_JSONB_COLUMNS and value is not None:
        return value if isinstance(value, Jsonb) else Jsonb(value)
    return value


def restore_skills(
    cur: Any,
    backup: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    affected_ids: Sequence[int],
) -> None:
    """恢复原有 Skill，并删除本次发布新增的记录。"""

    affected = sorted({int(skill_id) for skill_id in affected_ids})
    original_skills = [dict(row) for row in backup.get("skills", ())]
    original_ids = {int(row["id"]) for row in original_skills}
    cur.execute(
        """
        DELETE FROM custom_prompt_user_preference
        WHERE tenant_id = %s
          AND custom_prompt_id = ANY(%s)
        """,
        (TENANT_ID, affected),
    )
    new_ids = sorted(set(affected).difference(original_ids))
    cur.execute(
        """
        DELETE FROM custom_prompt
        WHERE tenant_id = %s
          AND id = ANY(%s)
        """,
        (TENANT_ID, new_ids),
    )

    assignments = ", ".join(f"{column} = %s" for column in _RESTORE_SKILL_COLUMNS)
    for row in original_skills:
        cur.execute(
            f"UPDATE custom_prompt SET {assignments} WHERE id = %s AND tenant_id = %s",
            (
                *(
                    _restore_skill_value(column, row.get(column))
                    for column in _RESTORE_SKILL_COLUMNS
                ),
                int(row["id"]),
                TENANT_ID,
            ),
        )

    for row_value in backup.get("preferences", ()):
        row = dict(row_value)
        cur.execute(
            """
            INSERT INTO custom_prompt_user_preference (
                id, tenant_id, custom_prompt_id, user_id, enabled, update_time
            ) OVERRIDING SYSTEM VALUE
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET tenant_id = EXCLUDED.tenant_id,
                custom_prompt_id = EXCLUDED.custom_prompt_id,
                user_id = EXCLUDED.user_id,
                enabled = EXCLUDED.enabled,
                update_time = EXCLUDED.update_time
            """,
            (
                row.get("id"),
                row.get("tenant_id"),
                row.get("custom_prompt_id"),
                row.get("user_id"),
                row.get("enabled"),
                row.get("update_time"),
            ),
        )


def verify_embeddings(
    cur: Any,
    ids: Sequence[int],
    *,
    model: Any,
    signature_factory: Any | None = None,
) -> None:
    """验证每条 Skill 都有向量，且签名与当前完整定义一致。"""

    normalized_ids = sorted({int(skill_id) for skill_id in ids})
    cur.execute(
        """
        SELECT id, name, description, prompt, embedding, embedding_signature
        FROM custom_prompt
        WHERE tenant_id = %s
          AND id = ANY(%s)
          AND type = 'DATA_SKILL'
          AND specific_ds = TRUE
          AND datasource_ids = %s::jsonb
          AND active = TRUE
          AND visible = TRUE
          AND visibility_scope = 'ADMIN_PUBLIC'
        ORDER BY id
        """,
        (TENANT_ID, normalized_ids, Jsonb([DATASOURCE_ID])),
    )
    rows = cur.fetchall()
    if len(rows) != len(normalized_ids):
        raise RuntimeError(
            f"Data Skill embedding 记录不完整: 期望 {len(normalized_ids)}，实际 {len(rows)}"
        )
    if signature_factory is None:
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))
        from apps.chat.curd.custom_prompt_embedding import skill_definition_signature

        signature_factory = skill_definition_signature

    for skill_id, name, description, prompt, embedding, signature in rows:
        try:
            vector = json.loads(embedding) if isinstance(embedding, str) else embedding
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Data Skill {skill_id} embedding 不是有效 JSON") from exc
        if not isinstance(vector, list) or not vector:
            raise RuntimeError(f"Data Skill {skill_id} embedding 缺失")
        try:
            [float(item) for item in vector]
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Data Skill {skill_id} embedding 向量无效") from exc
        expected = signature_factory(
            name,
            description,
            prompt,
            model,
            len(vector),
        )
        if signature != expected:
            raise RuntimeError(f"Data Skill {skill_id} embedding_signature 不一致")


def _save_embeddings(ids: list[int]) -> int:
    export_postgres_compat_env(DB)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from sqlalchemy.orm import scoped_session, sessionmaker

    from apps.chat.curd.custom_prompt_embedding import save_custom_prompt_skill_embedding
    from common.core.db import engine

    session_maker = scoped_session(sessionmaker(bind=engine))
    return save_custom_prompt_skill_embedding(session_maker, ids, tenant_id=TENANT_ID)


def _embedding_model() -> Any:
    export_postgres_compat_env(DB)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from apps.ai_model.embedding import EmbeddingModelCache

    return EmbeddingModelCache.get_model()


def _load_recommended_dashboards(connection: Any) -> list[Any]:
    from xiuxian_dashboard_snapshot import load_recommended_dashboards

    return load_recommended_dashboards(connection)


def _acquire_publish_lock(cur: Any) -> None:
    cur.execute(
        "SELECT pg_advisory_lock(hashtextextended(%s, 0))",
        (PUBLISH_LOCK_KEY,),
    )


def _release_publish_lock(cur: Any) -> None:
    cur.execute(
        "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
        (PUBLISH_LOCK_KEY,),
    )


def main() -> None:
    now = dt.datetime.now()
    with psycopg.connect(**DB) as conn:
        ids: list[int] = []
        backup: dict[str, list[dict[str, Any]]] = {"skills": [], "preferences": []}
        with conn.cursor() as cur:
            _acquire_publish_lock(cur)
        try:
            dashboards = _load_recommended_dashboards(conn)
            skills = build_data_skills(dashboards)
            markers = [skill["prompt"].splitlines()[0].strip() for skill in skills]
            markers.append(LEGACY_PAYMENT_MARKER)
            with conn.cursor() as cur:
                backup = backup_existing_skills(cur, markers)
            with conn.cursor() as cur:
                ids = upsert_skills(cur, skills, now=now)
            conn.commit()
            saved = _save_embeddings(ids)
            if saved != len(ids):
                raise RuntimeError(
                    f"Data Skill embedding 保存不完整: 期望 {len(ids)}，实际 {saved}"
                )
            with conn.cursor() as cur:
                verify_embeddings(cur, ids, model=_embedding_model())
        except BaseException:
            conn.rollback()
            if ids:
                with conn.cursor() as cur:
                    restore_skills(cur, backup, affected_ids=ids)
                conn.commit()
            raise
        finally:
            with conn.cursor() as cur:
                _release_publish_lock(cur)
    print(f"修仙 Data Skills 已写入: {ids}; embeddings 已保存: {saved}")


if __name__ == "__main__":
    main()
