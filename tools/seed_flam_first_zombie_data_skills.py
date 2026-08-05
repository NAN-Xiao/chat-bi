# -*- coding: utf-8 -*-
"""Seed flam / first_zombie datasource-scoped Data Skills."""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from core_system_db import core_system_db_config, export_postgres_compat_env
from flam_first_zombie_active_dashboard_sql import sql_blocks_markdown as active_sql_blocks_markdown
from flam_first_zombie_core_dashboard_sql import sql_blocks_markdown as core_sql_blocks_markdown
from flam_first_zombie_dashboard_sql import sql_blocks_markdown
from flam_first_zombie_dashboard_skill_overrides import apply_dashboard_skill_overrides
from flam_first_zombie_remaining_dashboard_sql import sql_blocks_markdown as remaining_sql_blocks_markdown


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"

DB = core_system_db_config()

TENANT_ID = 7477202383789887488
DATASOURCE_ID = 3

NEW_USER_RETENTION_VIEW_IDS = (
    "22f0761ab59449189707aca09323810e",
    "29055a5fcfd74169a12373b3f0d9a412",
    "ba48ea6e38e748ee9990b59324459b64",
    "b64cc15b6dde4833ac1f8830038f673f",
    "cdf17cb957bb40499914a3ef790a79ef",
    "1f099cfb059a469ebedb5d040ff84de2",
    "4d8bfb37698843aab0031c74dbbf8489",
    "db1d8ef987724e68a1e0c9fe8b073ed1",
    "f0d759307a304043883a23499a281b97",
    "f39bac6b01784ca5b92c60ffe4348756",
    "63e03c7e2ad34ad58321892998497a85",
)

PAYMENT_LTV_VIEW_IDS = (
    "f784452553f1426ea5097b092deb818a",
    "6391d385e5084c0f86351ae088d3c336",
    "6fce0cfb227b47828b41fd3c5cc736d5",
    "f75122a83c84441381fe77a551f69a28",
    "20a42bea9bcf4bc5b1bddfff187a874d",
    "01b402cb5b5f4c95bc457cf505a2ecc7",
    "bb9fbc7502af455cbea246821e180c72",
    "24a51da63ed84379adbec45927500dce",
    "8b1c7fa28da041afaf91d4a834a9a84a",
    "89d495c3733a441799b032cd7407df01",
    "65f52e391c5a430b8c8d2575195082f4",
    "b9043b8bca964589949a11c198154af4",
    "e300602c05804ecc93123625f9bafa3a",
    "eabf5e30333342ed8bf47dfcd0898278",
)

CURRENT_SNAPSHOT_VIEW_IDS = (
    "de17a15e36b14e79826a86637c576514",
)

CHANNEL_ACQUISITION_VIEW_IDS = (
    "531012d01f104a509da2d1926692ee1d",
)

PAY_DISTRIBUTION_VIEW_IDS = (
    "f6ca362eb4274830b3298b0227a8ab88",
    "4045ede9004f48de9fb8b8aed5f79287",
    "fdb8f135e2644bcb80b7634882809f7e",
)

ACTIVITY_VIEW_IDS = (
    "c794f6521d8b44d39f78eabdf109896b",
    "6266951d0e1842e2b259121ab06f7a61",
    "13d554014c854e508ff016d93a6f3899",
    "161fd0d2996a49a29e82606e6db7d95b",
    "9684a569ed034fb0b8a106a9817effaa",
    "095b1cf41cd64844b1f78f07ceccb7bf",
)

ECONOMY_VIEW_IDS = (
    "4cc60cadf26e4b2f945c672f2648d205",
    "df837cb59810483f84fb0e7cd420646a",
    "fda6854e188c44c4b35e75c9af6d9854",
)

GIFT_RETENTION_VIEW_IDS = (
    "15da41b65ee64aba854e2de701a728bc",
    "f113ac14e8994d12814452040b702424",
)

EXPEDITION_VIEW_IDS = (
    "9d4add7a8be048ea9c7beb62a43e50cc",
    "9325211a9f594376bf818cec639aa103",
    "440303dfdf39408ba86ffb222f3334f2",
    "0b849c96c0a3480c9e940b92995d5e3e",
    "f2be189bf85f4181bc7191cd5138561f",
    "e02bdbafdd364d3cba9f991f94896c86",
    "59a8dfd8d6e341988edfbf1666872aae",
    "848927b0833443d39a93797c3507368e",
    "344c936b561f44f6bc29cc2663f3f651",
    "61c21b5974844638a3d7370971de58c9",
)

HERO_GROWTH_VIEW_IDS = (
    "e13ce279fb3d432da20336b1f93eaf4f",
    "78ddbc37336844b1852ddeaef72f7ecc",
)

CITY_BUILD_VIEW_IDS = (
    "4608fb0831cd4845ba881678fb778b2f",
    "dbc481fea69d4314af8535600fa4f8c8",
    "48f02edf9a364e1082cd67008cd60b2b",
    "8f6dcec8cfdb40b4a7c02139b7d35f56",
    "1b9eb5aac8224dee9ccdf839d5a3988c",
    "82f560ee39f2409485e7270d2c9db26c",
    "3a46d6c112284ee98373dbe53baa6290",
    "697c622479fb4ab0b768e02c360e6c6f",
    "725f639c5ed24cc6a13d6e1fa2430c8a",
    "1e41ffdca6b041a6abea363fcb1b8cd2",
    "1c5f7aa5ae6f47ecb3dcfab37ee5e34e",
    "a547eb9c1a1a4f4eba00191abbd9ac62",
)

STALE_SKILL_MARKERS = (
    "<!-- data-skill-source:flam:first-zombie:dashboard-statistics -->",
    "<!-- data-skill-source:flam:first-zombie:revenue-voice-root-cause -->",
)

DATA_SKILLS: list[dict[str, str]] = [
    {
        "name": "flam 实时数据时区与日期口径",
        "description": (
            "flam / first_zombie 今天实时付费趋势、按小时付费、实时日期、"
            "dt 分区与实时看板 SQL 生成规则。"
        ),
        "prompt": """<!-- dashboard-refresh-policy:{"auto_refresh":true,"snapshot_max_age_hours":3} -->
<!-- data-skill-source:flam:first-zombie:timezone-realtime -->
# flam 实时数据时区与日期口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于 `event`、`user` 两张表中的日期过滤、实时看板、实时付费、在线人数、小时趋势等问题。

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
- 实时小时维度应基于事件业务时间取小时：
  `DATE_FORMAT(DATE_FORMAT(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR), '%Y-%m-%d %H:00:00'), '%H:00')`
- flam ADS/MySQL 返回中文 SELECT 别名时可能变成 `??`，持久看板 SQL 字段必须使用 ASCII 别名：
  `time_label`、`hour_label`、`online_users`、`pay_count`、`cumulative_pay_count`；图表配置用中文 `name` 展示、英文 `value` 绑定字段。
- ADS 对动态 `MAX(dt)`、严格业务日 CTE 和跨分区时间函数过滤容易超时；持久实时看板用 `tools/repair_flam_first_zombie_realtime_dashboard.py` 先探测最近可用业务日，再把 SQL 固化为常量 `dt`/业务日期窗口。
- 实时付费优先展示业务今天；如果今天没有付费事件，回退到最近有付费事件的业务日。回退是为了展示“最近可用实时趋势”，不得虚构今天数据。
- 实时真实交易次数使用 `event='ServerPayLog'` 的订单行；支付流程事件只能作为独立流程事件量，不能命名为真实充值次数。
- 累计真实交易次数应先按业务小时聚合，再对小时做累计求和。
- 在线人数的业务字段是 `CCU.personal.ed_ccu`。如果当前数据行的 `personal` 没有 `ed_ccu`，应说明数据侧缺少当前在线人数值，不要把 CCU 事件条数或空 `uid` 去重数当成真实在线人数。

## 禁止事项
- 不要在 flam 实时问题里直接用 `CURDATE()` / `NOW()` 作为业务日口径。
- 实时查询应遵循本 Data Skill 的日期规则。
- 不要把该日期规则套用到其他数据源。

## 实时看板持久 SQL
以下 SQL 是本 Data Skill 对 `实时看板` 已保存组件的模板配置；修复脚本会基于当前数据把付费/在线日期固化后写入看板，避免打开看板时动态探测超时。

<!-- dashboard-sql:e3fe7e4819e64b71b76d9329a3023359 -->
```sql
WITH latest_dt AS (
    SELECT e.dt
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), INTERVAL 15 DAY), '%Y%m%d') AS SIGNED)
                   AND CAST(DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y%m%d') AS SIGNED)
      AND e.prod = 110000038
      AND e.event = 'CCU'
      AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_ccu')), '') IS NOT NULL
    GROUP BY e.dt
    ORDER BY e.dt DESC
    LIMIT 1
)
SELECT DATE_FORMAT(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR), '%H:00') AS time_label,
       MAX(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_ccu')), '') AS DECIMAL(18,4))) AS online_users
FROM `event` e
JOIN latest_dt ld ON e.dt = ld.dt
WHERE e.prod = 110000038
  AND e.event = 'CCU'
  AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_ccu')), '') IS NOT NULL
GROUP BY HOUR(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR)), time_label
ORDER BY HOUR(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR))
LIMIT 24
```

<!-- dashboard-sql:4fc570b4be7d406c9f648d9088f760bb -->
```sql
WITH latest_dt AS (
    SELECT e.dt
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), INTERVAL 15 DAY), '%Y%m%d') AS SIGNED)
                   AND CAST(DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y%m%d') AS SIGNED)
      AND e.prod = 110000038
      AND e.event = 'ServerPayLog'
    GROUP BY e.dt
    ORDER BY e.dt DESC
    LIMIT 1
)
SELECT DATE_FORMAT(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR), '%H:00') AS hour_label,
       COUNT(*) AS pay_count
FROM `event` e
JOIN latest_dt ld ON e.dt = ld.dt
WHERE e.prod = 110000038
  AND e.event = 'ServerPayLog'
GROUP BY HOUR(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR)), hour_label
ORDER BY HOUR(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR))
LIMIT 24
```

<!-- dashboard-sql:2149b7abbc6c4cd7ad6f52379e69b15a -->
```sql
WITH latest_dt AS (
    SELECT e.dt
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), INTERVAL 15 DAY), '%Y%m%d') AS SIGNED)
                   AND CAST(DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y%m%d') AS SIGNED)
      AND e.prod = 110000038
      AND e.event = 'ServerPayLog'
    GROUP BY e.dt
    ORDER BY e.dt DESC
    LIMIT 1
),
hourly AS (
    SELECT HOUR(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR)) AS hour_index,
           DATE_FORMAT(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR), '%H:00') AS hour_label,
           COUNT(*) AS pay_count
    FROM `event` e
    JOIN latest_dt ld ON e.dt = ld.dt
    WHERE e.prod = 110000038
      AND e.event = 'ServerPayLog'
    GROUP BY hour_index, hour_label
)
SELECT hour_label,
       SUM(pay_count) OVER (ORDER BY hour_index) AS cumulative_pay_count
FROM hourly
ORDER BY hour_index
LIMIT 24
```""",
    },
    {
        "name": "flam 新增与留存 cohort 口径",
        "description": "flam / first_zombie 新增用户、渠道/系统注册归因、D1/D3/D7 留存和新增看板 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:new-user-retention -->
# flam 新增与留存 cohort 口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于新增用户数、渠道/系统新增、新增用户 D1/D3/D7 留存、渠道留存和 `新增看板`/`渠道分析`/`投放看板`中新增留存类组件。

## 表与字段
- 今天、当天、今日、实时、当前小时、当前分钟、当前整点统计新增用户时，必须使用 `event_realtime` 表的注册事件 `UserRegister`；不得静默改查 `event`。
- 完整历史日和留存 cohort 使用 `event` 表的注册事件 `UserRegister`；已与 `user.userinfo.regdate = user.dt` 的注册日 cohort 按日核对一致，但事件表扫描更轻。
- 需要读取 `pay.pay1/pay7`、当前等级等快照字段时，再按 `uid + 注册日 dt` 回连 `user` 用户日表。
- `dt` 是业务日期分区，格式为 `YYYYMMDD` 数字。
- 注册日期取 `JSON_UNQUOTE(JSON_EXTRACT(userinfo, '$.regdate'))`，格式为 `YYYYMMDD` 字符串。
- 持久看板的 D1/D3/D7 留存分子优先使用注册 cohort 在精确后续日期的 `UserActive` 活跃去重；只有用户明确要求 `remain` 埋点标记时才读取后续精确生命周期日快照的 `remain.remain1/remain3/remain7`。
- 按渠道、系统拆分时，渠道/系统取注册事件行的 `adinfo` / `deviceinfo`，不要用后续活跃日覆盖新增归因。

## SQL 口径
- 新增用户分母：目标表中 `event='UserRegister'` 的注册日 cohort，按 `uid` 去重；未完成当天使用 `event_realtime`，完整历史日使用 `event`。新增趋势、渠道新增、系统新增不要为了取注册日去扫描 `user` 快照 JSON。
- D1 留存分子：先固定注册事件 cohort，再在该 cohort 的精确次日 `UserActive` 中查同一 `uid`；不能只读取注册当天，也不要跨多日 `MAX(remain1)`。
- 默认只展示已成熟 cohort：近月看板以当前日前一完整分区为成熟截止，D1 默认窗口排除最近 1 天，D7 默认窗口排除最近 7 天，避免把未成熟 cohort 当 0%。
- 用户问“最近 N 天新增用户留存/滞留情况”且未指定 D3/D7 时，默认按 D1 精确日留存理解；cohort 窗口应取最近 N 个已成熟注册日。例如系统日期为 2026-06-30 时，“最近三天新增用户留存”应统计注册日 2026-06-26、2026-06-27、2026-06-28，对应活跃观察日 2026-06-27、2026-06-28、2026-06-29；不要把 2026-06-29 注册 cohort 纳入 D1 留存分母。
- flam ADS 对 `MAX(user.dt)` / `MAX(event.dt)` 这类大视图聚合较慢；非 `metric` 历史时序图必须以 `{{dashboard_start_yyyymmdd}}` 至 `{{dashboard_end_yyyymmdd}}` 限定完整 `dt` 分区窗口，并显式过滤 `prod = 110000038`。
- 非 `metric` 历史时序图的 SQL 必须返回完整 `date_filter`：`{{"time_field":"dt","date_parameter_type":"yyyymmdd_number","date_expression":{{"version":1,"mode":"preset","preset":"past_7_days"}}}}`；SQL 的日期条件使用 `{{dashboard_start_yyyymmdd}}` 与 `{{dashboard_end_yyyymmdd}}`。用户指定范围时，`date_expression` 必须按用户范围生成。`metric` 图表不得返回 `date_filter` 或看板日期 token。

## 推荐输出
- 默认优先使用中文 SQL 输出别名：`日期`、`新增用户数`、`次日留存用户数`、`次日留存率`；图表配置的 `value` 必须与 SQL 返回字段完全一致。
- 如果执行后 flam ADS 把中文别名返回为 `??` / `????`，或当前问题需要走已验证的持久看板兼容写法，则可退回稳定英文别名 `cohort_date`, `new_users`, `d1_retained_users`, `d1_retention_pct`，但图表配置必须保留中文展示名：`{{"value":"cohort_date","name":"日期"}}`、`{{"value":"d1_retention_pct","name":"次日留存率"}}` 等。
- 留存趋势图使用折线图，x 轴为注册日期，主 y 轴优先只展示 `次日留存率` / `d1_retention_pct`；`新增用户数` 和 `次日留存用户数` 是辅助上下文，用户没有要求同时展示规模时不要把人数和百分比混在同一折线 y 轴里。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对已保存看板中新增、渠道新增、系统新增和新增留存类组件的落地配置。

{sql_blocks_markdown(NEW_USER_RETENTION_VIEW_IDS)}
""",
    },
    {
        "name": "flam 历史看板日期窗口口径",
        "description": "flam / first_zombie 离线历史看板的日期窗口、ADS 性能和成熟 cohort 规则。",
        "prompt": """<!-- data-skill-source:flam:first-zombie:historical-date-window -->
# flam 历史看板日期窗口口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于 `核心看板`、`新增看板`、`活跃看板`、`付费概览`、`渠道分析`、`投放看板` 等离线历史看板的日期窗口选择。

## 日期窗口
- flam 的 ADS 视图对 `MAX(dt)`、`DISTINCT dt` 和先取最大分区的 CTE 计划较重；历史活跃、DAU/WAU/MAU、ARPU/ARPPU 这类近月趋势必须用 `{{dashboard_start_yyyymmdd}}` 至 `{{dashboard_end_yyyymmdd}}` 限定完整 `dt` 分区窗口，并显式过滤 `prod = 110000038` 和目标事件。
- 非 `metric` 历史时序图必须返回 `date_filter`：`{"time_field":"dt","date_parameter_type":"yyyymmdd_number","date_expression":{"version":1,"mode":"preset","preset":"past_7_days"}}`；用户指定范围时按用户范围生成 `date_expression`。`metric` 图表必须省略 `date_filter` 及全部看板日期 token。
- DAU/活跃趋势在未指定日期范围时，遵循平台通用 Data Skill 的过去 7 个完整自然日默认范围；使用当前日前一完整分区作为结束边界，避免额外扫描事件视图获取最大分区。
- 指标需要成熟 cohort 或最新快照语义时，使用当前日前一完整分区或排除对应成熟窗口，例如新增留存、7 日 LTV、当前等级分布；这类问题不能把未成熟 cohort 当 0。
- 需要计算 D1/D3/D7 留存或 7 日 LTV 时，只展示成熟 cohort：D1 默认排除最近 1 天，D7 默认排除最近 7 天。
- 实时看板继续遵循 `flam 实时数据时区与日期口径` Data Skill 的实时日期规则；不要把实时规则套到历史离线看板。

## 禁止事项
- 不要为了近月活跃趋势额外构造 `MAX(event.dt)` / `SELECT DISTINCT dt` 分区 CTE；这会显著拖慢 ADS 查询。
- 不要把未成熟 cohort 的留存、LTV 直接展示为 0。
- 不要在这个 Data Skill 中沉淀具体业务指标 SQL；具体指标 SQL 归属对应的新增留存、付费 LTV、当前快照等技能。
""",
    },
    {
        "name": "flam 活跃用户口径",
        "description": "flam / first_zombie DAU/WAU/MAU、活跃生命周期、渠道/系统活跃和周登录天数 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:active-users -->
# flam 活跃用户口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于 `活跃看板`、核心 DAU、渠道活跃、DAU/WAU/MAU、活跃生命周期构成和周登录天数分布。

## 活跃用户
- DAU/WAU/MAU 使用 `event` 表的归一化活跃事件 `UserActive` 计算 `uid` 去重，并显式过滤 `prod = 110000038` 以帮助 ADS 分区/条件下推。
- 按渠道/系统拆分活跃时，使用活跃事件行上的 `adinfo` / `deviceinfo`。
- 历史活跃趋势在未指定日期范围时，遵循平台通用 Data Skill 的过去 7 个完整自然日默认范围；SQL 必须以 `{{dashboard_start_yyyymmdd}}` 至 `{{dashboard_end_yyyymmdd}}` 限定 `dt` 分区窗口，并返回同范围的 `date_filter`，不要为了取最大分区对大视图做 `MAX(dt)` / `DISTINCT dt` 聚合。
- DAU 在未指定日期范围时，遵循平台通用 Data Skill 的过去 7 个完整自然日默认范围；WAU/周登录天数按自然周聚合，观察窗口应扩展到完整周；MAU 按自然月聚合，观察窗口应扩展到完整月。
- 活跃生命周期先用 `UserActive` 确定当日活跃 `uid`，再关联同日 `user` 快照读取 `lastinfo.regnday` 分层：`<=1` 新增期，`<=7` 成长期，`<=30` 稳定期，其余成熟期。

## 禁止事项
- 不要把 `event` 全表任意事件去重当 DAU。
- 不要把多个登录/进入游戏事件集合当作 flam 历史 DAU 的默认口径；`UserActive` 已经是该数据源的活跃归一化事件，重复使用登录事件集合会显著拖慢查询。
- 不要把 `user` 日表里存在的用户直接当活跃用户，除非问题明确询问“用户日快照覆盖人数”。
- 不要把边界周/月的不完整 30 天窗口当完整 WAU/MAU。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对 `活跃看板` 已保存组件的落地配置。

{active_sql_blocks_markdown()}
""",
    },
    {
        "name": "flam 付费与 LTV 口径",
        "description": "flam / first_zombie 日付费、累计付费、ARPU/ARPPU、付费率、首付、近 7 日累充和新增 cohort LTV SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:payment-ltv -->
<!-- data-skill-sql-validation:[
{{
  "match":["ltv","LTV","新增用户平均付费","新增人均付费","新增用户付费","新增付费","首日付费","首日LTV","首日 LTV","1日LTV","1 日 LTV","次日LTV","次日 LTV","2日LTV","2 日 LTV","3日LTV","3 日 LTV","7日LTV","7 日 LTV","14日LTV","14 日 LTV","30日LTV","30 日 LTV"],
  "forbidden_sql_patterns":[
    "DATE_ADD\\\\s*\\\\([\\\\s\\\\S]{{0,240}}INTERVAL\\\\s+1\\\\s+DAY[\\\\s\\\\S]{{0,160}}d1_dt",
    "DATE_ADD\\\\s*\\\\([\\\\s\\\\S]{{0,240}}INTERVAL\\\\s+2\\\\s+DAY[\\\\s\\\\S]{{0,160}}d2_dt",
    "DATE_ADD\\\\s*\\\\([\\\\s\\\\S]{{0,240}}INTERVAL\\\\s+3\\\\s+DAY[\\\\s\\\\S]{{0,160}}d3_dt",
    "DATE_ADD\\\\s*\\\\([\\\\s\\\\S]{{0,240}}INTERVAL\\\\s+7\\\\s+DAY[\\\\s\\\\S]{{0,160}}d7_dt",
    "DATE_ADD\\\\s*\\\\([\\\\s\\\\S]{{0,240}}INTERVAL\\\\s+14\\\\s+DAY[\\\\s\\\\S]{{0,160}}d14_dt",
    "DATE_ADD\\\\s*\\\\([\\\\s\\\\S]{{0,240}}INTERVAL\\\\s+30\\\\s+DAY[\\\\s\\\\S]{{0,160}}d30_dt"
  ],
  "message":"flam 新增 cohort LTV 的 pay 窗口字段必须按快照成熟日读取：pay1=首日/1日(+0)，pay2=次日/2日(+1)，pay3=+2，pay7=+6，pay14=+13，pay30=+29。不要把字段名数字直接写成 DATE_ADD 的 +1/+2/+3/+7/+14/+30。"
}},
{{
  "match":["ltv","LTV","新增用户平均付费","新增人均付费","新增用户付费","新增付费","首日付费","首日LTV","首日 LTV","1日LTV","1 日 LTV","次日LTV","次日 LTV","2日LTV","2 日 LTV","3日LTV","3 日 LTV","7日LTV","7 日 LTV","14日LTV","14 日 LTV","30日LTV","30 日 LTV"],
  "forbidden_sql_patterns":[
    "LEFT\\\\s+JOIN\\\\s+(?:`?first_zombie`?\\\\s*\\\\.\\\\s*)?`?user`?\\\\s+(?:AS\\\\s+)?`?s`?\\\\s+ON\\\\s+(?!(?:(?!\\\\b(?:WHERE|GROUP\\\\s+BY|ORDER\\\\s+BY|LIMIT|LEFT\\\\s+JOIN|RIGHT\\\\s+JOIN|INNER\\\\s+JOIN|JOIN)\\\\b)[\\\\s\\\\S])*`?s`?\\\\s*\\\\.\\\\s*`?dt`?)(?:(?!\\\\b(?:WHERE|GROUP\\\\s+BY|ORDER\\\\s+BY|LIMIT|LEFT\\\\s+JOIN|RIGHT\\\\s+JOIN|INNER\\\\s+JOIN|JOIN)\\\\b)[\\\\s\\\\S])*`?s`?\\\\s*\\\\.\\\\s*`?uid`?\\\\s*=\\\\s*`?c`?\\\\s*\\\\.\\\\s*`?uid`?"
  ],
  "message":"flam 新增 cohort LTV 回连 user 快照时必须在 JOIN 条件中限定成熟快照分区，例如 `s.dt IN (c.d1_dt, c.d2_dt, c.d3_dt, c.d7_dt)`；不能只按 uid/prod 连接全量用户日快照。"
}},
{{
  "name":"snapshot_partition_bounds_required",
  "match":["ltv","LTV","新增用户平均付费","新增人均付费","新增用户付费","新增付费","首日付费","首日LTV","首日 LTV","1日LTV","1 日 LTV","次日LTV","次日 LTV","2日LTV","2 日 LTV","3日LTV","3 日 LTV","7日LTV","7 日 LTV","14日LTV","14 日 LTV","30日LTV","30 日 LTV"],
  "forbidden_sql_patterns":[
    "LEFT\\\\s+JOIN\\\\s+(?:`?first_zombie`?\\\\s*\\\\.\\\\s*)?`?user`?\\\\s+(?:AS\\\\s+)?`?s`?\\\\s+ON\\\\s+(?!(?:(?!\\\\b(?:WHERE|GROUP\\\\s+BY|ORDER\\\\s+BY|LIMIT|LEFT\\\\s+JOIN|RIGHT\\\\s+JOIN|INNER\\\\s+JOIN|JOIN)\\\\b)[\\\\s\\\\S])*`?s`?\\\\s*\\\\.\\\\s*`?dt`?\\\\s+BETWEEN)(?:(?!\\\\b(?:WHERE|GROUP\\\\s+BY|ORDER\\\\s+BY|LIMIT|LEFT\\\\s+JOIN|RIGHT\\\\s+JOIN|INNER\\\\s+JOIN|JOIN)\\\\b)[\\\\s\\\\S])*`?s`?\\\\s*\\\\.\\\\s*`?dt`?\\\\s+IN\\\\s*\\\\("
  ],
  "message":"flam 新增 cohort LTV 回连 user 快照时，除了 `s.dt IN (...)` 精确成熟日，还必须为回连快照别名 `s` 增加固定分区边界。若在 `pay_windows` 等后续 CTE 中使用 `b.snapshot_start_dt` / `b.snapshot_end_dt`，必须在该 CTE 自身的 FROM 中先写 `FROM cohort c JOIN bounds b ON 1 = 1`；CTE 之间不会继承表别名作用域。随后才写 `LEFT JOIN user s ON s.uid = c.uid AND s.prod = 110000038 AND s.dt BETWEEN b.snapshot_start_dt AND b.snapshot_end_dt`，避免 ADS/MySQL 对 user 快照做大范围动态扫描。"
}},
{{
  "match":["次日LTV","次日 LTV"],
  "forbidden_sql_all_contains":[["pay1","次日"]],
  "message":"flam 次日 LTV 是注册第 2 个自然日累计窗口，应读取 pay.pay2 和 cohort_dt + 1 快照；pay.pay1 只能用于首日/1日 LTV。"
}}
] -->
# flam 付费与 LTV 口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于付费概览、ARPU/ARPPU、日充值次数/人数、新增首日付费、新增用户平均付费、累计付费、近 7 日累充、渠道付费、等级段付费和新增 cohort LTV。

## 付费与累计
- `user.pay.paytotal` 是用户截至该 `dt` 的累计付费快照，可用于累计付费金额、累计付费用户、当前等级段累计人均付费等快照指标。
- 历史日充值金额直接汇总 `event='ServerPayLog'` 的 `personal.money`；不要按日汇总 `paytotal`，也不要用支付流程事件筛人后再推导交易金额。
- 历史日付费、ARPU/ARPPU、付费概览和渠道付费 SQL 以 `ServerPayLog.personal.money` 为分子，按 `dt` 分区聚合；非 `metric` 时间图必须以 `{{{{dashboard_start_yyyymmdd}}}}` 至 `{{{{dashboard_end_yyyymmdd}}}}` 限定窗口并返回同范围的 `date_filter`，不扫描大视图取得最大分区。
- 用户明确查询今天、今日、当天的实时付费非 `metric` 时间图时，使用 `event_realtime`，SQL 的 `dt` 条件保存成对的 `{{{{dashboard_start_yyyymmdd}}}}` 和 `{{{{dashboard_end_yyyymmdd}}}}`，并返回 `{{"time_field":"dt","date_parameter_type":"yyyymmdd_number","date_expression":{{"version":1,"mode":"preset","preset":"today"}}}}`；不得把实际 `yyyyMMdd` 固化到可保存、复制的图表 SQL 中。
- 只有结果需要按渠道/系统等维度拆分时才解析交易事件行的 `adinfo` / `deviceinfo` JSON；国家拆分统一使用活跃事件和 `ServerPayLog` 事件各自行的 `userinfo.country`，不使用 `currentinfo.country`。
- 日充值次数使用 `ServerPayLog.personal.orderId` 去重；日充值用户数使用同日 `ServerPayLog.uid` 去重。
- 日新增充值用户数使用 `user.pay.firstpaytime` 转换的首付业务日；不得使用分析窗口内最小付费事件日期。
- `firstpaytime` 为毫秒时间戳，历史首付日使用 `DATE_FORMAT(FROM_UNIXTIME(firstpaytime / 1000), '%Y%m%d')`；抽样与 `ServerPayLog.dt` 对齐。
- 近 7 日累充排名直接汇总最近 7 天 `ServerPayLog.personal.money`；不能把支付流程事件或窗口内 `paytotal` 差分当交易金额。
- 支付流程事件可以按 `event` 名展示流程量，但不得命名为充值次数、真实订单数、付费人数、ARPU 或 ARPPU。
- ARPU 分母是同日 `UserActive` 活跃用户数，ARPPU 分母是同日付费用户数，二者分母不同。

## 留存与 LTV
- 留存和 LTV 必须先固定注册 cohort，再在后续用户日记录中读取 `remain` 或 `pay` 累计窗口字段。
- `remain.remain1 = 1` 表示 D1 留存，`remain3 = 1`、`remain7 = 1` 分别表示 D3/D7 留存。
- `pay.pay1/pay2/pay3/pay7/pay14/pay30` 表示注册后 1/2/3/7/14/30 个自然日累计付费窗口，注册日算第 1 个自然日；在不同生命周期日的快照中这些窗口会逐步成熟。
- LTV 命名必须区分：首日/1日 LTV 使用 `pay1` 和注册日快照；次日/2日 LTV 使用 `pay2` 和注册后第 1 天快照。不要把“次日 LTV”写成 `pay1`。
- `pay1/pay2/pay3/pay7` 字段名中的数字是累计窗口名，不是 `DATE_ADD` 的日期偏移量。新增 cohort LTV 快照映射必须写成：1 日/首日 LTV = 注册日快照 `s.dt = cohort_dt` 读取 `pay1`；次日/2 日 LTV = 注册后第 1 天快照 `cohort_dt + 1` 读取 `pay2`；3 日 LTV = 注册后第 2 天快照 `cohort_dt + 2` 读取 `pay3`；7 日 LTV = 注册后第 6 天快照 `cohort_dt + 6` 读取 `pay7`；14 日 LTV = `cohort_dt + 13` 读取 `pay14`；30 日 LTV = `cohort_dt + 29` 读取 `pay30`。
- 禁止把新增 cohort LTV 的 `d1_dt/d2_dt/d3_dt/d7_dt/d14_dt/d30_dt` 分别写成 `+1/+2/+3/+7/+14/+30`；正确偏移是 `+0/+1/+2/+6/+13/+29`。如果业务库最大 `dt` 尚未覆盖对应快照，应返回 NULL，而不是错位读取下一天或更晚快照。
- 新增 cohort LTV 回连 `user` 日快照时，`JOIN` 条件必须同时限定 `uid`、`prod`、固定分区边界和目标成熟快照分区。`bounds` 是单行 CTE；每个需要使用 `b.*` 的后续 CTE 都必须在自身的 `FROM` 中引入它，例如 `pay_windows AS (... FROM cohort c JOIN bounds b ON 1 = 1 LEFT JOIN user s ON s.uid = c.uid AND s.prod = 110000038 AND s.dt BETWEEN b.snapshot_start_dt AND b.snapshot_end_dt AND s.dt IN (c.d1_dt, c.d2_dt, c.d3_dt, c.d7_dt, ...))`。CTE 之间不会继承表别名作用域，不能只在 `cohort` CTE 中定义 `b` 后就在 `pay_windows` 中引用 `b.snapshot_start_dt`。禁止只写 `s.uid = c.uid AND s.prod = 110000038` 后再在 `SUM(CASE WHEN s.dt = ... THEN ...)` 中判断日期，这会扫描同一用户所有历史快照并导致 ADS/MySQL 超时。
- `snapshot_start_dt` 应等于 cohort 起始注册日，`snapshot_end_dt` 应等于本次需要的最大成熟快照日与业务库最新完整 `dt` 的较小值；例如只查 1/3/7 日 LTV 时最多到 cohort 结束日 + 6，查 30 日 LTV 时最多到 cohort 结束日 + 29。
- 新增首日付费金额固定取注册日快照行的 `pay.pay1` 求和，不要从后续快照 `MAX(pay1)`。
- 用户询问“最近 N 天新增用户的平均付费金额/人均付费”但没有说明首日、累计或生命周期窗口时，不要静默只返回单一 `pay1` 口径；优先同时输出 `新增用户数`、`首日付费金额`、`首日人均付费`、`截至最新完整分区累计付费金额`、`截至最新完整分区累计人均付费`，并在回答中标明两套口径。
- 用户明确说“首日/D0/当天付费/新增当天付费/新增用户中的付费用户占比”时，使用注册日快照的 `pay.pay1` 判断付费金额与付费用户。
- 用户明确说“次日 LTV”时，使用注册后第 1 天快照的 `pay.pay2`；这与“次日留存”的 +1 观察日对齐，但字段名是 pay2。
- 用户说“后续付费/产生的付费/累计付费/截至当前/截至昨日/到目前为止”时，先固定新增 cohort，再读取当前日前一完整分区的 `pay.paytotal` 快照；付费用户数按 `paytotal > 0` 去重，不要误用注册日 `pay.pay1`。
- 新增 cohort LTV 表必须先固定注册 cohort 和分母，再按成熟生命周期日读取对应快照：1 日取注册日快照的 `pay1`，次日/2 日取注册后第 1 天快照的 `pay2`，3 日取注册后第 2 天快照的 `pay3`，7 日取注册后第 6 天快照的 `pay7`，14 日取注册后第 13 天快照的 `pay14`，30 日取注册后第 29 天快照的 `pay30`。
- 未成熟或业务库还没有对应生命周期快照的 LTV 单元格应返回 NULL/空值，不要把未成熟 cohort 当 0，也不要用注册日快照填充后续 LTV。
- 当前 flam 业务库只有 `user` 与 `event` 两张业务表，注册归因 JSON 里可见媒体/广告系列信息，但没有真实买量成本字段；没有成本分母时不能把 LTV 或回收金额命名为真实 ROI。

## 图表字段
- flam 的 MySQL/ADS 驱动对中文 SQL 别名和大小写返回不稳定时，优先保持看板图表配置的字段名与 SQL 返回字段完全一致。
- 持久看板 SQL、图表字段、x/y 轴和表格列必须同步更新；不能只修改 SQL 文本。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对已保存看板中付费和 LTV 类组件的落地配置；看板刷新会按这些 SQL 重新取数。

{sql_blocks_markdown(PAYMENT_LTV_VIEW_IDS)}
""",
    },
    {
        "name": "flam 礼包购买结构口径",
        "description": "flam / first_zombie 礼包购买、商品结构、购买次数和购买人数 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:gift-purchase-structure -->
# flam 礼包购买结构口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于核心看板 `礼包购买情况`、礼包/商品购买结构、购买次数、购买人数和付费事件商品分布。

## SQL 口径
- 核心看板 `礼包购买情况` 当前使用 `event='ServerPayLog'` 作为落地口径。
- `购买礼包ID` 取 `ServerPayLog.personal.productid`：`NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.productid')), '')`；该字段为空的支付事件不进入礼包排行。
- `购买次数` 统计符合条件的 `ServerPayLog` 事件行数；`购买人数` 统计去重 `uid`。
- 历史窗口在未指定日期范围时，遵循平台通用 Data Skill 的过去 7 个完整自然日默认范围；非 `metric` 时间图使用 `{{dashboard_start_yyyymmdd}}` 至 `{{dashboard_end_yyyymmdd}}` 限定完整业务日 `dt` 分区、过滤 `prod = 110000038`，并返回同范围的 `date_filter`。

## 禁止事项
- 生成核心看板 `礼包购买情况` 的 SQL 时，不要再使用 `ext.payId` / `ext.rechargeId` / `ext.productId` / `ext.goodsId` 作为该组件的礼包标识。
- 不要把所有付费事件集合混入该组件；当前看板组件已经收敛为 `ServerPayLog` + `personal.productid`。
- 不要把 `user.pay.paytotal` 差分结果按礼包拆分；`paytotal` 是累计金额快照，不包含礼包 ID。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对核心看板 `礼包购买情况` 组件的落地配置。

{core_sql_blocks_markdown(("551d465e59fa454ba97ff9ef0ad0dd2a",))}
""",
    },
    {
        "name": "flam 新手引导漏斗口径",
        "description": "flam / first_zombie 新手 cohort、进入游戏、引导开始、引导完成和任务领奖漏斗 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:onboarding-funnel -->
# flam 新手引导漏斗口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于核心看板 `新手引导漏斗转化`、新手引导通过率、教程步骤转化、早期激活链路问题。

## SQL 口径
- 漏斗起点使用 `user` 表注册日 cohort：`userinfo.regdate = dt`，按 `uid` 去重。不要用全量登录用户作为默认分母，登录会混入老用户。
- 后续步骤只统计该 cohort 在观察窗口内触发的事件：
  - 进入游戏：`EnterGame`,`Login`,`UserLogin`
  - 引导开始：`NewUserGuideStart`,`DialogueStart`
  - 引导完成：`NewUserGuide`,`DialogueEnd`
  - 章节/任务领奖：`ChapterTaskReward`,`TaskReward`
- 默认观察窗口在未指定日期范围时，遵循平台通用 Data Skill 的过去 7 个完整自然日默认范围；使用当前日前一完整分区作为截止，事件窗口与 cohort 窗口一致，并过滤 `prod = 110000038`。
- 漏斗输出必须包含 `step_order`、`新手步骤`、`用户数`、`整体转化率`、`上步转化率`、`流失人数`，图表类型使用 `funnel`。

## 禁止事项
- 不要把事件次数当漏斗人数；每一步必须按 cohort 内 `uid` 去重。
- 不要把没有顺序含义的并列指标画成漏斗；本漏斗的步骤顺序由 `step_order` 明确控制。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对核心看板 `新手引导漏斗转化` 组件的落地配置。

{core_sql_blocks_markdown(("73cfeb49a58a44799e5a91371fbe296d",))}
""",
    },
    {
        "name": "flam 当前快照与分布口径",
        "description": "flam / first_zombie 当前态快照指标和等级分布 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:current-snapshot-distribution -->
# flam 当前快照与分布口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于当前等级分布、当前等级段人群和其他明确询问“当前态/最新快照”的分布问题。

## SQL 口径
- 当前态指标使用 `user` 用户日表的当前日前一完整分区，固定过滤 `prod = 110000038`，避免为取最新分区扫描大视图。
- 等级取 `lastinfo.level`，按最新分区上的 `uid` 去重统计。
- 核心看板 `当前等级分布` 当前使用 3 级一个分桶：`0-2`、`3-5`、`6-8`、...、`27-29`、`30+`；空等级按 0 归入 `0-2`。
- 当前快照分布不是一段时间内的累计去重；不要把最近 30 天所有用户日合并后统计等级分布。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对已保存看板中当前快照分布类组件的落地配置。

{sql_blocks_markdown(CURRENT_SNAPSHOT_VIEW_IDS)}
""",
    },
    {
        "name": "flam 渠道投放注册与付费口径",
        "description": "flam / first_zombie 渠道注册 cohort、首日/7 日付费和投放看板 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:channel-acquisition-pay -->
# flam 渠道投放注册与付费口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于投放看板中渠道注册、首日付费、7 日累计付费和累计付费指标。

## SQL 口径
- 渠道投放注册必须先固定注册日 cohort：`user.userinfo.regdate = user.dt`，按 `uid` 去重。
- 渠道归因取注册日快照行的 `adinfo.mediaSource`，缺失时用 `adinfo.campaignName`，仍缺失记为“未知”。
- 首日付费金额固定读取注册日快照 `pay.pay1`；7 日累计付费读取注册日后第 6 天快照的 `pay.pay7`，未成熟时返回空值；累计付费读取当前日前一完整快照的 `pay.paytotal`。
- 历史窗口在未指定日期范围时，遵循平台通用 Data Skill 的过去 7 个完整自然日默认范围；非 `metric` 时间图使用 `{{dashboard_start_yyyymmdd}}` 至 `{{dashboard_end_yyyymmdd}}` 限定完整业务日 `dt` 分区、过滤 `prod = 110000038`，并返回同范围的 `date_filter`。

## 禁止事项
- 不要用活跃事件行的渠道覆盖注册归因。
- 不要从后续快照 `MAX(pay1)` 推导首日付费。
- 不要从注册日快照读取 7 日累计付费或累计付费；注册日快照会让首日、7 日和累计金额错误地相同。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对投放/渠道注册付费组件的落地配置。

{remaining_sql_blocks_markdown(CHANNEL_ACQUISITION_VIEW_IDS)}
""",
    },
    {
        "name": "flam 付费分布与付费事件结构口径",
        "description": "flam / first_zombie 充值用户周累充分布、付费事件商品结构和礼包购买分布 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:pay-distribution-structure -->
# flam 付费分布与付费事件结构口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于付费概览和渠道分析中的周累充分布、付费事件分布和商品/礼包购买结构。

## SQL 口径
- 周累充分布使用 `user` 用户日快照。持久看板按每周固定快照分区取数：历史完整周取周末分区，当前周取当前日前一完整分区；不要在 ADS 上对每个用户/每周动态 `MAX(dt)`。
- 支付流程事件分布使用 `PayBuyRet`,`PayBuyRetBenifit`,`PayBuyRetSandBox`,`PayFinish`,`ep_pay_purchase_finish`,`ep_pay_update_db_finish`，只按 `event` 展示流程事件量。
- 真实商品/礼包购买结构只使用 `ServerPayLog.personal.productid`；未验证流程事件的商品字段不做 `ext` 回退，也不回退为交易商品名。
- 周累充分布按累计 `pay.paytotal` 分段；支付流程事件分布统计流程事件行数，不从 `paytotal` 差分反推商品或交易金额。

## 禁止事项
- 不要把 `ep_pay_update_db_finish` 或其它支付流程事件混入真实交易金额、订单、付费人数或 ARPU 指标。
- 不要按天快照直接累计用户数；持久看板必须使用每周一个快照分区，避免一名用户在同一周被多天重复计入。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对付费分布类组件的落地配置。

{remaining_sql_blocks_markdown(PAY_DISTRIBUTION_VIEW_IDS)}
""",
    },
    {
        "name": "flam 活动参与与后续质量口径",
        "description": "flam / first_zombie 活动参与率、人均参与、近7天各活动参与次数、活动后续留存和付费质量 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:activity-quality -->
# flam 活动参与与后续质量口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于活动分析看板中的活动参与率、人均参与次数、等级段参与、近7天各活动参与次数、活动后续留存和活动后续付费。

## SQL 口径
- 活动参与人数使用活动事件集合中的 `uid` 去重；活动次数使用事件行数。
- “每周活动参与次数分布”当前落地为近7天按活动类型统计参与次数、参与人数和人均参与次数；活动类型取 `event`，参与次数为事件行数，参与人数为 `uid` 去重。
- 活动参与率的分母为同日 `UserActive` DAU。
- “各等级段参与日常活动的人数分布”优先读取 `personal.ed_mainBuildingLevel`，每3个等级一个段，最大到31级；过滤等级为空或不在1-31之间的记录，不输出未知等级段。
- 活动后续留存先固定用户首次参与活动日，再在参与日后的精确 D1/D7 `UserActive` 事件中按 `uid` 去重；D7 未成熟参与日不进入分母。
- 活动后续付费先固定用户首次参与活动日，再在参与日后的精确目标日 `ServerPayLog` 事件中按 `uid` 去重；金额读取 `personal.money`，订单读取 `personal.orderId`。
- 活动后续质量不得使用注册 cohort 的 `remain.remain1/remain7` 或 `pay1/pay7`，也不要把所有历史付费用户混入活动参与 cohort。

## 禁止事项
- 不要把活动事件次数当参与人数。
- 不要用全量注册用户或全量活跃用户替代具体活动参与 cohort。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对活动分析组件的落地配置。

{remaining_sql_blocks_markdown(ACTIVITY_VIEW_IDS)}
""",
    },
    {
        "name": "flam 钻石经济口径",
        "description": "flam / first_zombie 钻石获取、消耗、存量变化和来源/去向 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:gold-economy -->
# flam 钻石经济口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于经济系统看板中的钻石获取、消耗、存量变化、获取途径和消耗途径。

## SQL 口径
- 钻石经济使用 `event='GoldChange'`。
- 钻石变化字段在 `personal` 中，免费钻石取 `personal.ed_changeFree`，付费钻石取 `personal.ed_changePaid`。
- “钻石消耗获取情况”按免费钻石和付费钻石分别输出获取量、消耗量、存量变化；变化量大于 0 计入获取，变化量小于 0 取绝对值计入消耗，原始正负和保留为存量变化。
- “免费钻石获取途径分布”只统计 `personal.ed_changeFree > 0` 的获取记录，按 `personal.ed_route` 聚合，缺失时使用 `personal.ed_detailReason`，仅输出获取途径和免费钻石获取量。
- “钻石消耗途径分布”只统计 `personal.ed_changeFree < 0` 或 `personal.ed_changePaid < 0` 的消耗记录，按 `personal.ed_route` 聚合，缺失时使用 `personal.ed_detailReason`，分别输出免费钻石消耗量和付费钻石消耗量。
- 获取/消耗途径优先取 `personal.ed_route`，缺失时取 `personal.ed_detailReason`，仍缺失记为“未知”。
- 历史窗口在未指定日期范围时，遵循平台通用 Data Skill 的过去 7 个完整自然日默认范围；非 `metric` 时间图使用 `{{dashboard_start_yyyymmdd}}` 至 `{{dashboard_end_yyyymmdd}}` 限定完整业务日 `dt` 分区、过滤 `prod = 110000038`，并返回同范围的 `date_filter`。

## 禁止事项
- 不要再从 `ext.ed_changeFree/ext.ed_changePaid` 读取钻石变化；当前 `GoldChange` 样本中 `ext` 为空，字段在 `personal`。
- 不要把负数消耗直接展示为负柱；看板消耗量应展示绝对值。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对经济系统组件的落地配置。

{remaining_sql_blocks_markdown(ECONOMY_VIEW_IDS)}
""",
    },
    {
        "name": "flam 礼包复购与月卡留存口径",
        "description": "flam / first_zombie 新手礼包复购、月卡购买用户留存和付费商品识别 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:gift-retention -->
# flam 礼包复购与月卡留存口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于礼包付费概览中的新手礼包复购率、月卡购买用户 30 日留存。

## SQL 口径
- 购买行为不使用 `user.pay.paytotal` 直接拆商品。
- “购买新手礼包用户复购率”当前落地仅使用 `event='ServerPayLog'`，商品 ID 读取 `personal.productid`，订单号读取 `personal.orderId`。
- 新手礼包当前识别为 `personal.productid = '85003'`；首购日为用户首次购买该商品的日期。
- 新手礼包复购率以购买新手礼包用户为 cohort，统计首购后 7 日内是否再次触发 `ServerPayLog`；近 7 天未成熟首购 cohort 需要排除，避免复购率偏低。
- “购买月卡用户的30日留存”当前落地仅使用 `event='ServerPayLog'`，月卡商品暂定为 `personal.productid = '190002'`。
- 月卡留存以 30-60 天前购买月卡的成熟用户为 cohort，使用 `UserActive` 判断购买后第 1/3/7/15/30 日活跃，输出次留、3留、7留、15留、30留。

## 禁止事项
- 不要把所有付费用户当新手礼包或月卡 cohort。
- 不要用累计付费快照推断具体商品复购。
- 生成新手礼包复购 SQL 时不要从 `ext` 读取商品 ID；`ServerPayLog` 样本中商品字段在 `personal.productid`。
- 生成月卡留存 SQL 时不要使用 `month`/`月卡` 文本匹配；当前 `ServerPayLog` 样本中商品字段是数字型 `personal.productid`。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对礼包复购和月卡留存组件的落地配置。

{remaining_sql_blocks_markdown(GIFT_RETENTION_VIEW_IDS)}
""",
    },
    {
        "name": "flam 出征与演习口径",
        "description": "flam / first_zombie 出征、竞技场、荣耀远征、过去7日出征维度、英雄出征量和胜率 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:expedition-drill -->
# flam 出征与演习口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于出征数据看板中的出征事件数、过去7日出征维度分析、平均战力、荣耀远征、出征明细、近七天英雄出征量、胜率和主城等级演习。

## SQL 口径
- 出征/竞技/演习事件集合为 `WorldMarch`,`WorldMarchRet`,`ActivityWorldBoss`,`ActivityAllianceBossBattleRet`,`honorExpedition`,`ArenaResults`,`TrainingArenaResults`,`multipleArena`。
- “过去7日各兵种出征情况”当前落地为 `WorldMarch` 出征维度分析：出征类型取 `personal.ed_marchType`，目标类型取 `personal.ed_targetType`，大本等级取 `personal.ed_mainBuildingLevel`，出征 ID 取 `personal.ed_marchId`，预计耗时取 `personal.ed_estimatedSeconds`，出征战力取 `personal.ed_myTeamBattlePower`。
- “近七天英雄出征量分布”使用 `WorldMarch` 的 `personal.ed_myTeamHeroList`，该字段是英雄对象 JSON 数组；需按数组下标展开并读取每个对象的 `heroId`，不要把整段 JSON 当英雄 ID，也不要按逗号拆字符串。
- 主城等级优先取事件参数 `personal.ed_mainBuildingLevel`。
- 平均战力优先取 `personal.ed_myTeamBattlePower`；未验证的 ext 战力字段不得作为回退。
- “各等级出征胜率”使用 `WorldMarchRet` 结果事件，按 `personal.ed_mainBuildingLevel` 和 `personal.ed_targetType` 分组；胜利判断优先取 `personal.ed_result`，其次 `personal.ed_battleResult`，值为 `4`、`win`、`success`、`1`、`胜利` 计为胜利。
- “各英雄出征胜率”使用 `WorldMarch` 的 `personal.ed_myTeamHeroList` 展开英雄阵容，再按 `uid + personal.ed_marchId` 回连 `WorldMarchRet` 结果事件；出征次数按 `uid + ed_marchId + hero_id` 去重统计，胜率分母为该英雄参与且有结果回包的出征次数，不输出出征用户数。
- 出征分布、胜率、将领/主城等级拆分会解析 JSON 并做高基数分组，持久看板默认使用近 7 天窗口；指标卡只查昨天、前天、上周同日三个目标分区。

## 禁止事项
- 不要把全量战斗/活动事件都算作出征事件。
- 不要把胜率分母写成参与用户数；胜率分母是有结果的出征/竞技事件行。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对出征数据组件的落地配置。

{remaining_sql_blocks_markdown(EXPEDITION_VIEW_IDS)}
""",
    },
    {
        "name": "flam 英雄养成口径",
        "description": "flam / first_zombie 英雄升级、升星、养成用户和 SSR 英雄等级分布 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:hero-growth -->
# flam 英雄养成口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于养成看板中的英雄养成情况和 SSR 英雄等级分布。

## SQL 口径
- 英雄养成事件集合为 `HeroAcquisition`,`HeroLevelUp`,`HeroStarUp`,`HeroSkillUpgrade`,`HeroRecruit`。
- 养成看板当前落地 SQL 优先读取 `event.personal` 中的英雄字段；英雄 ID 使用 `personal.ed_heroId`。
- 英雄等级优先取 `personal.ed_currentLevel`，缺失时取 `personal.ed_heroLevel`。
- 英雄星级优先取 `personal.ed_heroStar`，缺失时取 `personal.ed_newStar`。
- 当前等级分布必须先按 `uid, hero_id` 用 `ROW_NUMBER() OVER (PARTITION BY uid, hero_id ORDER BY dt DESC, time DESC)` 取最近一条养成事件，再统计用户数；不要把历史升级事件行数当当前等级分布。
- 英雄养成情况只统计 `HeroLevelUp` 和 `HeroStarUp` 两类看板行为，且仅保留 `personal.ed_heroId` 非空的事件。

## 禁止事项
- 不要用事件次数代替当前持有/当前等级分布人数。
- 不要在没有 hero_id 的事件上强行拆英雄，缺失可归为“未知”。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对英雄养成组件的落地配置。

{remaining_sql_blocks_markdown(HERO_GROWTH_VIEW_IDS)}
""",
    },
    {
        "name": "flam 主城建设与成长口径",
        "description": "flam / first_zombie 主城等级、建筑/科技升级、英雄招募、加速和主城漏斗 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:city-build-growth -->
# flam 主城建设与成长口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于主城建设看板中的主城平均等级、主城/建筑/科技升级、等级分布、招募情况、加速和主城升级漏斗。

## SQL 口径
- 当前主城等级类指标使用 `user` 当前日前一完整分区的 `lastinfo.blevel`，按 `uid` 去重，并过滤 `prod = 110000038`。
- 主城/建筑升级事件使用 `BuildingUpgrade`,`BuildingIdleUpgrade`；建筑 ID 优先取 `personal.ed_buildingId`，其次 `personal.ed_metaId`。
- 科技升级类事件只使用 `TechnologyDonation`。
- 招募情况使用 `event='HeroRecruit'`，招募池 ID 取 `personal.ed_cardType`，招募方式取 `personal.ed_recruitNumType`；`ONE` 映射为“单抽”，`TEN` 映射为“十连抽”，缺失或其它值归为“未知”。
- 加速类型当前没有已验证字段映射；组件必须显示“待补充字段映射”，不得从 `ext.ed_detailReason`、`ext.ed_route` 或其他相邻字段猜测类型。
- 主城升级漏斗使用最新快照主城等级阈值，而不是历史升级事件次数。
- 三个“当日升级次数” `metric` 使用当前业务日的前一日作为最新完整业务日，并据此计算前一日和上周同日；不得返回 `date_filter` 或看板日期 token。示例中的 `20260730` 仅表示已由调用方确定的当前业务日，实际生成时必须替换为本次请求确定的日期字面量。

## 禁止事项
- 不要把最近 30 天所有用户快照合并后统计当前等级分布。
- 不要把升级事件次数当当前主城等级玩家数。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对主城建设组件的落地配置。

{remaining_sql_blocks_markdown(CITY_BUILD_VIEW_IDS)}
""",
    },
    {
        "name": "flam 留存流失与回流口径",
        "description": "flam / first_zombie 活跃留存、付费留存、流失、沉默和回流用户 SQL 生成规则。",
        "prompt": """<!-- data-skill-source:flam:first-zombie:retention-churn-return -->
# flam 留存流失与回流口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于留存分析看板、活跃留存、付费留存、流失用户、沉默用户、回流用户、召回分析和流失前行为画像。

## SQL 口径
- 活跃留存使用 `event='UserActive'`，按 `uid` 去重；不要把全事件去重或 `user` 快照行数当活跃。
- 新增用户留存继续遵循 `flam 新增与留存 cohort 口径`：先固定注册 cohort，再看精确 D1/D3/D7 的 `UserActive` 或明确要求时读取 `remain` 标记。
- 活跃用户留存以观察日 `UserActive` 用户为 cohort，分子为同一批用户在第 N 日再次 `UserActive`，默认只展示已成熟观察日。
- 付费用户留存以观察日付费事件用户或付费快照用户为 cohort；如果用户问“付费后留存”，优先使用付费事件集合确定 cohort，再在后续 `UserActive` 中计算留存。
- 用户未指定流失天数时，默认 `流失用户` 为最近 7 个完整业务日没有 `UserActive`、且此前 30 天内有过 `UserActive` 的用户。
- 用户未指定沉默天数时，默认 `沉默用户` 为最近 3 到 6 个完整业务日没有 `UserActive`、且此前 30 天内有过 `UserActive` 的用户。
- 用户未指定回流天数时，默认 `回流用户` 为当前观察日 `UserActive`，且此前连续 7 个完整业务日没有 `UserActive`，再往前 30 天内有过 `UserActive` 的用户。
- 流失前画像可以按渠道、系统、区服、等级、主城等级、付费分层、最近一次活动/付费/建筑/出征行为拆分；涉及当前状态时使用 `user` 当前日前一完整分区。
- 历史窗口优先使用 `{{dashboard_start_yyyymmdd}}` 至 `{{dashboard_end_yyyymmdd}}` 限定固定完整 `dt` 分区，并过滤 `prod = 110000038`；非 `metric` 时间图返回同范围的 `date_filter`，避免先对 ADS 大视图做 `MAX(dt)` 或全历史扫描。

## 七日留存 SQL 示例（MySQL/StarRocks）
当用户要求查看最近一段已成熟 cohort 的 D7 留存趋势时，使用以下结构作为生成 SQL 的参照。可以按用户指定的 cohort 数量调整窗口，但必须保留 `bounds`、注册 cohort 和第 7 日快照三层结构。

```sql
WITH bounds AS (
  SELECT MAX(dt) AS max_dt
  FROM `user`
  WHERE prod = 110000038
),
cohorts AS (
  SELECT
    u.uid,
    u.dt AS cohort_dt
  FROM `user` u
  CROSS JOIN bounds b
  WHERE u.prod = 110000038
    AND u.dt BETWEEN
      CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(b.max_dt AS CHAR), '%Y%m%d'), INTERVAL 20 DAY), '%Y%m%d') AS SIGNED)
      AND CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(b.max_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED)
    AND JSON_UNQUOTE(JSON_EXTRACT(u.userinfo, '$.regdate')) = CAST(u.dt AS CHAR)
),
retention_snapshot AS (
  SELECT
    c.cohort_dt,
    c.uid,
    JSON_UNQUOTE(JSON_EXTRACT(r.remain, '$.remain7')) AS remain7
  FROM cohorts c
  LEFT JOIN `user` r
    ON r.uid = c.uid
   AND r.prod = 110000038
   AND r.dt = CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED)
)
SELECT
  cohort_dt AS `注册日期`,
  COUNT(DISTINCT uid) AS `新增用户数`,
  COUNT(DISTINCT CASE WHEN remain7 = '1' THEN uid END) AS `七日留存人数`,
  ROUND(
    COUNT(DISTINCT CASE WHEN remain7 = '1' THEN uid END) * 100.0
    / NULLIF(COUNT(DISTINCT uid), 0),
    2
  ) AS `七日留存率`
FROM retention_snapshot
GROUP BY cohort_dt
ORDER BY cohort_dt;
```

- 上例展示最近 14 个已成熟 D7 cohort：`max_dt - 20` 到 `max_dt - 7`。
- `remain7` 必须从 `cohort_dt + 7` 的 `r.remain` 快照读取，不能写成物理列 `u.remain7`，也不能读取注册日快照。
- 不得在 `WHERE` 中直接使用 `MAX(dt)`；最大分区只能在 `bounds` CTE/子查询中计算，再通过 `b.max_dt` 引用。

## 推荐输出
- 留存矩阵输出字段建议为 `cohort_date`、`cohort_users`、`retained_users_d1/d3/d7`、`retention_rate_d1/d3/d7`。
- 流失/沉默/回流输出字段建议为 `日期`、`用户数`，拆分分析增加 `渠道`、`系统`、`区服ID`、`等级段`、`付费分层` 等维度。
- ID 类字段如 `uid`、`区服ID` 必须按文本展示，不要加千分位格式化。

## 禁止事项
- 不要把未成熟 cohort 的留存当 0。
- 不要把某日没有事件的用户直接判为永久流失；必须说明使用的连续未活跃窗口。
- 不要把付费留存和新增留存混用；二者 cohort 分母不同。
""",
    },
    {
        "name": "flam 用户分层与人群分析口径",
        "description": "flam / first_zombie 新老用户、活跃分层、付费分层、等级分层和人群交叉分析 SQL 生成规则。",
        "prompt": """<!-- data-skill-source:flam:first-zombie:user-segmentation -->
# flam 用户分层与人群分析口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于用户分群、人群画像、分层对比、高价值用户、低活跃高付费用户、等级/主城/付费/活跃交叉分析。

## 分层定义
- 新增用户：注册日 cohort，优先用 `event='UserRegister'`；需要快照字段时用 `user.userinfo.regdate = user.dt`。
- 新用户/老用户生命周期默认使用 `user.lastinfo.regnday`：`<=1` 新增期，`<=7` 成长期，`<=30` 稳定期，`>30` 成熟期。
- 活跃分层默认基于最近 7 个完整业务日的 `UserActive` 天数：1 天低活跃，2-4 天中活跃，5-7 天高活跃。
- 付费分层默认基于当前日前一完整分区 `user.pay.paytotal`：0 为非付费，`(0,100)` 小额付费，`[100,500)` 中额付费，`[500,+∞)` 高额付费；用户指定阈值时以用户阈值为准。
- 等级段默认读取 `user.lastinfo.level`：1-10、11-20、21-30、31+；主城等级段默认读取 `user.lastinfo.blevel`：1-5、6-10、11-15、16+。
- 渠道优先读取注册日或目标事件行 `adinfo.mediaSource`，缺失时用 `adinfo.campaignName`，仍缺失记为“未知”；不要用后续活跃事件渠道覆盖注册归因，除非用户明确问活跃渠道。

## SQL 口径
- 当前人群画像使用 `user` 当前日前一完整分区，按 `uid` 去重；不要合并最近 30 天用户快照后统计当前画像。
- 行为人群使用 `event` 表先固定行为 cohort，再回连同日或当前快照读取画像字段。
- 高价值用户、付费用户、未付费用户等金额相关人群必须遵守字段权限；如果当前用户无权读取 `pay`，不得生成金额或 ARPU/ARPPU 相关 SQL。
- 交叉分析默认输出每个分层的用户数、占比；需要业务效果时再追加 DAU、付费用户数、付费金额、留存率等指标。
- 历史窗口优先使用 `{{dashboard_start_yyyymmdd}}` 至 `{{dashboard_end_yyyymmdd}}` 限定固定完整 `dt`，并过滤 `prod = 110000038`；非 `metric` 时间图返回同范围的 `date_filter`。

## 推荐输出
- 人群分层表字段建议为 `分层名称`、`用户数`、`占比`。
- 交叉分析字段建议为 `分层A`、`分层B`、`用户数`、`活跃用户数`、`付费用户数`、`付费金额`，其中金额字段需有权限才输出。
- 用户 ID、区服 ID、联盟 ID、订单号等标识字段按文本展示。

## 禁止事项
- 不要把事件次数当用户数；用户分层默认按 `uid` 去重。
- 不要在用户没有给阈值时临时发明多个互相冲突的付费分层；使用本 skill 默认阈值并在回答中说明。
- 不要绕过权限读取 `pay`、`remain` 或其他被禁字段。
""",
    },
    {
        "name": "flam 区服生命周期与健康度口径",
        "description": "flam / first_zombie 区服维度新增、活跃、付费、留存、开服阶段和健康度 SQL 生成规则。",
        "prompt": """<!-- data-skill-source:flam:first-zombie:server-lifecycle-health -->
# flam 区服生命周期与健康度口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于区服分析、新服/老服对比、区服健康度、区服新增/活跃/付费/留存、开服阶段和区服异常排查。

## 字段口径
- 区服 ID 优先读取 `user.userinfo._serverId`，缺失时读取 `user.lastinfo._serverId`；事件分析可读取事件行 `userinfo._serverId` 或 `lastinfo._serverId`。
- 区服 ID 是标识字段，SQL 输出时建议 `CAST(server_id AS CHAR) AS 区服ID`，前端展示不得加千分位。
- 如果数据源没有独立开服日期表，默认用该区服最早注册日或最早 `UserRegister` 业务日近似开服日；回答中必须标明这是近似口径。
- 区服生命周期默认按开服天数分层：0-3 天新服启动期，4-7 天新服成长期，8-14 天稳定观察期，15 天以上成熟期；用户指定分层时以用户指定为准。

## SQL 口径
- 区服新增使用 `UserRegister` 或注册日快照 cohort，按 `uid` 去重。
- 区服 DAU 使用 `event='UserActive'`，按 `uid` 去重。
- 区服付费用户和充值次数使用付费事件集合；区服累计付费金额使用当前日前一完整分区 `user.pay.paytotal`，金额字段需遵守权限。
- 区服留存先固定区服注册 cohort，再看精确 D1/D3/D7 `UserActive`；不要用当前区服活跃用户反推注册留存。
- 区服健康度默认同时看最近 7 天 DAU 趋势、新增趋势、付费用户数、付费金额、D1/D7 留存和流失/回流；没有成本字段时不要输出 ROI。
- 历史窗口优先使用 `{{dashboard_start_yyyymmdd}}` 至 `{{dashboard_end_yyyymmdd}}` 限定固定完整 `dt`，并过滤 `prod = 110000038`；非 `metric` 时间图返回同范围的 `date_filter`。

## 推荐输出
- 区服排行榜字段建议为 `区服ID`、`新增用户数`、`DAU`、`付费用户数`、`付费金额`、`D1留存率`、`开服天数`。
- 区服生命周期趋势字段建议为 `日期`、`区服ID`、`生命周期阶段`、`新增用户数`、`活跃用户数`、`付费金额`。

## 禁止事项
- 不要把区服 ID 当连续数值求和或平均。
- 不要在没有开服日期表时假装有真实开服日；只能用最早注册/事件日期近似。
- 不要把注册归因渠道和活跃事件渠道混用到同一个区服 cohort 口径里。
""",
    },
    {
        "name": "flam 埋点健康与数据质量口径",
        "description": "flam / first_zombie 事件量、用户量、字段完整率、数据新鲜度和异常波动 SQL 生成规则。",
        "prompt": """<!-- data-skill-source:flam:first-zombie:tracking-data-quality -->
# flam 埋点健康与数据质量口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于埋点健康检查、事件量异常、字段缺失、数据新鲜度、版本/渠道/系统维度的数据质量排查。

## SQL 口径
- 事件量使用 `event` 表行数，事件用户数使用 `COUNT(DISTINCT uid)`；二者必须分开展示。
- 数据新鲜度优先检查最近固定窗口内是否存在目标 `dt` 分区，例如最近 3 天或 7 天；ADS 查询较慢时避免直接全表 `MAX(dt)`。
- 关键事件健康检查默认覆盖 `UserRegister`、`UserActive`、付费事件集合、`CCU`、`GoldChange`、主城/建筑升级、活动、出征和英雄养成事件集合。
- 字段完整率按目标事件过滤后计算：`missing_rate = 缺失目标 JSON path 的事件数 / 目标事件数`；不要在所有事件上检查只属于某个事件的字段。
- JSON 字段空值判断使用 `NULLIF(JSON_UNQUOTE(JSON_EXTRACT(...)), '') IS NULL`，同时兼容 JSON path 不存在和空字符串。
- 事件波动默认按最近 7 天与前 7 天对比，输出事件量、事件用户数、环比变化；用户要求同比时再查上周同日或更长窗口。
- 版本、系统、设备、渠道、国家等维度需先确认字段存在：常见来源为 `deviceinfo._platform`、`deviceinfo._osVersion`、`deviceinfo._model`、`adinfo.mediaSource`、`adinfo.campaignName`、`userinfo.country`。
- 历史窗口优先使用 `{{dashboard_start_yyyymmdd}}` 至 `{{dashboard_end_yyyymmdd}}` 限定固定完整 `dt`，并过滤 `prod = 110000038`；非 `metric` 时间图返回同范围的 `date_filter`，避免大范围 JSON_KEYS 聚合或全历史扫描。

## 推荐输出
- 事件健康表字段建议为 `日期`、`事件名`、`事件量`、`触发用户数`、`较前期变化率`。
- 字段完整率表字段建议为 `事件名`、`字段路径`、`事件量`、`缺失事件数`、`缺失率`。
- 数据新鲜度表字段建议为 `表名`、`检查窗口`、`最近有数日期`、`缺失分区数`、`状态`。

## 禁止事项
- 不要把事件量下跌直接解释为业务下跌；需要先排除埋点缺失、分区延迟、版本/渠道局部缺失。
- 不要在没有字段样本或字典说明时硬猜 JSON path；可以先输出需要确认的字段路径。
- 不要用全表 `COUNT(*)` 或全历史 `MAX(dt)` 作为默认健康检查，除非用户明确要求全量审计。
""",
    },
]

_DASHBOARD_SQL_BLOCK_PATTERN = re.compile(
    r"(?P<header><!-- dashboard-sql:(?P<view_id>[^ ]+?) -->\s*```sql\s*\n)"
    r"(?P<sql>[\s\S]*?)(?P<footer>\n```)"
)
_DASHBOARD_TOKEN_DATE_VIEW_IDS = {
    "839ce2cab673467ab22fe508bf822d61",
    "f0793fb6af7845c8be2b39e2d7ea523f",
    "97337c8b63544de89f26d2719cc45e75",
}
_DASHBOARD_REALTIME_DATE_VIEW_IDS = {
    "4fc570b4be7d406c9f648d9088f760bb",
    "2149b7abbc6c4cd7ad6f52379e69b15a",
}
_DASHBOARD_METRIC_DATE_VIEW_IDS = {
    "9d4add7a8be048ea9c7beb62a43e50cc",
    "9325211a9f594376bf818cec639aa103",
    "440303dfdf39408ba86ffb222f3334f2",
    "0b849c96c0a3480c9e940b92995d5e3e",
    "4608fb0831cd4845ba881678fb778b2f",
    "dbc481fea69d4314af8535600fa4f8c8",
    "48f02edf9a364e1082cd67008cd60b2b",
    "8f6dcec8cfdb40b4a7c02139b7d35f56",
}
_DASHBOARD_END_DATE_SQL = (
    "STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d')"
)
_DASHBOARD_START_DATE_SQL = (
    "STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d')"
)
_REALTIME_BUSINESS_DATE_SQL = "DATE(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR))"
_METRIC_EXAMPLE_BUSINESS_DATE_SQL = "STR_TO_DATE('20260730', '%Y%m%d')"
_DATABASE_CURRENT_DATE_PATTERN = re.compile(
    r"\b(?:CURDATE|NOW|CURRENT_DATE|CURRENT_TIMESTAMP|LOCALTIME|LOCALTIMESTAMP|"
    r"GETDATE|GETUTCDATE)\s*(?:\(\s*\))?",
    re.IGNORECASE,
)


def _tokenize_dashboard_sql_current_date(prompt: str) -> str:
    """按看板语义替换旧日期函数，未知用法直接拒绝发布。"""

    def replace_sql_block(match: re.Match[str]) -> str:
        view_id = match.group("view_id")
        sql = match.group("sql")
        current_date_match = _DATABASE_CURRENT_DATE_PATTERN.search(sql)
        if view_id in _DASHBOARD_METRIC_DATE_VIEW_IDS:
            sql = sql.replace(_DASHBOARD_START_DATE_SQL, _METRIC_EXAMPLE_BUSINESS_DATE_SQL)
            sql = sql.replace(_DASHBOARD_END_DATE_SQL, _METRIC_EXAMPLE_BUSINESS_DATE_SQL)
            sql = _DATABASE_CURRENT_DATE_PATTERN.sub(_METRIC_EXAMPLE_BUSINESS_DATE_SQL, sql)
        elif current_date_match is None:
            return match.group(0)
        elif view_id in _DASHBOARD_TOKEN_DATE_VIEW_IDS:
            sql = _DATABASE_CURRENT_DATE_PATTERN.sub(_DASHBOARD_END_DATE_SQL, sql)
            if view_id == "97337c8b63544de89f26d2719cc45e75":
                sql = sql.replace(
                    f"DATE_SUB({_DASHBOARD_END_DATE_SQL}, INTERVAL 60 DAY)",
                    f"DATE_SUB({_DASHBOARD_START_DATE_SQL}, INTERVAL 30 DAY)",
                )
        elif view_id in _DASHBOARD_REALTIME_DATE_VIEW_IDS:
            sql = sql.replace(
                "FROM_UNIXTIME(e.time / 1000)",
                "DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR)",
            )
            sql = _DATABASE_CURRENT_DATE_PATTERN.sub(_REALTIME_BUSINESS_DATE_SQL, sql)
        else:
            raise ValueError(f"Flam 看板 SQL 存在未分类的数据库当前日期函数: {view_id}")
        return f"{match.group('header')}{sql}{match.group('footer')}"

    return _DASHBOARD_SQL_BLOCK_PATTERN.sub(replace_sql_block, prompt)


DATA_SKILLS = [
    {**skill, "prompt": _tokenize_dashboard_sql_current_date(skill["prompt"])}
    for skill in apply_dashboard_skill_overrides(DATA_SKILLS)
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
          AND tenant_id = %s
          AND specific_ds = TRUE
          AND datasource_ids = %s::jsonb
          AND position(%s in COALESCE(prompt, '')) > 0
        ORDER BY id
        LIMIT 1
        """,
        (tenant_id, Jsonb([datasource_id]), marker),
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
              AND tenant_id = %s
              AND type = 'DATA_SKILL'
              AND specific_ds = TRUE
              AND datasource_ids = %s::jsonb
            """,
            (*values, skill_id, tenant_id, Jsonb([datasource_id])),
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
        VALUES (%s, 'DATA_SKILL', %s, %s, %s, 'ALL', TRUE, TRUE, NULL, NULL, 'ADMIN_PUBLIC', %s, TRUE, %s, NULL, NULL)
        RETURNING id
        """,
        (tenant_id, now, skill["name"][:255], skill["description"], prompt, Jsonb([datasource_id])),
    )
    return int(cur.fetchone()[0])


def _delete_stale_skills(cur, *, tenant_id: int, datasource_id: int) -> list[int]:
    stale_ids: list[int] = []
    for marker in STALE_SKILL_MARKERS:
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
            FOR UPDATE
            """,
            (tenant_id, Jsonb([datasource_id]), marker),
        )
        ids = [int(row[0]) for row in cur.fetchall()]
        if not ids:
            continue
        stale_ids.extend(ids)
        cur.execute(
            """
            DELETE FROM custom_prompt_user_preference
             WHERE custom_prompt_id = ANY(%s)
            """,
            (ids,),
        )
        cur.execute(
            """
            DELETE FROM custom_prompt
             WHERE tenant_id = %s
                AND type = 'DATA_SKILL'
                AND specific_ds = TRUE
                AND datasource_ids = %s::jsonb
                AND position(%s in COALESCE(prompt, '')) > 0
            """,
            (tenant_id, Jsonb([datasource_id]), marker),
        )
    return stale_ids


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
    deleted_stale_ids: list[int] = []
    with psycopg.connect(**DB) as conn:
        with conn.cursor() as cur:
            for skill in DATA_SKILLS:
                ids.append(_upsert_skill(cur, tenant_id=TENANT_ID, datasource_id=DATASOURCE_ID, skill=skill, now=now))
            deleted_stale_ids = _delete_stale_skills(
                cur,
                tenant_id=TENANT_ID,
                datasource_id=DATASOURCE_ID,
            )
        conn.commit()
    saved = _save_embeddings(ids, TENANT_ID)
    print(f"Upserted flam data skills: {ids}; deleted stale skills: {deleted_stale_ids}; embeddings saved: {saved}")


if __name__ == "__main__":
    main()
