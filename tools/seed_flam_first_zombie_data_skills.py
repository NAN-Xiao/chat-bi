# -*- coding: utf-8 -*-
"""Seed flam / first_zombie datasource-scoped Data Skills."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from core_system_db import core_system_db_config, export_postgres_compat_env
from flam_first_zombie_active_dashboard_sql import sql_blocks_markdown as active_sql_blocks_markdown
from flam_first_zombie_core_dashboard_sql import sql_blocks_markdown as core_sql_blocks_markdown
from flam_first_zombie_dashboard_sql import sql_blocks_markdown
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
)

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
  `PayBuyRet`, `PayBuyRetBenifit`, `PayBuyRetSandBox`, `PayFinish`, `ServerPayLog`, `ep_pay_purchase_finish`, `ep_pay_update_db_finish`
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
  AND e.event IN ('PayBuyRet','PayBuyRetBenifit','PayBuyRetSandBox','PayFinish','ServerPayLog','ep_pay_purchase_finish','ep_pay_update_db_finish')
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
      AND e.event IN ('PayBuyRet','PayBuyRetBenifit','PayBuyRetSandBox','PayFinish','ServerPayLog','ep_pay_purchase_finish','ep_pay_update_db_finish')
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
      AND e.event IN ('PayBuyRet','PayBuyRetBenifit','PayBuyRetSandBox','PayFinish','ServerPayLog','ep_pay_purchase_finish','ep_pay_update_db_finish')
    GROUP BY `小时`
) h2 ON h2.`小时` <= h1.`小时`
GROUP BY h1.`小时`
ORDER BY h1.`小时`
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
- 新增用户使用 `user` 用户日表。
- `dt` 是业务日期分区，格式为 `YYYYMMDD` 数字。
- 注册日期取 `JSON_UNQUOTE(JSON_EXTRACT(userinfo, '$.regdate'))`，格式为 `YYYYMMDD` 字符串。
- 留存标记取后续精确生命周期日快照：D1 读取注册日 +1 天那行的 `remain.remain1='1'`，D3/D7 同理读取注册日 +3/+7 天对应快照。
- 按渠道、系统拆分时，渠道/系统取注册日那一行的 `adinfo` / `deviceinfo`，不要用后续活跃日覆盖新增归因。

## SQL 口径
- 新增用户分母：`userinfo.regdate = user.dt` 的注册日 cohort，按 `uid` 去重。
- D1 留存分子：先固定注册日 cohort，再在该 cohort 的精确次日快照中查同一 `uid` 的 `remain.remain1 = '1'`；不能只读取注册当天，也不要跨多日 `MAX(remain1)`。
- 默认只展示已成熟 cohort：观察截止日取 `user` 表最大 `dt`，D1 默认窗口为 `max_dt - 28` 到 `max_dt - 1`，不要把最新未成熟 cohort 当 0%。
- 不要直接使用 `CURDATE()` 代表数据最大业务日；flam 看板应以 `MAX(user.dt)` 对齐当前可用数据。

## 推荐输出
- `cohort_date`, `new_users`, `d1_retained_users`, `d1_retention_pct`。
- 留存趋势图使用折线图，x 轴 `cohort_date`（展示名“日期”），y 轴 `d1_retention_pct`（展示名“次日留存率”）。
- flam 的 MySQL/ADS 驱动对中文 SQL 别名不稳定，持久看板 SQL 应使用英文别名，图表配置用 `name` 存中文展示名。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对已保存看板中新增、渠道新增、系统新增和新增留存类组件的落地配置。

{sql_blocks_markdown(NEW_USER_RETENTION_VIEW_IDS)}
""",
    },
    {
        "name": "flam 历史看板日期窗口口径",
        "description": "flam / first_zombie 离线历史看板的 MAX(dt) 日期窗口和成熟 cohort 规则。",
        "prompt": """<!-- data-skill-source:flam:first-zombie:historical-date-window -->
# flam 历史看板日期窗口口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于 `核心看板`、`新增看板`、`活跃看板`、`付费概览`、`渠道分析`、`投放看板` 等离线历史看板的日期窗口选择。

## 日期窗口
- 历史看板不能使用 `CURDATE()` / `NOW()` 作为业务数据窗口。flam 业务库是离线分区表，系统自然日和数据最大业务日可能不同。
- 历史趋势默认以对应事实表最大 `dt` 为观察日，取最近 30 个业务分区：`MAX(dt)-29` 到 `MAX(dt)`。
- 指标来自 `user` 表时观察日取 `MAX(user.dt)`；指标来自 `event` 表时观察日取 `MAX(event.dt)`；跨表指标要明确主事实表，不能混用两个表的最大日期。
- 需要计算 D1/D3/D7 留存或 7 日 LTV 时，只展示成熟 cohort：D1 默认截止 `MAX(dt)-1`，D7 默认截止 `MAX(dt)-7`。
- 实时看板继续遵循 `flam 实时数据时区与日期口径` Data Skill 的 UTC+8 规则；不要把实时规则套到历史离线看板。

## 禁止事项
- 不要用系统当前日期过滤离线历史看板。
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
- 历史活跃趋势遵循 `flam 历史看板日期窗口口径`：观察日优先从 `UserActive` 事件按 `dt DESC LIMIT 1` 获取，不使用 `CURDATE()` / `NOW()`，也不要为了取最大分区对大视图做 `MAX(dt)` 全量聚合。
- DAU 展示最近 30 个业务分区；WAU/周登录天数按自然周聚合，观察窗口应扩展到完整周，不能只拿最近 30 天后再按周聚合；MAU 按自然月聚合，观察窗口应扩展到完整月。
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
        "description": "flam / first_zombie 日付费、累计付费、ARPU/ARPPU、付费率、首付、近 7 日累充和 LTV SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:payment-ltv -->
# flam 付费与 LTV 口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于付费概览、ARPU/ARPPU、日充值次数/人数、新增首日付费、累计付费、近 7 日累充、渠道付费、等级段付费和 7 日 LTV。

## 付费与累计
- `user.pay.paytotal` 是用户截至该 `dt` 的累计付费快照，可用于累计付费金额、累计付费用户、当前等级段累计人均付费等快照指标。
- 日付费金额不能直接按日汇总 `paytotal`。日付费金额应按同一用户相邻 `dt` 的 `paytotal` 差分计算，并将负差分截为 0。
- 历史日付费、ARPU/ARPPU 和付费概览 SQL 应避免对 30 天以上用户快照全量使用 `LAG()` 窗口排序；优先用当前日快照按 `uid + 前一日 dt` 关联前日快照计算差分，并只扫描当前窗口内 `paytotal > 0` 的用户行。
- 获取观察日优先使用 `SELECT dt FROM user ORDER BY dt DESC LIMIT 1`，不要为了取最大分区对大视图做 `MAX(dt)` 全量聚合。
- 只有结果需要按渠道/系统等维度拆分时才解析 `adinfo` / `deviceinfo` JSON；ARPU/ARPPU 总览不应在中间层提取未使用的渠道字段。
- 日充值次数优先使用 `event` 表中的付费事件次数：`PayBuyRet`,`PayBuyRetBenifit`,`PayBuyRetSandBox`,`PayFinish`,`ServerPayLog`,`ep_pay_purchase_finish`,`ep_pay_update_db_finish`。
- 日充值用户数使用付费事件用户去重；日新增充值用户数使用用户首次付费事件日期。
- 近 7 日累充排名使用观察日累计 `paytotal` 减去 7 天前累计 `paytotal`，不是取 30 日窗口内 `MAX(paytotal)`。
- ARPU 分母是同日 `UserActive` 活跃用户数，ARPPU 分母是同日付费用户数，二者分母不同。

## 留存与 LTV
- 留存和 LTV 必须先固定注册 cohort，再在后续用户日记录中读取 `remain` 或 `pay` 累计窗口字段。
- `remain.remain1 = 1` 表示 D1 留存，`remain3 = 1`、`remain7 = 1` 分别表示 D3/D7 留存。
- `pay.pay1/pay2/pay3/pay7` 表示注册后当日/第1日/第2日/第7日累计付费窗口。新增首日付费金额固定取注册日快照行的 `pay.pay1` 求和，不要从后续快照 `MAX(pay1)`；7 日 LTV 要以注册 cohort 人数为分母，并只展示 D7 成熟 cohort。

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
- 礼包购买来自 `event` 事件明细表中的付费成功/回调事件：`PayBuyRet`,`PayBuyRetBenifit`,`PayBuyRetSandBox`,`PayFinish`,`ServerPayLog`,`ep_pay_purchase_finish`,`ep_pay_update_db_finish`。
- 礼包名/商品 ID 优先从 `ext.payId` 取，其次 `ext.rechargeId`、`ext.productId`、`ext.goodsId`；都缺失时回退为事件名，避免整行丢失。
- `购买次数` 统计付费事件行数；`购买人数` 统计去重 `uid`。
- 历史窗口遵循 `flam 历史看板日期窗口口径`：以 `event.MAX(dt)` 为观察日，默认最近 30 个业务分区。

## 禁止事项
- 不要漏掉 `ep_pay_update_db_finish`，否则会低估部分实时/支付链路事件。
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
- 默认观察窗口以 `user.MAX(dt)` 为观察日，最近 30 个业务分区；事件窗口与 cohort 窗口一致。
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
- 当前态指标使用 `user` 用户日表的最新完整分区：`MAX(user.dt)`。
- 等级取 `lastinfo.level`，按最新分区上的 `uid` 去重统计。
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
- 首日付费金额固定读取注册日快照 `pay.pay1`；7 日累计付费读取注册日 cohort 的 `pay.pay7`；累计付费读取注册日快照可见的 `pay.paytotal`。
- 历史窗口以 `MAX(user.dt)` 为观察日，默认最近 30 个业务分区；不要使用 `CURDATE()` 或系统当前日期。

## 禁止事项
- 不要用活跃事件行的渠道覆盖注册归因。
- 不要从后续快照 `MAX(pay1)` 推导首日付费。

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
- 周累充分布使用 `user` 用户日快照，但每个自然周内每个用户只取该周最后一条快照，避免把同一用户的多天快照重复计入分布。
- 付费事件集合为 `PayBuyRet`,`PayBuyRetBenifit`,`PayBuyRetSandBox`,`PayFinish`,`ServerPayLog`,`ep_pay_purchase_finish`,`ep_pay_update_db_finish`。
- 商品/礼包标识优先从 `ext.payId` 取，其次 `ext.rechargeId`、`ext.productId`、`ext.goodsId`，均缺失时回退为事件名。
- 周累充分布按累计 `pay.paytotal` 分段；付费事件分布统计事件行数，不从 `paytotal` 差分反推商品。

## 禁止事项
- 不要漏掉 `ep_pay_update_db_finish`。
- 不要按天快照直接累计用户数，必须先做周内用户去重与最新快照筛选。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对付费分布类组件的落地配置。

{remaining_sql_blocks_markdown(PAY_DISTRIBUTION_VIEW_IDS)}
""",
    },
    {
        "name": "flam 活动参与与后续质量口径",
        "description": "flam / first_zombie 活动参与率、人均参与、参与频次、活动后续留存和付费质量 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:activity-quality -->
# flam 活动参与与后续质量口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于活动分析看板中的活动参与率、人均参与次数、等级段参与、周参与频次、活动后续留存和活动后续付费。

## SQL 口径
- 活动参与人数使用活动事件集合中的 `uid` 去重；活动次数使用事件行数。
- 活动参与率的分母为同日 `UserActive` DAU。
- 活动等级段优先读取事件参数 `ext.ed_mainBuildingLevel`。
- 活动后续留存先固定用户首次参与活动日，再在精确 D1/D7 用户快照读取 `remain.remain1/remain7`，并排除 D7 未成熟参与日。
- 活动后续付费先固定用户首次参与活动日，再读取参与日及成熟窗口内的付费字段；不要把所有历史付费用户混入活动参与 cohort。

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
- 单条变化量为 `ext.ed_changeFree + ext.ed_changePaid`。
- 变化量大于 0 计入钻石获取，变化量小于 0 取绝对值计入钻石消耗，二者之和保留为钻石存量变化。
- 路径/原因优先取 `ext.ed_route`，缺失时取 `ext.ed_detailReason`，仍缺失记为“未知”。
- 历史窗口以 `MAX(event.dt)` 为观察日，默认最近 30 个业务分区。

## 禁止事项
- 不要只看免费钻石或只看付费钻石字段；必须把 `ed_changeFree` 与 `ed_changePaid` 合并计算。
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
- 购买行为使用付费事件集合，不使用 `user.pay.paytotal` 直接拆商品。
- 商品/礼包标识优先从 `ext.payId` 取，其次 `ext.rechargeId`、`ext.productId`、`ext.goodsId`。
- 新手礼包识别使用商品标识中的 `new`、`starter`、`新手`、`首充` 等关键词；首购日为该类商品的最早付费事件日期。
- 新手礼包复购率以购买新手礼包用户为 cohort，统计首购后当周、第 1 周、第 2 周是否再次触发付费事件。
- 月卡识别使用商品标识中的 `month` 或 `月卡`，月卡留存以购买用户为 cohort，在购买后第 1/7/14/30 日登录事件中按 `uid` 去重。

## 禁止事项
- 不要把所有付费用户当新手礼包或月卡 cohort。
- 不要用累计付费快照推断具体商品复购。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对礼包复购和月卡留存组件的落地配置。

{remaining_sql_blocks_markdown(GIFT_RETENTION_VIEW_IDS)}
""",
    },
    {
        "name": "flam 出征与演习口径",
        "description": "flam / first_zombie 出征、竞技场、荣耀远征、兵种升级、将领出征和胜率 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:expedition-drill -->
# flam 出征与演习口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于出征数据看板中的出征事件数、兵种升级、平均战力、荣耀远征、出征明细、将领出征、胜率和主城等级演习。

## SQL 口径
- 出征/竞技/演习事件集合为 `WorldMarch`,`WorldMarchRet`,`ActivityWorldBoss`,`ActivityAllianceBossBattleRet`,`honorExpedition`,`ArenaResults`,`TrainingArenaResults`,`multipleArena`。
- 兵种升级使用 `event='ArmyUpgrade'`，兵种优先取 `ext.ed_newArmyId`，其次 `ext.ed_oldArmyId`。
- 将领 ID 优先取 `ext.ed_heroId`，其次取 `ext.captainId`。
- 主城等级优先取事件参数 `ext.ed_mainBuildingLevel`。
- 平均战力优先取 `ext.combatPower`，缺失时取 `ext.captainPower`。
- 胜率使用结果字段 `ext.battleResult` 或 `ext.expeditionDungeonResult`，值为 `win`、`success`、`1`、`胜利` 计为胜利。

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
- 英雄 ID 优先取 `ext.ed_heroId`，其次 `ext.captainId`。
- 英雄等级优先取 `ext.ed_currentLevel`，缺失时取 `ext.ed_heroLevel`。
- 英雄星级优先取 `ext.ed_heroStar`，缺失时取 `ext.ed_newStar`。
- 当前等级分布必须先按 `uid, hero_id` 取最近一条养成事件，再统计用户数；不要把历史升级事件行数当当前等级分布。

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
        "description": "flam / first_zombie 主城等级、建筑/科技升级、兵种招募、加速和主城漏斗 SQL 生成规则。",
        "prompt": f"""<!-- data-skill-source:flam:first-zombie:city-build-growth -->
# flam 主城建设与成长口径

## 适用范围
- 仅适用于当前 flam 数据源 `first_zombie`，datasource_id=3。
- 适用于主城建设看板中的主城平均等级、主城/建筑/科技升级、等级分布、兵种招募、加速和主城升级漏斗。

## SQL 口径
- 当前主城等级类指标使用 `user` 最新快照 `MAX(user.dt)` 的 `lastinfo.blevel`，按 `uid` 去重。
- 主城/建筑升级事件使用 `BuildingUpgrade`,`BuildingIdleUpgrade`；建筑 ID 优先取 `ext.ed_buildingId`，其次 `ext.ed_metaId`。
- 科技升级类事件使用 `BuildingIdleUpgrade`,`HeroSkillUpgrade`,`RadarUpgrade`,`AllianceTechnologyDonation`。
- 兵种招募/升级使用 `event='ArmyUpgrade'`，兵种优先取 `ext.ed_newArmyId`，其次 `ext.ed_oldArmyId`，数量取 `ext.ed_count`。
- 加速使用从 `BuildingUpgrade`,`BuildingIdleUpgrade`,`ArmyUpgrade` 中识别，类型优先取 `ext.ed_detailReason`，其次 `ext.ed_route`。
- 主城升级漏斗使用最新快照主城等级阈值，而不是历史升级事件次数。

## 禁止事项
- 不要把最近 30 天所有用户快照合并后统计当前等级分布。
- 不要把升级事件次数当当前主城等级玩家数。

## 持久看板 SQL
以下 SQL 是本 Data Skill 对主城建设组件的落地配置。

{remaining_sql_blocks_markdown(CITY_BUILD_VIEW_IDS)}
""",
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
          AND tenant_id = %s
          AND position(%s in COALESCE(prompt, '')) > 0
        ORDER BY id
        LIMIT 1
        """,
        (tenant_id, marker),
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


def _delete_stale_skills(cur, *, tenant_id: int) -> list[int]:
    stale_ids: list[int] = []
    for marker in STALE_SKILL_MARKERS:
        cur.execute(
            """
            SELECT id
            FROM custom_prompt
            WHERE tenant_id = %s
              AND type = 'DATA_SKILL'
              AND position(%s in COALESCE(prompt, '')) > 0
            ORDER BY id
            """,
            (tenant_id, marker),
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
               AND position(%s in COALESCE(prompt, '')) > 0
            """,
            (tenant_id, marker),
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
            deleted_stale_ids = _delete_stale_skills(cur, tenant_id=TENANT_ID)
        conn.commit()
    saved = _save_embeddings(ids, TENANT_ID)
    print(f"Upserted flam data skills: {ids}; deleted stale skills: {deleted_stale_ids}; embeddings saved: {saved}")


if __name__ == "__main__":
    main()
