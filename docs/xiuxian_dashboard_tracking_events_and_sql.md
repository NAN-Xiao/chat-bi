# 修仙空间默认看板打点事件与计算 SQL

## 1. 文档范围

本文只整理“修仙”空间以下 5 个默认推荐看板中的打点事件、快照字段和指标计算 SQL：

- 核心看板
- 留存分析
- 新增看板
- 活跃看板
- 渠道分析（业务沟通中也称“渠道看板”）

当前系统库配置范围：

| 配置项 | 值 |
| --- | --- |
| 工作空间 | 修仙 |
| 租户 | `tenant_id=7482727237662281728` |
| 数据源 | `datasource_id=6` |
| 产品 | `prod=110000047` |
| 历史事件表 | `event` |
| 当天实时事件表 | `event_realtime` |
| 用户日快照表 | `user` |
| 看板范围 | `core_dashboard_tree.scope='default'` |
| 组件总数 | 37 |

本文以当前系统库中保存的默认看板 SQL 为准。SQL 中：

- `{{dashboard_start_yyyymmdd}}` 表示看板开始日期，数字格式为 `YYYYMMDD`。
- `{{dashboard_end_yyyymmdd}}` 表示看板结束日期，数字格式为 `YYYYMMDD`。
- 用户数默认按 `COUNT(DISTINCT uid)` 去重；事件次数才统计事件行或订单 ID。

## 2. 打点事件总览

| 业务用途 | 事件名 | 主要字段 | 使用看板 |
| --- | --- | --- | --- |
| 新增用户、注册 cohort | `UserRegister` | `dt`、`uid`、`adinfo`、`deviceinfo`、`userinfo` | 核心、留存、新增、渠道 |
| 活跃用户、DAU/WAU/MAU、留存观察 | `UserActive` | `dt`、`uid`、`adinfo`、`deviceinfo`、`userinfo` | 核心、留存、活跃、渠道 |
| 真实充值交易 | `ServerPayLog` | `dt`、`uid`、`personal.money`、`personal.orderId`、`personal.productid` | 核心、留存、渠道 |

修仙这 5 个看板的核心统计只依赖以上 3 个归一化事件。支付流程事件不能代替 `ServerPayLog` 计算收入、真实充值人数或真实订单数。

## 3. 通用字段口径

### 3.1 渠道

```sql
COALESCE(
    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.mediaSource')), ''),
    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.campaignName')), ''),
    '未知'
)
```

渠道优先使用 `mediaSource`，为空时使用 `campaignName`，仍为空时归为“未知”。注册和新增留存必须使用注册事件行的渠道，不能被后续活跃事件覆盖。

### 3.2 系统

```sql
COALESCE(
    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.deviceinfo, '$._platform')), ''),
    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.userinfo, '$._platformType')), ''),
    '未知'
)
```

### 3.3 国家

```sql
COALESCE(
    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.userinfo, '$.country')), ''),
    '未知'
)
```

### 3.4 充值与快照字段

```sql
-- 真实充值金额
CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')), '') AS DECIMAL(18, 4))

-- 真实订单 ID
NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.orderId')), '')

-- 礼包/商品 ID
NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.productid')), '')

-- 注册用户首日累计付费
COALESCE(
    CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.pay1')), '') AS DECIMAL(18, 4)),
    0
)

-- 用户累计付费快照
COALESCE(
    CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.paytotal')), '') AS DECIMAL(18, 4)),
    0
)

-- 首次付费时间，毫秒时间戳
CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.firstpaytime')), '') AS DECIMAL(18, 0))
```

`event.personal.money` 是真实交易流水金额；`user.pay.pay1` 是注册 cohort 首日累计付费；`user.pay.paytotal` 是截至快照日的累计付费。三者不可混用。

## 4. 看板组件清单

### 4.1 核心看板

看板 ID：`afe201c9762c448aa0495f3508c01793`

| 组件 | 组件 ID | 事件/数据来源 | 计算口径 | SQL 编号 |
| --- | --- | --- | --- | --- |
| 活跃用户 | `c3d6ca851f8150ba94d73a83ca18b438` | `event_realtime.UserActive` | 当天实时活跃用户去重数 | SQL-01 |
| 新增用户 | `2ca07023c33d514eaa07977425ee7f53` | `event_realtime.UserRegister` | 当天实时注册用户去重数 | SQL-02 |
| 充值人数 | `f212cbcd03a15590a39519e874a1a6f4` | `event_realtime.ServerPayLog` | 当天实时充值用户去重数 | SQL-03 |
| 充值总额 | `5bb72c937f565b7295b3bf4d1b746496` | `event_realtime.ServerPayLog.personal.money` | 当天实时收入之和，除以 10000 展示为“万” | SQL-04 |
| ARPU与ARPPU | `22d89d4a69224e53994d21fb44b376aa` | `ServerPayLog`、`UserActive` | `ARPU=收入/活跃用户数`；`ARPPU=收入/付费用户数` | SQL-05 |
| 日付费率 | `95d8497afac14f0a90342031fb43bc04` | `UserActive`、`ServerPayLog` | 当天同时活跃且付费的用户数/当天活跃用户数 | SQL-06 |
| DAU趋势 | `6b458210dec64fdc8c067b301272f347` | `UserActive` | 每日活跃用户去重数 | SQL-07 |
| 新增用户趋势 | `1c5288d1fe144ddea2b9e82c5ac72b24` | `UserRegister` | 每日注册用户去重数 | SQL-08 |
| 累计付费用户趋势 | `f499305aa9b44a209cbe72cb68985a46` | `user.pay.paytotal` | 每日快照中累计付费大于 0 的用户数 | SQL-09 |
| 每日渠道新增用户 | `8683537b4c2641afa1cefb2dec8dfb06` | `UserRegister` | 按日期、注册渠道统计新增用户数 | SQL-10 |
| 渠道累计付费排行 | `304e66bb74254b9e88d8711ce33d94cc` | `ServerPayLog` | 所选窗口按渠道汇总真实充值金额 | SQL-11 |
| 礼包购买情况 | `bcd7dc9ca6c349909fa74c8d4b0502d7` | `ServerPayLog` | 按 `personal.productid` 统计交易行数和购买用户数 | SQL-12 |
| 当前等级分布 | `7f71477b49404ad289485f4f22d34c2f` | 目标日期 `user.lastinfo.level` | 用户等级分桶统计 | SQL-13 |
| 各渠道新增留存 | `f99d0fb5f3624192953bdbfa31549abd` | `UserRegister`、`UserActive` | 渠道注册 cohort 的 D1/D3/D7 精确日留存 | SQL-14 |
| 新增用户ARPU与ARPPU | `2192510609759838208` | `UserRegister`、注册日 `user.pay.pay1` | 新增 ARPU=首日付费/新增人数；新增 ARPPU=首日付费/新增付费人数 | SQL-15 |

### 4.2 留存分析

看板 ID：`32909e56ee174a2a9d8226be17d51ddf`

| 组件 | 组件 ID | Cohort | 观察事件 | 计算口径 | SQL 编号 |
| --- | --- | --- | --- | --- | --- |
| 各渠道新增留存 | `531bc723e3cb42f0a1fe2c412d7f05b0` | `UserRegister`，按注册渠道 | `UserActive` | D1/D3/D7 活跃人数/注册人数 | SQL-14 |
| 各渠道活跃留存 | `464bc0c1f62049a5b2562fd09d699640` | 当日 `UserActive`，按渠道 | `UserActive` | D1/D3/D7 仍活跃人数/当日活跃人数 | SQL-16 |
| 各渠道新增用户次日留存趋势 | `57c366462db9418ba14fcde0febeb18d` | `UserRegister`，按注册渠道 | `UserActive` | 注册次日活跃人数/注册人数 | SQL-17 |
| 各渠道付费留存 | `2194312685934518272` | 当日 `ServerPayLog` 付费用户，按交易渠道 | `UserActive` | D1/D3/D7 活跃人数/当日付费人数 | SQL-18 |
| 各渠道新增付费留存 | `2194313160293523456` | `user.pay.firstpaytime` 等于快照日的首次付费用户 | `UserActive` | D1/D3/D7 活跃人数/新增付费人数 | SQL-19 |

### 4.3 新增看板

看板 ID：`b09e4d57f57b41859a0c2d4609f80f26`

| 组件 | 组件 ID | 事件/数据来源 | 计算口径 | SQL 编号 |
| --- | --- | --- | --- | --- |
| 新增用户数 | `bdc788729cbc4157bfe3046170c1f92a` | `UserRegister` | 每日注册用户去重数 | SQL-08 |
| 每日渠道新增用户 | `b687a5175da64fc3a3d37ee9a0ec12b2` | `UserRegister` | 按日期、注册渠道统计新增用户数 | SQL-10 |
| 新增用户数（按系统） | `10d4c025e0bf4d9a9f3bd60194cdabb0` | `UserRegister` | 按日期、注册事件系统统计新增用户数 | SQL-20 |
| 新增用户次日留存率 | `b0f27793e48349c1a6a7fbf40ff03ffd` | `UserRegister`、`UserActive` | 注册次日精确活跃人数/注册人数 | SQL-21 |
| 新增首日付费金额 | `a6eb26710f7b4dc6ab69ded704c32fee` | `UserRegister`、注册日 `user.pay.pay1` | 按注册日期汇总首日累计付费 | SQL-22 |

### 4.4 活跃看板

看板 ID：`c68e08ee9b4a4be59c3c8fbbe918affd`

| 组件 | 组件 ID | 事件/数据来源 | 计算口径 | SQL 编号 |
| --- | --- | --- | --- | --- |
| DAU | `e4344fa52c564002931ce13ea3657027` | `UserActive` | 每日活跃用户去重数 | SQL-07 |
| WAU | `0369399df2eb4a3299d6d34f9663101b` | `UserActive` | 自然周内活跃用户去重数 | SQL-23 |
| MAU | `ad88b71e2b08435c8c7a0606c5579f30` | `UserActive` | 自然月内活跃用户去重数 | SQL-24 |
| 活跃用户生命周期构成 | `fd9a8fe1127e4f21bf1809a6560ec6e2` | `UserActive`、同日用户快照 | 按 `lastinfo.regnday` 划分生命周期 | SQL-25 |
| 活跃用户数（按渠道） | `816451c6645a4451b7e85bbfb74d7ee7` | `UserActive` | 按日期、活跃事件渠道统计活跃用户 | SQL-26 |
| 活跃用户数（按系统） | `6c96d753e08742579580d52764d5589b` | `UserActive` | 按日期、活跃事件系统统计活跃用户 | SQL-27 |
| 周登录天数分布 | `d4675e033a9c4d4881264a66861b066e` | `UserActive` | 先算每用户每周活跃天数，再统计 1 至 7 天人数 | SQL-28 |

### 4.5 渠道分析

看板 ID：`a34aef6cb7214f7fa23e5846a0a66236`

| 组件 | 组件 ID | 事件/数据来源 | 计算口径 | SQL 编号 |
| --- | --- | --- | --- | --- |
| 每日渠道新增用户 | `918d4fd1c4d649d5bae371828928f409` | `UserRegister` | 按日期、注册渠道统计新增用户 | SQL-10 |
| 活跃用户数（按渠道） | `2ae501be08934d758f82802abf016059` | `UserActive` | 按日期、渠道统计活跃用户 | SQL-26 |
| 付费用户数（按渠道） | `eba39b8352a34136872404c16fbd17a9` | `ServerPayLog` | 按日期、交易渠道统计付费用户 | SQL-29 |
| 付费金额（按渠道） | `9eff78876b1b405385f96d8559a286a8` | `ServerPayLog.personal.money` | 按日期、交易渠道汇总真实充值金额 | SQL-30 |
| 各渠道新增留存 | `e797a8af6785452e9fdcee7d80786b6e` | `UserRegister`、`UserActive` | 渠道注册 cohort 的 D1/D3/D7 精确日留存 | SQL-14 |

## 5. 核心计算 SQL

以下 SQL 按指标口径去重。多个组件引用同一编号时应保持相同业务定义。

### SQL-01 当天实时活跃用户

```sql
SELECT COUNT(DISTINCT uid) AS `活跃用户`
FROM `event_realtime`
WHERE dt = CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
  AND prod = 110000047
  AND event = 'UserActive';
```

### SQL-02 当天实时新增用户

```sql
SELECT COUNT(DISTINCT uid) AS `新增用户`
FROM `event_realtime`
WHERE dt = CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
  AND prod = 110000047
  AND event = 'UserRegister';
```

### SQL-03 当天实时充值人数

```sql
SELECT COUNT(DISTINCT uid) AS `充值人数`
FROM `event_realtime`
WHERE dt = CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
  AND prod = 110000047
  AND event = 'ServerPayLog';
```

### SQL-04 当天实时充值总额

```sql
SELECT ROUND(
           COALESCE(SUM(CAST(NULLIF(NULLIF(
               JSON_UNQUOTE(JSON_EXTRACT(personal, '$.money')), ''
           ), 'null') AS DECIMAL(18, 4))), 0) / 10000,
           2
       ) AS `充值总额（万）`
FROM `event_realtime`
WHERE dt = CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
  AND prod = 110000047
  AND event = 'ServerPayLog';
```

### SQL-05 ARPU 与 ARPPU

```sql
WITH daily_pay AS (
    SELECT e.dt,
           SUM(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')), '') AS DECIMAL(18, 4))) AS pay_amount,
           COUNT(DISTINCT e.uid) AS pay_users
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'ServerPayLog'
    GROUP BY e.dt
), daily_active AS (
    SELECT e.dt, COUNT(DISTINCT e.uid) AS active_users
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'UserActive'
    GROUP BY e.dt
)
SELECT STR_TO_DATE(CAST(a.dt AS CHAR), '%Y%m%d') AS `日期`,
       ROUND(COALESCE(p.pay_amount, 0) / NULLIF(a.active_users, 0), 2) AS `ARPU`,
       ROUND(COALESCE(p.pay_amount, 0) / NULLIF(p.pay_users, 0), 2) AS `ARPPU`
FROM daily_active a
LEFT JOIN daily_pay p ON p.dt = a.dt
ORDER BY a.dt;
```

### SQL-06 日付费率

```sql
WITH user_day_flags AS (
    SELECT e.dt,
           e.uid,
           MAX(CASE WHEN e.event = 'UserActive' THEN 1 ELSE 0 END) AS is_active,
           MAX(CASE WHEN e.event = 'ServerPayLog' THEN 1 ELSE 0 END) AS is_payer
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event IN ('UserActive', 'ServerPayLog')
    GROUP BY e.dt, e.uid
)
SELECT STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS `日期`,
       SUM(is_active) AS `活跃用户数`,
       SUM(CASE WHEN is_active = 1 AND is_payer = 1 THEN 1 ELSE 0 END) AS `活跃付费用户数`,
       ROUND(
           SUM(CASE WHEN is_active = 1 AND is_payer = 1 THEN 1 ELSE 0 END)
           / NULLIF(SUM(is_active), 0) * 100,
           2
       ) AS `活跃用户付费率`
FROM user_day_flags
WHERE is_active = 1
GROUP BY dt
ORDER BY dt;
```

### SQL-07 DAU

```sql
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       COUNT(DISTINCT e.uid) AS `DAU`
FROM `event` e
WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND e.prod = 110000047
  AND e.event = 'UserActive'
GROUP BY e.dt
ORDER BY e.dt;
```

### SQL-08 每日新增用户

```sql
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       COUNT(DISTINCT e.uid) AS `新增用户数`
FROM `event` e
WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND e.prod = 110000047
  AND e.event = 'UserRegister'
GROUP BY e.dt
ORDER BY e.dt;
```

### SQL-09 累计付费用户趋势

```sql
SELECT STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d') AS `日期`,
       COUNT(DISTINCT CASE
           WHEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.paytotal')), '') AS DECIMAL(18, 4)), 0) > 0
           THEN u.uid
       END) AS `累计付费用户数`
FROM `user` u
WHERE u.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND u.prod = 110000047
GROUP BY u.dt
ORDER BY u.dt;
```

### SQL-10 每日渠道新增用户

```sql
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       COALESCE(
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.mediaSource')), ''),
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.campaignName')), ''),
           '未知'
       ) AS `渠道`,
       COUNT(DISTINCT e.uid) AS `新增用户数`
FROM `event` e
WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND e.prod = 110000047
  AND e.event = 'UserRegister'
GROUP BY e.dt, `渠道`
ORDER BY e.dt, `渠道`;
```

### SQL-11 渠道累计付费排行

```sql
SELECT COALESCE(
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.mediaSource')), ''),
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.campaignName')), ''),
           '未知'
       ) AS `渠道`,
       ROUND(SUM(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')), '') AS DECIMAL(18, 4))), 2)
           AS `累计付费金额`
FROM `event` e
WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND e.prod = 110000047
  AND e.event = 'ServerPayLog'
GROUP BY `渠道`
ORDER BY `累计付费金额` DESC;
```

### SQL-12 礼包购买情况

```sql
SELECT NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.productid')), '') AS `购买礼包ID`,
       COUNT(*) AS `购买次数`,
       COUNT(DISTINCT e.uid) AS `购买人数`
FROM `event` e
WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND e.prod = 110000047
  AND e.event = 'ServerPayLog'
  AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.productid')), '') IS NOT NULL
GROUP BY `购买礼包ID`
ORDER BY `购买次数` DESC;
```

### SQL-13 当前等级分布

```sql
WITH user_level AS (
    SELECT u.uid,
           COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.level')), '') AS DECIMAL(18, 4)), 0) AS level_value
    FROM `user` u
    WHERE u.dt = {{dashboard_end_yyyymmdd}}
      AND u.prod = 110000047
)
SELECT CASE
           WHEN level_value >= 30 THEN '30+'
           ELSE CONCAT(FLOOR(level_value / 3) * 3, '-', FLOOR(level_value / 3) * 3 + 2)
       END AS `等级区间`,
       COUNT(DISTINCT uid) AS `用户数`
FROM user_level
GROUP BY `等级区间`
ORDER BY CASE
    WHEN `等级区间` = '30+' THEN 999
    ELSE CAST(SUBSTRING_INDEX(`等级区间`, '-', 1) AS SIGNED)
END;
```

### SQL-14 各渠道新增 D1/D3/D7 留存

```sql
WITH cohort AS (
    SELECT e.dt AS cohort_dt,
           e.uid,
           COALESCE(
               NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.mediaSource')), ''),
               NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.campaignName')), ''),
               '未知'
           ) AS channel
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'UserRegister'
    GROUP BY e.dt, e.uid, channel
), active AS (
    SELECT e.dt, e.uid
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'UserActive'
    GROUP BY e.dt, e.uid
)
SELECT STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d') AS `日期`,
       c.channel AS `渠道`,
       COUNT(DISTINCT c.uid) AS `新增用户数`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = CAST(DATE_FORMAT(DATE_ADD(
           STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY
       ), '%Y%m%d') AS SIGNED) THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `D1`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = CAST(DATE_FORMAT(DATE_ADD(
           STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d'), INTERVAL 3 DAY
       ), '%Y%m%d') AS SIGNED) THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `D3`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = CAST(DATE_FORMAT(DATE_ADD(
           STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY
       ), '%Y%m%d') AS SIGNED) THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `D7`
FROM cohort c
LEFT JOIN active a ON a.uid = c.uid
GROUP BY c.cohort_dt, c.channel
ORDER BY c.cohort_dt, c.channel;
```

未成熟的 D1/D3/D7 cohort 应返回 `NULL`；完整保存 SQL通过日期骨架和观察截止日分别判断成熟度。

### SQL-15 新增用户 ARPU 与 ARPPU

```sql
WITH new_users AS (
    SELECT e.dt, e.uid
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'UserRegister'
    GROUP BY e.dt, e.uid
), new_user_payment AS (
    SELECT n.dt,
           n.uid,
           COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.pay1')), '') AS DECIMAL(18, 4)), 0)
               AS first_day_payment
    FROM new_users n
    JOIN `user` u
      ON u.prod = 110000047
     AND u.dt = n.dt
     AND u.uid = n.uid
     AND CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.userinfo, '$.regdate')), '') AS SIGNED) = n.dt
)
SELECT STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS `日期`,
       COUNT(DISTINCT uid) AS `新增用户数`,
       COUNT(DISTINCT CASE WHEN first_day_payment > 0 THEN uid END) AS `新增付费用户数`,
       ROUND(SUM(first_day_payment), 2) AS `新增首日付费金额`,
       ROUND(SUM(first_day_payment) / NULLIF(COUNT(DISTINCT uid), 0), 2) AS `新增用户ARPU`,
       ROUND(SUM(first_day_payment)
             / NULLIF(COUNT(DISTINCT CASE WHEN first_day_payment > 0 THEN uid END), 0), 2)
           AS `新增用户ARPPU`
FROM new_user_payment
GROUP BY dt
ORDER BY dt;
```

### SQL-16 各渠道活跃留存

```sql
WITH cohort AS (
    SELECT e.dt AS cohort_dt,
           e.uid,
           COALESCE(
               NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.mediaSource')), ''),
               NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.campaignName')), ''),
               '未知'
           ) AS channel
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'UserActive'
    GROUP BY e.dt, e.uid, channel
), active AS (
    SELECT e.dt, e.uid
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'UserActive'
    GROUP BY e.dt, e.uid
)
SELECT c.cohort_dt AS `日期`, c.channel AS `渠道`,
       COUNT(DISTINCT c.uid) AS `活跃用户数`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = CAST(DATE_FORMAT(DATE_ADD(
           STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY
       ), '%Y%m%d') AS SIGNED) THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `D1`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = CAST(DATE_FORMAT(DATE_ADD(
           STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d'), INTERVAL 3 DAY
       ), '%Y%m%d') AS SIGNED) THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `D3`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = CAST(DATE_FORMAT(DATE_ADD(
           STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY
       ), '%Y%m%d') AS SIGNED) THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `D7`
FROM cohort c
LEFT JOIN active a ON a.uid = c.uid
GROUP BY c.cohort_dt, c.channel;
```

### SQL-17 各渠道新增用户次日留存

```sql
WITH registers AS (
    SELECT e.dt AS reg_dt,
           e.uid,
           COALESCE(
               NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.mediaSource')), ''),
               NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.campaignName')), ''),
               '未知'
           ) AS channel
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'UserRegister'
)
SELECT r.reg_dt AS `日期`,
       r.channel AS `渠道`,
       COUNT(DISTINCT r.uid) AS `新增用户数`,
       COUNT(DISTINCT a.uid) AS `次日留存用户数`,
       ROUND(COUNT(DISTINCT a.uid) / NULLIF(COUNT(DISTINCT r.uid), 0) * 100, 2) AS `次日留存率`
FROM registers r
LEFT JOIN `event` a
  ON a.uid = r.uid
 AND a.dt = CAST(DATE_FORMAT(DATE_ADD(
     STR_TO_DATE(CAST(r.reg_dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY
 ), '%Y%m%d') AS SIGNED)
 AND a.prod = 110000047
 AND a.event = 'UserActive'
GROUP BY r.reg_dt, r.channel;
```

### SQL-18 各渠道付费留存

```sql
WITH payer_cohort AS (
    SELECT e.dt AS cohort_dt,
           e.uid,
           COALESCE(
               NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.mediaSource')), ''),
               NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.campaignName')), ''),
               '未知'
           ) AS channel
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'ServerPayLog'
    GROUP BY e.dt, e.uid, channel
), active AS (
    SELECT e.dt, e.uid
    FROM `event` e
    WHERE e.prod = 110000047 AND e.event = 'UserActive'
    GROUP BY e.dt, e.uid
)
SELECT cohort_dt AS `日期`, channel AS `渠道`,
       COUNT(DISTINCT p.uid) AS `付费用户数`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = CAST(DATE_FORMAT(DATE_ADD(
           STR_TO_DATE(CAST(p.cohort_dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY
       ), '%Y%m%d') AS SIGNED) THEN p.uid END) / NULLIF(COUNT(DISTINCT p.uid), 0) * 100, 2) AS `D1`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = CAST(DATE_FORMAT(DATE_ADD(
           STR_TO_DATE(CAST(p.cohort_dt AS CHAR), '%Y%m%d'), INTERVAL 3 DAY
       ), '%Y%m%d') AS SIGNED) THEN p.uid END) / NULLIF(COUNT(DISTINCT p.uid), 0) * 100, 2) AS `D3`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = CAST(DATE_FORMAT(DATE_ADD(
           STR_TO_DATE(CAST(p.cohort_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY
       ), '%Y%m%d') AS SIGNED) THEN p.uid END) / NULLIF(COUNT(DISTINCT p.uid), 0) * 100, 2) AS `D7`
FROM payer_cohort p
LEFT JOIN active a ON a.uid = p.uid
GROUP BY cohort_dt, channel;
```

### SQL-19 各渠道新增付费留存

```sql
WITH first_payer_cohort AS (
    SELECT u.dt AS cohort_dt,
           u.uid,
           COALESCE(
               NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.adinfo, '$.mediaSource')), ''),
               NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.adinfo, '$.campaignName')), ''),
               '未知'
           ) AS channel
    FROM `user` u
    WHERE u.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND u.prod = 110000047
      AND CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.firstpaytime')), '') AS DECIMAL(18, 0)) > 0
      AND u.dt = CAST(DATE_FORMAT(FROM_UNIXTIME(
          CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.firstpaytime')), '') AS DECIMAL(18, 0)) / 1000
      ), '%Y%m%d') AS SIGNED)
), active AS (
    SELECT e.dt, e.uid
    FROM `event` e
    WHERE e.prod = 110000047 AND e.event = 'UserActive'
    GROUP BY e.dt, e.uid
)
SELECT cohort_dt AS `日期`, channel AS `渠道`,
       COUNT(DISTINCT p.uid) AS `新增付费用户数`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = CAST(DATE_FORMAT(DATE_ADD(
           STR_TO_DATE(CAST(p.cohort_dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY
       ), '%Y%m%d') AS SIGNED) THEN p.uid END) / NULLIF(COUNT(DISTINCT p.uid), 0) * 100, 2) AS `D1`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = CAST(DATE_FORMAT(DATE_ADD(
           STR_TO_DATE(CAST(p.cohort_dt AS CHAR), '%Y%m%d'), INTERVAL 3 DAY
       ), '%Y%m%d') AS SIGNED) THEN p.uid END) / NULLIF(COUNT(DISTINCT p.uid), 0) * 100, 2) AS `D3`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = CAST(DATE_FORMAT(DATE_ADD(
           STR_TO_DATE(CAST(p.cohort_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY
       ), '%Y%m%d') AS SIGNED) THEN p.uid END) / NULLIF(COUNT(DISTINCT p.uid), 0) * 100, 2) AS `D7`
FROM first_payer_cohort p
LEFT JOIN active a ON a.uid = p.uid
GROUP BY cohort_dt, channel;
```

首次付费日来自 `firstpaytime`，不能用分析窗口内首次出现 `ServerPayLog` 的日期替代。

### SQL-20 按系统新增用户

```sql
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       COALESCE(
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.deviceinfo, '$._platform')), ''),
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.userinfo, '$._platformType')), ''),
           '未知'
       ) AS `系统`,
       COUNT(DISTINCT e.uid) AS `新增用户数`
FROM `event` e
WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND e.prod = 110000047
  AND e.event = 'UserRegister'
GROUP BY e.dt, `系统`
ORDER BY e.dt, `系统`;
```

### SQL-21 新增用户次日留存

```sql
WITH cohort AS (
    SELECT e.dt AS cohort_dt, e.uid
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'UserRegister'
    GROUP BY e.dt, e.uid
), active AS (
    SELECT e.dt, e.uid
    FROM `event` e
    WHERE e.prod = 110000047 AND e.event = 'UserActive'
    GROUP BY e.dt, e.uid
)
SELECT STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d') AS `日期`,
       COUNT(DISTINCT c.uid) AS `新增用户数`,
       COUNT(DISTINCT a.uid) AS `次日留存用户数`,
       ROUND(COUNT(DISTINCT a.uid) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `次日留存率`
FROM cohort c
LEFT JOIN active a
  ON a.uid = c.uid
 AND a.dt = CAST(DATE_FORMAT(DATE_ADD(
     STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY
 ), '%Y%m%d') AS SIGNED)
GROUP BY c.cohort_dt
ORDER BY c.cohort_dt;
```

### SQL-22 新增首日付费金额

```sql
WITH cohort AS (
    SELECT e.dt AS cohort_dt,
           e.uid,
           COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.pay1')), '') AS DECIMAL(18, 4)), 0) AS pay1
    FROM `event` e
    JOIN `user` u ON u.prod = e.prod AND u.dt = e.dt AND u.uid = e.uid
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'UserRegister'
      AND CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.userinfo, '$.regdate')), '') AS SIGNED) = e.dt
)
SELECT STR_TO_DATE(CAST(cohort_dt AS CHAR), '%Y%m%d') AS `日期`,
       ROUND(SUM(pay1), 2) AS `新增首日付费金额`
FROM cohort
GROUP BY cohort_dt
ORDER BY cohort_dt;
```

### SQL-23 WAU

```sql
SELECT DATE_SUB(
           STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'),
           INTERVAL WEEKDAY(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d')) DAY
       ) AS `周`,
       COUNT(DISTINCT e.uid) AS `WAU`
FROM `event` e
WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND e.prod = 110000047
  AND e.event = 'UserActive'
GROUP BY `周`
ORDER BY `周`;
```

### SQL-24 MAU

```sql
SELECT DATE_FORMAT(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), '%Y-%m') AS `月份`,
       COUNT(DISTINCT e.uid) AS `MAU`
FROM `event` e
WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND e.prod = 110000047
  AND e.event = 'UserActive'
GROUP BY `月份`
ORDER BY `月份`;
```

### SQL-25 活跃用户生命周期构成

```sql
WITH active_uid AS (
    SELECT e.dt, e.uid
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'UserActive'
    GROUP BY e.dt, e.uid
), active_snapshot AS (
    SELECT a.dt,
           a.uid,
           COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.regnday')), '') AS DECIMAL(18, 4)), 0)
               AS regnday
    FROM active_uid a
    LEFT JOIN `user` u ON u.uid = a.uid AND u.dt = a.dt AND u.prod = 110000047
)
SELECT STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS `日期`,
       CASE
           WHEN regnday <= 1 THEN '新增期'
           WHEN regnday <= 7 THEN '成长期'
           WHEN regnday <= 30 THEN '稳定期'
           ELSE '成熟期'
       END AS `生命周期`,
       COUNT(DISTINCT uid) AS `活跃用户数`
FROM active_snapshot
GROUP BY dt, `生命周期`
ORDER BY dt, `生命周期`;
```

### SQL-26 按渠道活跃用户

```sql
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       COALESCE(
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.mediaSource')), ''),
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.campaignName')), ''),
           '未知'
       ) AS `渠道`,
       COUNT(DISTINCT e.uid) AS `活跃用户数`
FROM `event` e
WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND e.prod = 110000047
  AND e.event = 'UserActive'
GROUP BY e.dt, `渠道`
ORDER BY e.dt, `渠道`;
```

### SQL-27 按系统活跃用户

```sql
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       COALESCE(
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.deviceinfo, '$._platform')), ''),
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.userinfo, '$._platformType')), ''),
           '未知'
       ) AS `系统`,
       COUNT(DISTINCT e.uid) AS `活跃用户数`
FROM `event` e
WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND e.prod = 110000047
  AND e.event = 'UserActive'
GROUP BY e.dt, `系统`
ORDER BY e.dt, `系统`;
```

### SQL-28 周登录天数分布

```sql
WITH user_week AS (
    SELECT DATE_SUB(
               STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'),
               INTERVAL WEEKDAY(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d')) DAY
           ) AS week_start,
           e.uid,
           COUNT(DISTINCT e.dt) AS login_days
    FROM `event` e
    WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND e.prod = 110000047
      AND e.event = 'UserActive'
    GROUP BY week_start, e.uid
)
SELECT week_start AS `周`,
       SUM(login_days = 1) AS `1天`,
       SUM(login_days = 2) AS `2天`,
       SUM(login_days = 3) AS `3天`,
       SUM(login_days = 4) AS `4天`,
       SUM(login_days = 5) AS `5天`,
       SUM(login_days = 6) AS `6天`,
       SUM(login_days >= 7) AS `7天`
FROM user_week
GROUP BY week_start
ORDER BY week_start;
```

### SQL-29 按渠道付费用户数

```sql
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       COALESCE(
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.mediaSource')), ''),
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.campaignName')), ''),
           '未知'
       ) AS `渠道`,
       COUNT(DISTINCT e.uid) AS `付费用户数`
FROM `event` e
WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND e.prod = 110000047
  AND e.event = 'ServerPayLog'
GROUP BY e.dt, `渠道`
ORDER BY e.dt, `渠道`;
```

### SQL-30 按渠道付费金额

```sql
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       COALESCE(
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.mediaSource')), ''),
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.campaignName')), ''),
           '未知'
       ) AS `渠道`,
       ROUND(SUM(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')), '') AS DECIMAL(18, 4))), 2)
           AS `付费金额`
FROM `event` e
WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND e.prod = 110000047
  AND e.event = 'ServerPayLog'
GROUP BY e.dt, `渠道`
ORDER BY e.dt, `渠道`;
```

## 6. 口径注意事项

1. 核心看板顶部 4 张指标卡读取 `event_realtime` 当天数据；历史趋势读取 `event` 或 `user`，两类数据不能直接拼接为同一口径。
2. “日付费率”是当天同时存在 `UserActive` 和 `ServerPayLog` 的用户占当天活跃用户的比例，不是累计付费用户占全部用户的比例。
3. 普通收入只汇总 `ServerPayLog.personal.money`；`PayBuyRet` 等流程事件不代表真实收入。
4. 新增 ARPU、ARPPU 和新增首日付费使用注册日 `user.pay.pay1`，不是注册用户后续全生命周期收入。
5. 累计付费用户趋势读取每日 `user.pay.paytotal` 快照；渠道累计付费排行则汇总所选窗口内 `ServerPayLog.personal.money`，两者的“累计”对象不同。
6. 新增留存分母固定为 `UserRegister` cohort；活跃留存、付费留存、新增付费留存必须分别固定自己的 cohort，不能混用。
7. 首次付费日以 `user.pay.firstpaytime` 为准，不能用分析窗口内第一次出现 `ServerPayLog` 的日期替代。
8. 留存必须匹配 cohort 后精确第 N 日。未成熟 cohort 返回 `NULL`；已经成熟但无人留存时才返回 0。
9. 渠道使用 `mediaSource -> campaignName -> 未知` 的固定优先级，不得静默替换成其他字段。
10. `dt` 是 `YYYYMMDD` 数字分区；跨月、跨年计算必须先转日期再加天数，不能直接做 `dt + 1`。

## 7. 权威配置来源

- 当前系统库：`core_dashboard` 与 `core_dashboard_tree`
- 修仙工作空间范围：`tools/xiuxian_dashboard_snapshot.py`
- 修仙 Data Skill 主题目录：`tools/xiuxian_dashboard_skill_catalog.py`
- 修仙 Data Skills：`tools/seed_xiuxian_data_skills.py`
- 核心看板实时指标：`tools/add_xiuxian_core_dashboard_realtime_metrics.py`
- 核心看板真实交易修复：`tools/xiuxian_serverpaylog_core_dashboard_repair.py`

系统库是当前实际展示配置；脚本与 Data Skill 是后续发布和修复的代码来源。两者出现差异时，应先核对系统库当前组件 SQL，再同步修复脚本与相应 Data Skill，防止后续发布恢复旧口径。
