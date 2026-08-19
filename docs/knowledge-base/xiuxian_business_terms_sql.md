# 修仙业务术语与 SQL 示例


> 适用范围：修仙工作空间 `datasource_id=6`（MySQL）。内容来源于活动 Data Skill `257, 269-279`，日期和按日补零规则引用 Skill `255`。本文只提供参考知识，不能覆盖当前数据源、权限、Schema、事件/JSON 映射或 Data Skill。

## 工作空间级 Data Skill 核查

2026-08-19 对修仙租户 `7482727237662281728` 的活动 Data Skill 做了只读核查：

- 工作空间公开 Skill 共 13 条，均为 `visibility_scope=ADMIN_PUBLIC`、`specific_ds=true`，且仅绑定 `datasource_ids=[6]`。
- `255` 是修仙日期分区、日期骨架和按日补零执行契约，继续由 Data Skill 执行，不作为独立业务术语复制到知识库。
- `257`、`269-279` 是工作空间公开业务 Skill，共包含 45 个 SQL 代码块；本文从中提取稳定业务口径和代表性 SQL，不整段复制看板或执行提示词。
- `256`“SQL 的 CTE 分层规则”为用户私有通用 Skill，未绑定特定数据源；`280`“示例：修仙资源获取与消耗统计口径”为用户私有且绑定 datasource 6。两者均为 `visibility_scope=USER_PRIVATE`，不复制到工作空间公开知识库。
- 平台通用规则已实例化为下方“语义口径与 SQL 示例”条目，但不混入单个修仙业务 YAML 对象的来源标识。

本次核查未发现遗漏的工作空间公开业务 Skill。后续若要沉淀 `280` 的资源获取与消耗口径，应由其所有者明确创建同等私有可见性的知识条目，不能转为工作空间公开知识。

## 平台通用语义口径与修仙 SQL 示例

以下知识条目将平台通用规则实例化到修仙 datasource 6。平台层只规定日期、粒度、分子分母、维度排序和实时/历史选表方法；具体物理表、字段、事件名及产品过滤来自修仙工作空间 Schema 与工作空间 Data Skill。它们不是可跨数据源复制的固定 SQL。

平台权限、预测、图表输出和 MCP 工具规则不独立生成业务 SQL：权限规则是所有查询的前置门禁；预测必须另行具备成熟样本和预测配置；图表规则只约束结果字段；MCP 告警能力不访问修仙 MySQL 业务表。

### P1. 有界日期范围与按日聚合

```yaml
term: 有界日期范围与按日聚合
aliases: [日期范围查询, 按日趋势, 完整自然日趋势]
definition: 使用已确认的业务日期分区字段限制事实明细扫描，并按相同业务日粒度完成筛选、分组、排序和展示。
formula: 按 dt 闭区间过滤并 GROUP BY dt
constraints:
  - 修仙历史事件表的业务日期字段是 YYYYMMDD 数字分区 dt。
  - 用户指定日期时使用用户范围；未指定时遵循当前平台和工作空间默认窗口。
  - 可转存看板的趋势 SQL 使用成对的 dashboard 日期参数，不扫描 MAX(dt) 推断边界。
  - WHERE 和 GROUP BY 使用原始 dt；展示时再转换为 YYYY-MM-DD。
related_objects:
  - table: event
    fields: [dt, uid, prod, event]
examples:
  - name: 按日活跃用户趋势
    question: 指定日期范围内每天有多少活跃用户？
    dialect: mysql
    sql: |
      SELECT
          DATE_FORMAT(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS `日期`,
          COUNT(DISTINCT e.uid) AS `活跃用户数`
      FROM `event` e
      WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
        AND e.prod = 110000047
        AND e.event = 'UserActive'
      GROUP BY e.dt
      ORDER BY e.dt;
    notes: 日期投影、分组和排序保持同一业务日粒度。
```

### P2. 事件次数与触发用户数

```yaml
term: 事件次数与触发用户数
aliases: [行为次数与人数, 事件量与去重用户数]
definition: 事件次数统计满足条件的明细事件行数，触发用户数统计满足条件的去重 uid；两个指标表达不同粒度，不能互换。
formula: "事件次数=COUNT(*)；触发用户数=COUNT(DISTINCT uid)"
constraints:
  - 仅在工作空间字典确认事件名和事件明细表后使用。
  - 事件次数不能替代活跃人数、付费人数、收入或留存等业务指标。
  - 同一结果同时返回次数和人数时，字段名必须明确区分。
related_objects:
  - table: event
    fields: [dt, uid, prod, event]
examples:
  - name: 英雄养成事件次数与人数
    question: 指定日期范围内英雄升级和升星分别发生多少次、涉及多少用户？
    dialect: mysql
    sql: |
      SELECT
          e.event AS `养成事件`,
          COUNT(*) AS `事件次数`,
          COUNT(DISTINCT e.uid) AS `触发用户数`
      FROM `event` e
      WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
        AND e.prod = 110000047
        AND e.event IN ('HeroLevelUp', 'HeroStarUp')
      GROUP BY e.event
      ORDER BY `事件次数` DESC;
```

### P3. 比例指标的分子与分母

```yaml
term: 比例指标的分子与分母
aliases: [比例口径, 百分比口径, 付费渗透率]
definition: 比例指标必须在同一统计窗口和同一主体粒度下明确分子与分母；整体比例使用汇总后的分子除以汇总后的分母。
formula: 活跃用户付费率=同时活跃且付费的去重用户数/活跃去重用户数*100
constraints:
  - 分子和分母均按 dt、uid 聚合后计算，避免事件明细行数放大比例。
  - 分母为 0 时返回 NULL。
  - 百分比返回 0-100 的数值，不拼接百分号文本。
  - ServerPayLog 只用于确认付费用户，UserActive 用于确认活跃分母。
related_objects:
  - table: event
    fields: [dt, uid, prod, event]
examples:
  - name: 每日活跃用户付费率
    question: 指定日期范围内每天的活跃用户付费率是多少？
    dialect: mysql
    sql: |
      WITH user_day_flags AS (
          SELECT
              e.dt,
              e.uid,
              MAX(CASE WHEN e.event = 'UserActive' THEN 1 ELSE 0 END) AS is_active,
              MAX(CASE WHEN e.event = 'ServerPayLog' THEN 1 ELSE 0 END) AS is_payer
          FROM `event` e
          WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
            AND e.prod = 110000047
            AND e.event IN ('UserActive', 'ServerPayLog')
          GROUP BY e.dt, e.uid
      )
      SELECT
          DATE_FORMAT(STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS `日期`,
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

### P4. Top N 维度排序

```yaml
term: Top N 维度排序
aliases: [维度排行, 高频项排行, 长尾维度限制]
definition: 对高基数维度按明确指标降序排序并限制返回数量，避免无界展示全部维度值。
formula: 按购买次数降序取前 N 个礼包 ID
constraints:
  - 维度字段及枚举含义必须来自当前工作空间元数据。
  - 必须声明排序指标和 N 值；不能依赖数据库无序返回。
  - 购买次数与购买人数分别使用事件行数和去重 uid。
related_objects:
  - table: event
    fields: [dt, uid, prod, event, personal]
    json_paths: [personal.$.productid]
examples:
  - name: 礼包购买次数 Top 10
    question: 指定日期范围内购买次数最多的前 10 个礼包是什么？
    dialect: mysql
    sql: |
      SELECT
          NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.productid')), '') AS `礼包ID`,
          COUNT(*) AS `购买次数`,
          COUNT(DISTINCT e.uid) AS `购买人数`
      FROM `event` e
      WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
        AND e.prod = 110000047
        AND e.event = 'ServerPayLog'
        AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.productid')), '') IS NOT NULL
      GROUP BY `礼包ID`
      ORDER BY `购买次数` DESC
      LIMIT 10;
```

### P5. 实时与完整历史事件选表

```yaml
term: 实时与完整历史事件选表
aliases: [实时选表, 当天事件表, 历史事件表]
definition: 未完成当前业务日的事件查询使用 event_realtime，已经结束的完整历史日期使用 event；两表不能静默互换。
formula: "当前业务日事件→event_realtime；完整历史日事件→event"
constraints:
  - 只有“今天、当天、今日、实时、当前小时、当前分钟、当前整点”等明确语义触发实时选表。
  - “截至当前”单独出现不能自动触发实时选表。
  - event_realtime 不存在、无权限或缺少字段时应明确报错，不能改查 event。
  - 跨日窗口包含今天时，只有工作空间确认两表字段语义一致后才能 UNION ALL 并在外层聚合。
related_objects:
  - table: event_realtime
    fields: [dt, uid, prod, event]
  - table: event
    fields: [dt, uid, prod, event]
examples:
  - name: 当前业务日实时充值人数
    question: 今天截至当前时刻有多少充值用户？
    dialect: mysql
    sql: |
      SELECT
          DATE_FORMAT(STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS `日期`,
          COUNT(DISTINCT e.uid) AS `充值人数`
      FROM `event_realtime` e
      WHERE e.dt = {{dashboard_end_yyyymmdd}}
        AND e.prod = 110000047
        AND e.event = 'ServerPayLog';
    notes: dashboard_end_yyyymmdd 必须由当前请求解析为当前业务日。
  - name: 完整历史日充值人数
    question: 指定完整历史日期范围内每天有多少充值用户？
    dialect: mysql
    sql: |
      SELECT
          DATE_FORMAT(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS `日期`,
          COUNT(DISTINCT e.uid) AS `充值人数`
      FROM `event` e
      WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
        AND e.prod = 110000047
        AND e.event = 'ServerPayLog'
      GROUP BY e.dt
      ORDER BY e.dt;
```

## 1. 新增用户与系统归因

```yaml
term: 新增用户与系统归因
aliases: [系统新增, 分系统新增用户]
definition: 统计触发 UserRegister 的去重用户，并使用注册事件上的设备或用户平台字段归因到系统。
formula: COUNT(DISTINCT uid) BY 注册日期, 系统
constraints:
  - 系统优先使用 deviceinfo.$._platform，为空时使用 userinfo.$._platformType。
  - 系统归因必须使用注册事件字段，不能被后续活跃事件覆盖。
related_objects:
  - table: event
    fields: [dt, uid, prod, event, deviceinfo, userinfo]
    json_paths: [deviceinfo.$._platform, userinfo.$._platformType]
examples:
  - name: 每日分系统新增
    question: 指定日期范围内每天各系统的新增用户数是多少？
    dialect: mysql
    sql: |
      WITH registers AS (
          SELECT
              e.dt,
              e.uid,
              COALESCE(
                  NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.deviceinfo, '$._platform')), ''),
                  NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.userinfo, '$._platformType')), ''),
                  '未知'
              ) AS platform_name
          FROM `event` e
          WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
            AND e.prod = 110000047
            AND e.event = 'UserRegister'
      )
      SELECT
          STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS `日期`,
          platform_name AS `系统`,
          COUNT(DISTINCT uid) AS `新增用户数`
      FROM registers
      GROUP BY dt, platform_name
      ORDER BY dt, platform_name;
```

## 2. 渠道新增用户

```yaml
term: 渠道新增用户
aliases: [渠道获客, 分渠道新增]
definition: 按注册事件上的渠道归因字段统计每日新增用户。
formula: COUNT(DISTINCT uid) BY 注册日期, 渠道
constraints:
  - 渠道优先使用 adinfo.$.mediaSource，为空时使用 adinfo.$.campaignName。
  - 渠道字段仍为空时归为“未知”。
  - 渠道成本和 ROI 需要额外确认成本字段和回收窗口。
related_objects:
  - table: event
    fields: [dt, uid, prod, event, adinfo]
    json_paths: [adinfo.$.mediaSource, adinfo.$.campaignName]
examples:
  - name: 每日分渠道新增
    question: 指定日期范围内各渠道每天新增多少用户？
    dialect: mysql
    sql: |
      WITH registers AS (
          SELECT
              e.dt,
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
      SELECT
          STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS `日期`,
          channel AS `渠道`,
          COUNT(DISTINCT uid) AS `新增用户数`
      FROM registers
      GROUP BY dt, channel
      ORDER BY dt, channel;
```

## 3. WAU

```yaml
term: WAU
aliases: [周活跃用户数, Weekly Active Users]
definition: 按自然周统计触发 UserActive 的去重用户数，周起始日为周一。
formula: COUNT(DISTINCT uid) BY 自然周
constraints:
  - 活跃主体按 uid 去重，事件次数不是 WAU。
  - 查询窗口跨越不完整周时，需要说明首尾周是否完整。
related_objects:
  - table: event
    fields: [dt, uid, prod, event]
examples:
  - name: WAU 趋势
    question: 指定日期范围内每周的 WAU 是多少？
    dialect: mysql
    sql: |
      SELECT
          DATE_SUB(
              STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'),
              INTERVAL WEEKDAY(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d')) DAY
          ) AS `周`,
          COUNT(DISTINCT e.uid) AS `WAU`
      FROM `event` e
      WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
        AND e.event = 'UserActive'
        AND e.prod = 110000047
      GROUP BY `周`
      ORDER BY `周`;
```

## 4. ARPU 与 ARPPU

```yaml
term: ARPU 与 ARPPU
aliases: [每活跃用户收入, 每付费用户收入]
definition: 使用 ServerPayLog 真实交易金额计算日收入，并分别以日活跃用户和日付费用户为分母计算 ARPU、ARPPU。
formula: "ARPU=日收入/DAU；ARPPU=日收入/日付费用户数"
constraints:
  - 日收入使用 personal.$.money，不能与用户快照累计付费字段混用。
  - 分母为 0 时返回 NULL，不制造虚假 0 比率。
related_objects:
  - table: event
    fields: [dt, uid, prod, event, personal]
    json_paths: [personal.$.money]
examples:
  - name: 每日 ARPU 与 ARPPU
    question: 指定日期范围内每天的 ARPU 和 ARPPU 是多少？
    dialect: mysql
    sql: |
      WITH daily_pay AS (
          SELECT
              e.dt,
              ROUND(SUM(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')), '') AS DECIMAL(18, 4))), 2) AS pay_amount,
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
      SELECT
          DATE_FORMAT(STR_TO_DATE(CAST(d.dt AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS `日期`,
          ROUND(COALESCE(p.pay_amount, 0) / NULLIF(d.active_users, 0), 2) AS `ARPU`,
          ROUND(COALESCE(p.pay_amount, 0) / NULLIF(p.pay_users, 0), 2) AS `ARPPU`
      FROM daily_active d
      LEFT JOIN daily_pay p ON p.dt = d.dt
      ORDER BY d.dt;
```

## 5. 实时充值人数

```yaml
term: 实时充值人数
aliases: [今日充值人数, 当前充值用户数]
definition: 按看板结束日，从实时事件表统计触发 ServerPayLog 的去重充值用户数；当看板结束日代表当前自然日时可作为实时口径。
formula: COUNT(DISTINCT uid)
constraints:
  - 仅适用于“今天、实时、当前”等问题，且看板结束日必须已解析为当前自然日。
  - 完整历史区间必须使用历史事件表和对应 Data Skill。
related_objects:
  - table: event_realtime
    fields: [dt, uid, prod, event]
examples:
  - name: 今日实时充值人数
    question: 看板结束日截至当前时刻有多少充值用户？
    dialect: mysql
    sql: |
      SELECT
          DATE_FORMAT(STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS `日期`,
          COUNT(DISTINCT uid) AS `充值人数`
      FROM `event_realtime`
      WHERE dt = {{dashboard_end_yyyymmdd}}
        AND prod = 110000047
        AND event = 'ServerPayLog';
```

## 6. 渠道新增 D1/D3/D7 留存

```yaml
term: 渠道新增 D1/D3/D7 留存
aliases: [渠道新增留存, 渠道 cohort 留存]
definition: 以注册事件形成渠道新增 cohort，统计同一批用户在注册日后的第 1、3、7 个自然日触发 UserActive 的去重比例。
formula: "Dn留存率=注册后第n日活跃用户数/新增用户数*100%"
constraints:
  - 分母为注册日期和渠道维度下的新增去重用户。
  - 分子为同一用户在精确 D1、D3、D7 日期活跃。
  - 观察结束日前不足 1、3、7 天的 cohort 返回 NULL。
  - 日期骨架和按日补零遵循 Skill 255。
related_objects:
  - table: event
    fields: [dt, uid, prod, event, adinfo]
    json_paths: [adinfo.$.mediaSource, adinfo.$.campaignName]
examples:
  - name: 各渠道 D1/D3/D7 留存
    question: 最近 15 个自然日各渠道新增用户的 D1、D3、D7 留存率是多少？
    dialect: mysql
    sql: |
      WITH params AS (
          SELECT
              DATE(STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d')) AS start_date,
              DATE(STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d')) AS end_date
      ), day_offsets AS (
          SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4
          UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9
          UNION ALL SELECT 10 UNION ALL SELECT 11 UNION ALL SELECT 12 UNION ALL SELECT 13 UNION ALL SELECT 14
      ), calendar AS (
          SELECT
              DATE_ADD(p.start_date, INTERVAL d.n DAY) AS cohort_date,
              CAST(DATE_FORMAT(DATE_ADD(p.start_date, INTERVAL d.n DAY), '%Y%m%d') AS SIGNED) AS cohort_dt,
              CAST(DATE_FORMAT(DATE_ADD(p.start_date, INTERVAL d.n + 1 DAY), '%Y%m%d') AS SIGNED) AS d1_dt,
              CAST(DATE_FORMAT(DATE_ADD(p.start_date, INTERVAL d.n + 3 DAY), '%Y%m%d') AS SIGNED) AS d3_dt,
              CAST(DATE_FORMAT(DATE_ADD(p.start_date, INTERVAL d.n + 7 DAY), '%Y%m%d') AS SIGNED) AS d7_dt
          FROM params p
          CROSS JOIN day_offsets d
          WHERE DATE_ADD(p.start_date, INTERVAL d.n DAY) <= p.end_date
      ), cohort AS (
          SELECT
              e.dt AS cohort_dt,
              e.uid,
              COALESCE(
                  NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.mediaSource')), ''),
                  NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.campaignName')), ''),
                  '未知'
              ) AS channel
          FROM `event` e
          WHERE e.prod = 110000047
            AND e.event = 'UserRegister'
            AND e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
          GROUP BY e.dt, e.uid, channel
      ), channels AS (
          SELECT DISTINCT channel FROM cohort
      ), date_channels AS (
          SELECT c.*, ch.channel
          FROM calendar c
          CROSS JOIN channels ch
      ), active AS (
          SELECT e.dt AS active_dt, e.uid
          FROM `event` e
          CROSS JOIN params p
          WHERE e.prod = 110000047
            AND e.event = 'UserActive'
            AND e.dt BETWEEN CAST(DATE_FORMAT(DATE_ADD(p.start_date, INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
                AND {{dashboard_end_yyyymmdd}}
          GROUP BY e.dt, e.uid
      )
      SELECT
          dc.cohort_date AS `日期`,
          dc.channel AS `渠道`,
          COUNT(DISTINCT c.uid) AS `新增用户数`,
          CASE WHEN dc.cohort_date > DATE_SUB(p.end_date, INTERVAL 1 DAY) THEN NULL
               ELSE COALESCE(ROUND(COUNT(DISTINCT CASE WHEN a.active_dt = dc.d1_dt THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2), 0) END AS `第1日`,
          CASE WHEN dc.cohort_date > DATE_SUB(p.end_date, INTERVAL 3 DAY) THEN NULL
               ELSE COALESCE(ROUND(COUNT(DISTINCT CASE WHEN a.active_dt = dc.d3_dt THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2), 0) END AS `第3日`,
          CASE WHEN dc.cohort_date > DATE_SUB(p.end_date, INTERVAL 7 DAY) THEN NULL
               ELSE COALESCE(ROUND(COUNT(DISTINCT CASE WHEN a.active_dt = dc.d7_dt THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2), 0) END AS `第7日`
      FROM date_channels dc
      CROSS JOIN params p
      LEFT JOIN cohort c ON c.cohort_dt = dc.cohort_dt AND c.channel = dc.channel
      LEFT JOIN active a ON a.uid = c.uid AND a.active_dt IN (dc.d1_dt, dc.d3_dt, dc.d7_dt)
      GROUP BY dc.cohort_date, dc.channel, p.end_date
      ORDER BY dc.cohort_date, dc.channel;
```

## 7. 当前等级分布

```yaml
term: 当前等级分布
aliases: [用户等级分布, 当前等级段]
definition: 使用观察结束日的用户快照等级，将用户划分到等级区间并统计去重用户数。
formula: COUNT(DISTINCT uid) BY 等级区间
constraints:
  - 使用 user 快照表，不能与历史升级事件次数混用。
  - 快照日必须符合最新完整日规则。
related_objects:
  - table: user
    fields: [dt, uid, prod, lastinfo]
    json_paths: [lastinfo.$.level]
examples:
  - name: 观察结束日等级分布
    question: 观察结束日的用户等级分布是什么？
    dialect: mysql
    sql: |
      WITH user_level AS (
          SELECT
              u.uid,
              COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.level')), '') AS DECIMAL(18,4)), 0) AS level_value
          FROM `user` u
          WHERE u.dt = {{dashboard_end_yyyymmdd}}
            AND u.prod = 110000047
      ), level_grouped AS (
          SELECT
              uid,
              CASE
                  WHEN level_value >= 50 THEN '50+'
                  WHEN level_value >= 48 THEN '48-49'
                  ELSE CONCAT(FLOOR(level_value / 3) * 3, '-', FLOOR(level_value / 3) * 3 + 2)
              END AS level_range,
              CASE WHEN level_value >= 50 THEN 50 WHEN level_value >= 48 THEN 48 ELSE FLOOR(level_value / 3) * 3 END AS sort_order
          FROM user_level
      )
      SELECT
          level_range AS `等级区间`,
          COUNT(DISTINCT uid) AS `用户数`
      FROM level_grouped
      GROUP BY level_range, sort_order
      ORDER BY sort_order;
```

## 8. 英雄养成

```yaml
term: 英雄养成
aliases: [英雄升级, 英雄升星]
definition: 按英雄统计升级、升星事件次数及对应去重用户数。
formula: "事件次数=事件行数；养成用户数=COUNT(DISTINCT uid)"
constraints:
  - HeroLevelUp 表示升级，HeroStarUp 表示升星。
  - 英雄 ID 到名称的映射必须来自修仙工作空间字典。
related_objects:
  - table: event
    fields: [dt, uid, prod, event, personal]
    json_paths: [personal.$.ed_heroId]
examples:
  - name: 英雄升级和升星排行
    question: 哪些英雄的升级和升星最活跃？
    dialect: mysql
    sql: |
      SELECT
          JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_heroId')) AS `将领ID`,
          COUNT(CASE WHEN e.event = 'HeroStarUp' THEN 1 END) AS `升星次数`,
          COUNT(DISTINCT CASE WHEN e.event = 'HeroStarUp' THEN e.uid END) AS `升星用户数`,
          COUNT(CASE WHEN e.event = 'HeroLevelUp' THEN 1 END) AS `升级次数`,
          COUNT(DISTINCT CASE WHEN e.event = 'HeroLevelUp' THEN e.uid END) AS `升级用户数`
      FROM `event` e
      WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
        AND e.prod = 110000047
        AND e.event IN ('HeroLevelUp', 'HeroStarUp')
        AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_heroId')), '') IS NOT NULL
      GROUP BY `将领ID`
      ORDER BY (`升星次数` + `升级次数`) DESC;
```
