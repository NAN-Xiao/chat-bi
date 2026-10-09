# 游戏数据分析全局知识库

> **用途**：所有 SLG/游戏项目数据分析的统一速查手册。做分析前先读此文档，避免踩坑。
> **维护说明**：每次新项目/新坑都更新到此文档。



> 两库表结构完全一致，仅数据按项目分布。

---

## 📊 三张核心表速查

### 1. `analytics.user` — 用户快照表（每日一份）

**用途**：留存、付费、等级、用户画像分析的主表。

**顶层字段（直接用，不要走 JSON）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| **`uid`** | string | **玩家唯一标识（关联键）** |
| `dt` | string | 日期分区，YYYYMMDD |
| `prod` | string | 项目 ID |
| `userinfo` | JSON | 注册基础信息 |
| `lastinfo` | JSON | 最近状态快照 |
| `remain` | JSON | 留存标签 |
| `level` | JSON | 等级信息（只用 blevel 系列） |
| `pay` | JSON | 付费信息 |
| `allianceinfo` | JSON | 联盟信息 |
| `adinfo` | JSON | 广告归因信息 |
| `abtest` | JSON | AB 测试分组 |
| `power` | — | 战力 |
| `deviceinfo` | JSON | 设备信息 |
| `ids` | JSON | 各类 ID |

**查询规范**：
- 默认查**前一天**的快照：`dt = DATE_FORMAT(DATE_ADD(CURRENT_DATE(), INTERVAL -1 DAY), '%Y%m%d')`
- 新用户筛选：`userinfo->>'$.regtype' = '0'`（0=纯新，1=重玩）

---

### 2. `analytics.event` — 行为事件表（离线，不含当天）

**用途**：行为漏斗、事件分析、行为路径。

**顶层字段（直接用）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| **`uid`** | string | **玩家唯一标识（与 user 表关联键）** |
| `dt` | string | 日期分区 |
| `prod` | string | 项目 ID |
| `time` | bigint | 服务器接收时间戳（毫秒） |
| **`event`** | string | **事件名称** |
| `userinfo` | JSON | 用户信息（同 user 表 userinfo） |
| `currentinfo` | JSON | 事件发生时的玩家状态 |
| `personal` | JSON | **事件参数** |

> **event 表包含 user 表所有字段**（同名字段含义相同），额外增加 event / personal / currentinfo。

**查询规范**：
- 默认查**最近 3 天（不含当天）**，尽量用固定日期区间
- 必须加 `event = 'xxx'` 过滤事件类型
- 事件参数从 `personal` 提取：`personal->>'$.paramName'`
- 事件时状态从 `currentinfo` 提取：`currentinfo->>'$.level'`

---

### 3. `elex_data.event` — 实时行为表（当天增量）

**用途**：当天实时数据查询。

**结构**：与 `analytics.event` 基本相同。

**限制**：
- ✅ 可用：`uid`、`time`、`userinfo`、`currentinfo` 等基础字段
- ❌ 不可用：离线加工的统计字段（留存、累计付费、标签等）

**混合查询**：历史区间用 `analytics.event` + 当天用 `elex_data.event`

---

## 🔑 常用 JSON 字段速查

### userinfo（注册信息）

```sql
userinfo->>'$.country'       -- 国家代码
userinfo->>'$.regdate'       -- 注册日期 YYYYMMDD
userinfo->>'$.regtime'       -- 注册时间戳（毫秒）
userinfo->>'$.regtype'       -- 注册类型：0=纯新, 1=重玩
userinfo->>'$._serverId'     -- 注册服务器ID
userinfo->>'$._appVersion'   -- 应用版本
userinfo->>'$._packageName'  -- 包名
userinfo->>'$._platformType' -- 平台类型
```

### lastinfo（最近状态）

```sql
lastinfo->>'$.blevel'         -- 建筑等级（SLG核心进度指标）
lastinfo->>'$.level'          -- 玩家等级
lastinfo->>'$.lastlogin'      -- 最近登录日期
lastinfo->>'$.regnday'        -- 注册天数（0=当天）
lastinfo->>'$._serverId'      -- 当前服务器ID
lastinfo->>'$._season'        -- 赛季编号
```

### remain（留存标签）

```sql
remain->>'$.remain1'   -- 次留（0=流失, 1=留存）
remain->>'$.remain3'   -- 3日留存
remain->>'$.remain7'   -- 7日留存
remain->>'$.remain14'  -- 14日留存
remain->>'$.remain30'  -- 30日留存
```

> 留存从注册"次日"开始计算。`regnday = 0` 是注册当天。

### pay（付费信息）

```sql
pay->>'$.pay1'         -- 注册首日付费金额
pay->>'$.pay3'         -- 注册3日累计付费
pay->>'$.pay7'         -- 注册7日累计付费
pay->>'$.pay14'        -- 注册14日累计付费
pay->>'$.pay30'        -- 注册30日累计付费
pay->>'$.paytotal'     -- 累计总付费
pay->>'$.firstpaytime' -- 首次付费时间戳
pay->>'$.lastpaytime'  -- 最后付费时间戳
pay->>'$.pay1count'    -- 首日付费次数
```

### level（等级信息）

```sql
level->>'$.blevel1day'   -- 注册第1天建筑等级
level->>'$.blevel3day'   -- 注册第3天建筑等级
level->>'$.blevel7day'   -- 注册第7天建筑等级
```

> ⚠️ 只用 blevel 系列，level1day/level3day/level7day **不使用**。

### adinfo（广告归因）

```sql
adinfo->>'$.mediaSource'    -- 媒体来源（Facebook/Google等）
adinfo->>'$.campaignName'   -- Campaign 名称
adinfo->>'$.campaignId'     -- Campaign ID
adinfo->>'$.adsetName'      -- Adset 名称
adinfo->>'$.adName'         -- 广告名称
adinfo->>'$.adId'           -- 广告 ID
```

**买量方式判定**（基于 campaignName 模式匹配）：
```sql
CASE
  WHEN campaignName = 'Organic'    THEN '自然流量'
  WHEN campaignName LIKE '%_AEO_%' THEN 'AEO'
  WHEN campaignName LIKE '%_VO_%'  THEN 'VO'
  WHEN campaignName LIKE '%_MAI_%' THEN 'MAI'
  ELSE 'other'
END AS ad_channel
```

### allianceinfo（联盟信息）

```sql
allianceinfo->>'$.allianceid'        -- 联盟ID（非空=已加入联盟）
allianceinfo->>'$.alliancename'      -- 联盟名称
allianceinfo->>'$.alliancerank'      -- 联盟内职位
allianceinfo->>'$.current_member'    -- 当前成员数
allianceinfo->>'$.alliancepower'     -- 联盟战力
```

### personal（事件参数，event 表专用）

```sql
-- 付费 ServerPayLog
personal->>'$.orderId'      -- 订单ID
personal->>'$.level'        -- 付费时大本等级
personal->>'$.productid'    -- 礼包ID
personal->>'$.money'        -- 礼包价格

-- 登出 Logout
personal->>'$.ed_playSeconds'  -- 本次在线时长（秒）

-- 活跃度 DailyLivenessAdd
personal->>'$.ed_livenessCount'  -- 活跃度计数

-- 通用
personal->>'$.ed_heroId'      -- 英雄ID
personal->>'$.ed_taskId'      -- 任务ID
personal->>'$.ed_activityId'  -- 活动ID
```

---

## 📐 业务口径规则（强制）

### 留存计算

**成熟度校验**：计算 N 日留存时，用户必须注册满 N 天才能进入分母。

| 留存指标 | 最低门槛 |
|---------|---------|
| remain1（次留） | `regnday >= 1` |
| remain3（3留） | `regnday >= 3` |
| remain7（7留） | `regnday >= 7` |
| remain14（14留） | `regnday >= 14` |

**推荐写法**：
```sql
COUNT(DISTINCT CASE WHEN regnday >= 7 AND remain7 = 1 THEN uid END) AS remain7_users
```

### 付费用户留存口径（强制）

付费用户判定窗口必须与留存窗口对齐：

| 留存指标 | 付费用户判定字段 |
|---------|----------------|
| 次留 remain1 | `pay1 > 0` |
| 3留 remain3 | `pay3 > 0` |
| 7留 remain7 | `pay7 > 0` |
| 14留 remain14 | `pay14 > 0` |
| 30留 remain30 | `pay30 > 0` |

> ⚠️ **禁止**用 `paytotal` 算付费留存——会把注册 N 天后才付费的用户算进来，导致留存率虚高。

### 百分比/转化率计算

```sql
CASE
  WHEN COALESCE(denominator, 0) = 0 THEN 0
  ELSE ROUND(
    COALESCE(CAST(numerator AS double), 0) /
    CAST(denominator AS double) * 100,
    4
  )
END AS metric_rate
```

- 分母为 0 时返回 0
- 用 `double` 避免整数除法
- 保留 4 位小数
- COLUMNMAP 中注明 "(%)"

### 活跃/付费/在线时长的事件来源

| 分析目标 | 事件名 | 来源表 |
|---------|--------|--------|
| 日活跃 | `UserLogin` | analytics.event / elex_data.event |
| 付费行为 | `ServerPayLog` | analytics.event / elex_data.event |
| 在线时长 | `Logout` + `personal.ed_playSeconds` | analytics.event / elex_data.event |

---

## ✍️ SQL 编写规范

### 必加项
1. `dt` 日期过滤（所有表）
2. `prod` 项目过滤（所有表）
3. `event` 事件过滤（event 表）
4. COLUMNMAP 注释（输出结果集的查询）
5. `LIMIT 100`（分析/测试查询）

### WHERE 条件顺序
```
dt → prod → event → 其他条件
```

### 表别名
- 禁止单字母别名（e, u, t, a）
- 用语义化缩写：`usr`、`evt`、`pay_evt`

### 时间戳转可读时间
```sql
FROM_UNIXTIME(FLOOR(time / 1000), '%Y-%m-%d %H:%i:%s') AS trans_time
```

### 日期加减
```sql
CAST(DATE_ADD(DATE('20260101'), INTERVAL 3 DAY) AS bigint)   -- 加3天
CAST(DATE_ADD(DATE('20260101'), INTERVAL -1 DAY) AS bigint)  -- 减1天
```

### COLUMNMAP 规范
```sql
/* COLUMNMAP: 日期=dt, 付费用户数=pay_users, 7留率(%)=remain7_rate */
```

---

## 🔗 user 表与 event 表关联模板

### 圈定用户 → 分析行为
```sql
WITH target_users AS (
  SELECT uid
  FROM analytics.user
  WHERE dt = '20260905'
    AND prod = '110000039'
    AND userinfo->>'$.regdate' >= '20260821'
    AND userinfo->>'$.regdate' <= '20260824'
    AND CAST(pay->>'$.paytotal' AS double) > 0
)
SELECT evt.event, COUNT(*) AS event_cnt
FROM analytics.event evt
INNER JOIN target_users tu ON evt.uid = tu.uid
WHERE evt.dt >= '20260821'
  AND evt.dt <= '20260831'
  AND evt.prod = '110000039'
GROUP BY evt.event
ORDER BY event_cnt DESC
LIMIT 100
```

> **关联键：直接用 `uid = uid`**，不要走 JSON 字段。

---

## 🎯 常见分析场景 SQL 模板

### 新增用户（纯新）
```sql
WHERE prod = 项目id
  AND dt = userinfo->>'$.regdate'
  AND userinfo->>'$.regtype' = '0'
```


### 按国家分组（T1/T2 常用）
```sql
CASE
  WHEN userinfo->>'$.country' = 'US' THEN 'T1_US'
  WHEN userinfo->>'$.country' IN ('DE','GB','FR','AU','CA','NL','BE','ES','AT','SE','NZ','CH','PT','DK','IE','FI') THEN 'T2'
  ELSE 'Other'
END AS country_tier
```

---
