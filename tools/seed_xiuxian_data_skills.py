"""幂等写入修仙数据源的工作空间级 Data Skill。"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from core_system_db import core_system_db_config, export_postgres_compat_env
from psycopg.types.json import Jsonb
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
DATE_PARTITION_SKILL_DESCRIPTION = (
    "修仙 datasource_id=6 日期趋势口径："
    "最近15天补齐新增趋势、按日补零、固定非递归日期骨架；"
    "当前等级与活跃用户分布使用截至昨天的最新完整历史日。"
)

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
    "message":"修仙数据源禁止使用 MAX(dt) 扫描最大业务日期；请根据用户时间范围或默认最近 7 天直接生成 dt 分区边界。"
  },
  {
    "forbidden_sql_patterns":[
      "\\\\bWITH\\\\s+(?:RECURSIVE\\\\s+)?`?bounds`?\\\\s*(?:\\\\([^)]*\\\\)\\\\s*)?AS\\\\s*\\\\(",
      "\\\\b(?:CROSS\\\\s+JOIN|JOIN|FROM)\\\\s+`?bounds`?\\\\b"
    ],
    "message":"修仙数据源禁止使用 bounds CTE 关联事件或快照大表；请把动态日期表达式直接写入每个表别名自己的 dt 分区条件。"
  },
  {
    "match":["最近 28 个完整自然日","最近28个完整自然日"],
    "forbidden_sql_patterns":[
      "\\\\b(?:CURDATE|NOW|CURRENT_DATE|CURRENT_TIMESTAMP|LOCALTIME|LOCALTIMESTAMP|GETDATE|GETUTCDATE)\\\\s*(?:\\\\(\\\\s*\\\\))?"
    ],
    "message":"修仙最近 28 个完整自然日必须使用看板起止日期 token；日期骨架不得使用数据库当前日期函数。"
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
- 用户指定相对日期窗口时，根据用户要求的窗口长度动态计算边界，结束日期默认为最后一个完整业务日。
- “当前等级”“活跃用户分布”等当前快照分布问题必须使用截至昨天的最新完整历史日，不能因“当前”一词改查未完成当天的 `event_realtime`。
- 用户未指定日期窗口时，默认查询最近 7 个完整自然日。
- 可转存看板的非 `metric` 日期趋势必须使用 `{{dashboard_start_yyyymmdd}}` 和 `{{dashboard_end_yyyymmdd}}` 作为包含式整数边界，并返回完整 `"date_filter"`：`{"time_field":"dt","date_parameter_type":"yyyymmdd_number","date_expression":{"version":1,"mode":"preset","preset":"past_7_days"}}`。用户指定范围时，`date_expression` 必须按用户范围生成。
- 涉及日期字段或日期条件的 `metric` 图表必须返回 `date_filter` 并使用成对看板日期 token；不得使用 `YYYYMMDD` 字面量省略 `date_filter`。
- 日期骨架使用从 0 开始的偏移量时，必须先锚定 `{{dashboard_end_yyyymmdd}}`，再减 `day_offset`。
- 下面 SQL 展示非 `metric` 日期趋势的统一边界写法。
- 动态边界必须直接写入每个大表别名自己的 `WHERE` 或 `JOIN ON` 分区条件，禁止先生成单行 `bounds` CTE 后再通过 `JOIN` / `CROSS JOIN` 引用。

```sql
SELECT
    e.dt,
    COUNT(*) AS event_count
FROM `event` e
WHERE e.dt BETWEEN
    {{dashboard_start_yyyymmdd}}
    AND {{dashboard_end_yyyymmdd}}
GROUP BY e.dt
ORDER BY e.dt
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


DATE_SECTION_MARKER = "<!-- managed:xiuxian-sql-repair:date:start -->"
DATE_SECTION_END_MARKER = "<!-- managed:xiuxian-sql-repair:date:end -->"
SERVERPAYLOG_SECTION_MARKER = "<!-- managed:xiuxian-sql-repair:serverpaylog:start -->"
SERVERPAYLOG_SECTION_END_MARKER = "<!-- managed:xiuxian-sql-repair:serverpaylog:end -->"

DATE_SPINE_GUIDANCE = """## SQL 修复示例：固定 0-14 日日期骨架

需要补齐已配置为最近 15 个完整自然日的非 `metric` 趋势时，使用固定偏移的非递归日期骨架。SQL 的事实表过滤必须使用同一组看板日期 token，并返回对应的完整 `"date_filter"`：

`{"time_field":"dt","date_parameter_type":"yyyymmdd_number","date_expression":{"version":1,"mode":"preset","preset":"past_7_days"}}`

```sql
WITH day_offsets AS (
    SELECT 0 AS day_offset
    UNION ALL SELECT 1
    UNION ALL SELECT 2
    UNION ALL SELECT 3
    UNION ALL SELECT 4
    UNION ALL SELECT 5
    UNION ALL SELECT 6
    UNION ALL SELECT 7
    UNION ALL SELECT 8
    UNION ALL SELECT 9
    UNION ALL SELECT 10
    UNION ALL SELECT 11
    UNION ALL SELECT 12
    UNION ALL SELECT 13
    UNION ALL SELECT 14
), date_spine AS (
    SELECT CAST(
        DATE_FORMAT(
            DATE_SUB(
                STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d'),
                INTERVAL day_offset DAY
            ),
            '%Y%m%d'
        )
        AS SIGNED
    ) AS dt
    FROM day_offsets
)
SELECT dt FROM date_spine ORDER BY dt
```

读取 `event`、`user` 时仍必须在各自表别名上直接写 `dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}` 分区条件；日期骨架只负责补齐输出日期，不得代替业务表自身的分区过滤。
""".strip()

SERVERPAYLOG_REPAIR_EXAMPLES = """## SQL 修复示例

“等级段人均付费”和“最新完整数据日核心指标”如果需要随看板日期选择变化，必须使用 `dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}` 并返回完整 `date_filter`；不得使用固定 `YYYYMMDD` 字面量或数据库当前日期函数规避日期参数。

```sql
-- 修复示例：按渠道付费用户
SELECT
    DATE_FORMAT(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS dt,
    COALESCE(
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.mediaSource')), ''),
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.campaignName')), ''),
        '未知'
    ) AS `渠道`,
    COUNT(DISTINCT e.uid) AS `付费用户数`,
    ROUND(
        SUM(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')), '') AS DECIMAL(18, 4))),
        2
    ) AS `付费金额`
FROM `event` e
WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND e.prod = 110000047
  AND e.event = 'ServerPayLog'
GROUP BY e.dt, `渠道`
ORDER BY e.dt, `渠道`;
```

```sql
-- 修复示例：等级段人均付费
WITH user_level AS (
    SELECT
        u.uid,
        CASE
            WHEN CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.level')), '') AS DECIMAL(18, 4)) < 10 THEN '0-9'
            WHEN CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.level')), '') AS DECIMAL(18, 4)) < 20 THEN '10-19'
            WHEN CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.level')), '') AS DECIMAL(18, 4)) < 30 THEN '20-29'
            ELSE '30+'
        END AS level_band
    FROM `user` u
    WHERE u.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND u.prod = 110000047
), user_payment AS (
    SELECT e.uid,
           SUM(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')), '') AS DECIMAL(18, 4))) AS pay_amount
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'ServerPayLog'
    GROUP BY e.uid
)
SELECT ul.level_band AS `等级段`,
       ROUND(SUM(COALESCE(up.pay_amount, 0)) / NULLIF(COUNT(DISTINCT ul.uid), 0), 2) AS `人均付费金额`
FROM user_level ul
LEFT JOIN user_payment up ON up.uid = ul.uid
GROUP BY ul.level_band;
```

```sql
-- 修复示例：最新完整数据日核心指标
WITH active_metrics AS (
    SELECT COUNT(DISTINCT e.uid) AS dau
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'UserActive'
), register_metrics AS (
    SELECT COUNT(DISTINCT e.uid) AS new_users
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'UserRegister'
), payment_metrics AS (
    SELECT
        COUNT(DISTINCT e.uid) AS payers,
        ROUND(
            SUM(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')), '') AS DECIMAL(18, 4))),
            2
        ) AS pay_amount
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'ServerPayLog'
)
SELECT
    DATE_FORMAT(STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS dt,
    a.dau AS `DAU`,
    r.new_users AS `新增用户数`,
    p.payers AS `付费用户数`,
    p.pay_amount AS `付费金额`
FROM active_metrics a
CROSS JOIN register_metrics r
CROSS JOIN payment_metrics p;
```
""".strip()

def _managed_section(start_marker: str, end_marker: str, content: str) -> str:
    return f"{start_marker}\n{content.strip()}\n{end_marker}"


DATE_SPINE_MANAGED_SECTION = _managed_section(
    DATE_SECTION_MARKER,
    DATE_SECTION_END_MARKER,
    DATE_SPINE_GUIDANCE,
)
SERVERPAYLOG_MANAGED_SECTION = _managed_section(
    SERVERPAYLOG_SECTION_MARKER,
    SERVERPAYLOG_SECTION_END_MARKER,
    SERVERPAYLOG_REPAIR_EXAMPLES,
)


DATE_PARTITION_SKILL = {
    **_LEGACY_DATA_SKILLS[0],
    "description": DATE_PARTITION_SKILL_DESCRIPTION,
    "prompt": _LEGACY_DATA_SKILLS[0]["prompt"].rstrip()
    + "\n\n"
    + DATE_SPINE_MANAGED_SECTION,
}
LEGACY_PAYMENT_MARKER = (
    "<!-- data-skill-source:xiuxian:paybuyret-monetization-arppu -->"
)
SERVERPAYLOG_MARKER = (
    "<!-- data-skill-source:xiuxian:serverpaylog-monetization-arppu -->"
)
PAYER_PROMPT_EXCLUDED_VIEW_IDS = frozenset(
    {
        "f499305aa9b44a209cbe72cb68985a46",
        "304e66bb74254b9e88d8711ce33d94cc",
        "fc272fe6a3a74cda90a0564a98890fab",
    }
)
DATA_SKILLS: list[dict[str, str]] = [DATE_PARTITION_SKILL]

DISTINCT_UID_PATTERN = (
    r"COUNT\s*\(\s*DISTINCT\s+(?:`?\w+`?\s*\.\s*)?`?uid`?\s*\)"
)
DISTINCT_UID_PATTERN_JSON = DISTINCT_UID_PATTERN.replace("\\", "\\\\")

SERVERPAYLOG_VALIDATION = """<!-- data-skill-sql-validation:[
  {
    "match":["新增首日付费金额","首日付费金额","D0付费金额","注册日付费金额"],
    "required_sql_contains":["UserRegister","$.pay1","$.regdate","AS SIGNED"],
    "forbidden_sql_contains":["AS UNSIGNED","PayBuyRet","ed_money","paytotal"],
    "message":"修仙新增首日付费金额必须按 UserRegister 去重用户，读取注册日 user 快照的 pay.pay1；dt/regdate 为 YYYYMMDD，当前方言必须 CAST AS SIGNED，不能使用 UNSIGNED。"
  },
  {
    "match":["收入","流水","付费金额","ARPU","arpu","ARPPU","arppu"],
    "allow_when":["新增首日付费金额","首日付费金额","D0付费金额","注册日付费金额"],
    "required_sql_contains":["ServerPayLog","$.money"],
    "forbidden_sql_contains":["PayBuyRet","ed_money","paytotal"],
    "message":"修仙收入、ARPU 和 ARPPU 必须使用 ServerPayLog 的 personal.money 与去重 uid；PayBuyRet、ed_money 和 paytotal 不能作为真实收入来源。"
  },
  {
    "match":["付费用户","付费人数","ARPU","arpu","ARPPU","arppu"],
    "required_sql_contains":["ServerPayLog"],
    "required_sql_patterns":[
      "{DISTINCT_UID_PATTERN_JSON}"
    ],
    "forbidden_sql_contains":["PayBuyRet","ed_money","paytotal"],
    "message":"修仙付费用户数以及 ARPU/ARPPU 分母必须使用 ServerPayLog 并按 uid 去重；仅统计人数时不要求读取金额字段，PayBuyRet、ed_money 和 paytotal 不能作为付费用户来源。"
  }
] -->""".replace("{DISTINCT_UID_PATTERN_JSON}", DISTINCT_UID_PATTERN_JSON)


_REALTIME_CURRENT_DATE_EVENTS = {
    "f212cbcd03a15590a39519e874a1a6f4": "ServerPayLog",
    "5bb72c937f565b7295b3bf4d1b746496": "ServerPayLog",
    "2ca07023c33d514eaa07977425ee7f53": "UserRegister",
    "c3d6ca851f8150ba94d73a83ca18b438": "UserActive",
}
_REALTIME_CURRENT_DATE_VIEW_IDS = set(_REALTIME_CURRENT_DATE_EVENTS)
_DATABASE_CURRENT_DATE_PATTERN = re.compile(
    r"\b(?:CURDATE|NOW|CURRENT_DATE|CURRENT_TIMESTAMP|LOCALTIME|LOCALTIMESTAMP|"
    r"GETDATE|GETUTCDATE)\s*(?:\(\s*\))?",
    re.IGNORECASE,
)


def _normalize_dashboard_sql_current_date(view_id: str, sql: str) -> str:
    """把实时 metric 的当前日期依赖改为看板结束日期，未知用法拒绝发布。"""

    if view_id not in _REALTIME_CURRENT_DATE_VIEW_IDS:
        if _DATABASE_CURRENT_DATE_PATTERN.search(sql) is not None or "MAX(rt.dt)" in sql:
            raise ValueError(f"修仙看板 SQL 存在未分类的数据库当前日期函数: {view_id}")
        return sql

    dashboard_end_date = "STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d')"
    normalized = _DATABASE_CURRENT_DATE_PATTERN.sub(dashboard_end_date, sql)
    event_name = _REALTIME_CURRENT_DATE_EVENTS[view_id]
    legacy_latest_dt = (
        "STR_TO_DATE(CAST((SELECT MAX(rt.dt) FROM event_realtime rt "
        f"WHERE rt.prod = 110000047 AND rt.event = '{event_name}') AS CHAR), '%Y%m%d')"
    )
    return normalized.replace(legacy_latest_dt, dashboard_end_date)


def dashboard_sql_block(view_id: str, sql: str) -> str:
    """把一个推荐看板抽屉保存为可追溯 SQL 块。"""

    normalized_sql = _normalize_dashboard_sql_current_date(view_id, sql.strip())
    return f"<!-- dashboard-sql:{view_id} -->\n```sql\n{normalized_sql}\n```"


def _index_dashboard_drawers(dashboards: Sequence[Any]) -> dict[str, Any]:
    drawers: dict[str, Any] = {}
    for dashboard in dashboards:
        if int(dashboard.tenant_id) != TENANT_ID or int(dashboard.datasource) != DATASOURCE_ID:
            raise ValueError(f"看板 {dashboard.id} 不属于修仙工作空间 datasource 6")
        for drawer in dashboard.drawers:
            view_id = str(drawer.view_id)
            if view_id in drawers:
                raise ValueError(f"推荐看板抽屉 view id 重复：{view_id}")
            if not drawer.sql.strip():
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

## 新增首日付费口径
- “新增首日付费金额”是注册 cohort 快照指标，不使用 ServerPayLog 交易流水替代。
- 新增用户按 `UserRegister` 的 `dt + uid` 去重，并按 `prod + dt + uid` 连接注册日 `user` 快照。
- `event.dt` 与 `user.dt` 是数值型 `YYYYMMDD`；`userinfo.regdate` 是 JSON 字符串 `YYYYMMDD`，比较时使用 `CAST(... AS SIGNED)`，当前方言不支持 `UNSIGNED`。
- 只有 `CAST(JSON_UNQUOTE(JSON_EXTRACT(userinfo, '$.regdate')) AS SIGNED) = dt` 才属于注册日 cohort；金额读取注册日快照的 `pay.pay1`。
- 最近 30 个完整自然日的非 `metric` 趋势使用 `{{dashboard_start_yyyymmdd}}` 至 `{{dashboard_end_yyyymmdd}}` 过滤，并返回同范围的 `"date_filter"`；按天展示时补齐无数据日期并返回 0。
""".strip()


def _topic_prompt_view_ids(topic: Any) -> tuple[str, ...]:
    """返回应进入 Skill prompt 的抽屉；保留目录登记但排除冲突或重复 SQL。"""

    return tuple(
        view_id
        for view_id in topic.view_ids
        if not (
            topic.slug == "payer-penetration"
            and view_id in PAYER_PROMPT_EXCLUDED_VIEW_IDS
        )
    )


def build_data_skills(dashboards: Sequence[Any]) -> list[dict[str, str]]:
    """从完整推荐看板快照生成 1 条基础 Skill 和 12 条主题 Skill。"""

    validate_catalog()
    drawers = _index_dashboard_drawers(dashboards)
    skills = [dict(DATE_PARTITION_SKILL)]
    for topic in TOPICS:
        effective_topic = replace(
            topic,
            view_ids=_topic_prompt_view_ids(topic),
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
        if topic.slug == "serverpaylog-revenue":
            sections.append(SERVERPAYLOG_MANAGED_SECTION)
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
        """,
        (TENANT_ID, Jsonb([DATASOURCE_ID]), marker),
    )
    rows = cur.fetchall()
    if len(rows) > 1:
        raise RuntimeError(f"Data Skill marker 重复，拒绝发布: {marker}")
    return rows[0] if rows else None


def _upsert_skill(cur, *, skill: dict[str, str], now: dt.datetime) -> int:
    prompt = skill["prompt"].strip()
    marker = prompt.splitlines()[0].strip()
    lock_key = f"{TENANT_ID}:{DATASOURCE_ID}:{marker}"
    cur.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (lock_key,),
    )
    row = _find_skill_by_marker(cur, marker)
    if marker == SERVERPAYLOG_MARKER:
        legacy_row = _find_skill_by_marker(cur, LEGACY_PAYMENT_MARKER)
        if row is not None and legacy_row is not None:
            raise RuntimeError(
                "ServerPayLog current marker 与 legacy marker 同时存在，拒绝发布"
            )
        row = row or legacy_row
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
_PUBLISHED_STABLE_COLUMNS = tuple(
    column
    for column in ("id", *_RESTORE_SKILL_COLUMNS)
    if column not in {"embedding", "embedding_signature"}
)


class SkillRestoreConflictError(RuntimeError):
    """当前 Skill 已偏离本轮发布状态，恢复不能覆盖并发修改。"""


def _restore_skill_value(column: str, value: Any) -> Any:
    if column in _RESTORE_JSONB_COLUMNS and value is not None:
        return value if isinstance(value, Jsonb) else Jsonb(value)
    return value


def _stable_skill_state(row: Mapping[str, Any]) -> dict[str, Any]:
    return {column: row.get(column) for column in _PUBLISHED_STABLE_COLUMNS}


def load_skill_states_by_ids(
    cur: Any,
    skill_ids: Sequence[int],
    *,
    for_update: bool = False,
) -> dict[int, dict[str, Any]]:
    """按 ID 读取 Skill 行；恢复时锁行以保证比较与写入原子。"""

    normalized_ids = sorted({int(skill_id) for skill_id in skill_ids})
    if not normalized_ids:
        return {}
    suffix = " FOR UPDATE" if for_update else ""
    cur.execute(
        f"""
        SELECT to_jsonb(cp)
        FROM custom_prompt cp
        WHERE cp.id = ANY(%s)
          AND cp.tenant_id = %s
        ORDER BY cp.id{suffix}
        """,
        (normalized_ids, TENANT_ID),
    )
    return {
        int(row[0]["id"]): dict(row[0])
        for row in cur.fetchall()
    }


def restore_skills(
    cur: Any,
    backup: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    affected_ids: Sequence[int],
    expected_states: Mapping[int, Mapping[str, Any]],
) -> None:
    """仅在仍匹配本轮发布状态时恢复，且不触碰既有 Skill 偏好。"""

    affected = sorted({int(skill_id) for skill_id in affected_ids})
    original_skills = [dict(row) for row in backup.get("skills", ())]
    original_by_id = {int(row["id"]): row for row in original_skills}
    original_ids = set(original_by_id)
    normalized_expected = {
        int(skill_id): dict(state)
        for skill_id, state in expected_states.items()
        if int(skill_id) in affected
    }
    if set(normalized_expected) != set(affected):
        missing = sorted(set(affected).difference(normalized_expected))
        raise SkillRestoreConflictError(
            f"缺少本轮发布期望态，拒绝恢复 Skill: {missing}"
        )
    current_states = load_skill_states_by_ids(cur, affected, for_update=True)
    restore_ids: list[int] = []
    conflicts: list[int] = []
    for skill_id in affected:
        current = current_states.get(skill_id)
        expected = normalized_expected[skill_id]
        original = original_by_id.get(skill_id)
        if current is not None and _stable_skill_state(
            current
        ) == _stable_skill_state(expected):
            restore_ids.append(skill_id)
        elif original is not None and current is not None and _stable_skill_state(
            current
        ) == _stable_skill_state(original):
            continue
        elif original is None and current is None:
            continue
        else:
            conflicts.append(skill_id)
    if conflicts:
        raise SkillRestoreConflictError(
            f"Skill 恢复冲突，已保留并发修改: {conflicts}"
        )

    new_ids = sorted(set(restore_ids).difference(original_ids))
    if new_ids:
        cur.execute(
            """
            DELETE FROM custom_prompt_user_preference
            WHERE tenant_id = %s
              AND custom_prompt_id = ANY(%s)
            """,
            (TENANT_ID, new_ids),
        )
        cur.execute(
            """
            DELETE FROM custom_prompt
            WHERE tenant_id = %s
              AND id = ANY(%s)
            """,
            (TENANT_ID, new_ids),
        )
        if cur.rowcount != len(new_ids):
            raise SkillRestoreConflictError(
                f"新增 Skill 删除数量变化，拒绝提交恢复: {new_ids}"
            )

    assignments = ", ".join(f"{column} = %s" for column in _RESTORE_SKILL_COLUMNS)
    for row in original_skills:
        if int(row["id"]) not in restore_ids:
            continue
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
        if cur.rowcount != 1:
            raise SkillRestoreConflictError(
                f"既有 Skill 恢复数量变化，拒绝提交恢复: {row['id']}"
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

    from apps.chat.curd.custom_prompt_embedding import (
        save_custom_prompt_skill_embedding,
    )
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


def main(argv: Sequence[str] | None = None) -> int:
    """兼容旧脚本入口，但所有写入统一交给正式发布器。"""

    from publish_xiuxian_dashboard_data_skills import main as publisher_main

    cli_args = list(sys.argv[1:] if argv is None else argv)
    if any(arg == "--mode" or arg.startswith("--mode=") for arg in cli_args):
        raise SystemExit("seed 入口固定使用 apply，禁止传入 --mode")
    return publisher_main([*cli_args, "--mode", "apply"])


if __name__ == "__main__":
    raise SystemExit(main())
