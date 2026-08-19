# 修仙业务术语与 SQL 示例


> 适用范围：修仙工作空间 `datasource_id=6`（MySQL）。内容来源于活动 Data Skill `257, 269-279`，日期和按日补零规则引用 Skill `255`。本文只提供参考知识，不能覆盖当前数据源、权限、Schema、事件/JSON 映射或 Data Skill。

## 工作空间级 Data Skill 核查

2026-08-19 对修仙租户 `7482727237662281728` 的活动 Data Skill 做了只读核查：

- 工作空间公开 Skill 共 13 条，均为 `visibility_scope=ADMIN_PUBLIC`、`specific_ds=true`，且仅绑定 `datasource_ids=[6]`。
- `255` 是修仙日期分区、日期骨架和按日补零执行契约，继续由 Data Skill 执行，不作为独立业务术语复制到知识库。
- `257`、`269-279` 是工作空间公开业务 Skill，共包含 45 个 SQL 代码块；本文从中提取稳定业务口径和代表性 SQL，不整段复制看板或执行提示词。
- `256`“SQL 的 CTE 分层规则”为用户私有通用 Skill，未绑定特定数据源；`280`“示例：修仙资源获取与消耗统计口径”为用户私有且绑定 datasource 6。两者均为 `visibility_scope=USER_PRIVATE`，不复制到工作空间公开知识库。
- 平台公共 Data Skill 的完整清单和对本文 SQL 示例的约束见下节，但不混入单个修仙业务 YAML 对象。

本次核查未发现遗漏的工作空间公开业务 Skill。后续若要沉淀 `280` 的资源获取与消耗口径，应由其所有者明确创建同等私有可见性的知识条目，不能转为工作空间公开知识。

## 平台级 Data Skill 核查

2026-08-19 对全部活动平台公共 Data Skill 做了只读核查，共 16 条；它们均为 `visibility_scope=PLATFORM_PUBLIC`、`specific_ds=false`、`datasource_ids=[]`，且不包含 SQL 代码块。平台 Skill 是所有已授权数据源共享的执行约束或工具能力，不能覆盖修仙工作空间 Skill 中已经确认的业务字段、事件和指标定义。

### SQL 与分析通用约束

| 平台 Skill | 约束主题 | 对本文示例的适用规则 |
| --- | --- | --- |
| `170` 数据源上下文、权限与语义优先 | 数据源、权限、Schema 和语义优先级 | 仅在当前用户有权访问修仙 datasource 6 时使用本文，不得根据相似名称跨数据源引用对象。 |
| `171` 时间字段、观察窗口与日期边界 | 业务时间、自然周期、成熟窗口和有界扫描 | 日期范围来自用户问题或看板参数；留存等未成熟 cohort 返回 NULL，不扩大为无界历史查询。 |
| `172` 明细粒度、去重与预聚合 | 事件粒度、主体去重和多事实表关联 | 用户类指标按 `uid` 去重；事件次数和触发用户数分开；关联前先按目标粒度聚合。 |
| `173` 比例指标、分子分母与百分比 | 留存率、付费率、ARPU/ARPPU 等非累加指标 | 明确分子、分母和统计窗口；分母为 0 时使用 NULL，不能制造业务含义不明的 0。 |
| `185` 维度拆解、排序与 Top N | 维度分组、高基数和长尾处理 | 系统、渠道、等级、英雄等维度必须来自当前工作空间元数据；Top N 需保留明确排序指标。 |
| `186` 事件/日志次数与主体数 | 事件次数、触发人数、去重键和事件属性 | `COUNT(*)` 表示事件次数，`COUNT(DISTINCT uid)` 表示触发用户数，两者不能互换。 |
| `187` 漏斗步骤、路径与转化校验 | 步骤顺序、主体状态和转化单调性 | 本文没有独立漏斗 SQL；后续加入支付流程或行为漏斗时，必须先按主体确认步骤状态和顺序。 |
| `188` 图表选择与结果字段结构 | 趋势、构成、指标卡、漏斗和表格字段 | 日期趋势返回稳定日期列和数值指标列；图表字段映射不能替换 SQL 的业务口径。 |
| `190` 预测、成熟样本与置信表达 | 预测目标、成熟样本和外推边界 | 本文 SQL 示例只做历史统计，不应被当作预测结果；预测必须另行声明样本、窗口和置信限制。 |
| `281` SQL 日期与分组规范 | 方言日期表达式、SELECT/GROUP BY 和输出别名 | 本文按 MySQL 生成日期表达式，投影、分组、排序表达式必须保持同一日期粒度。 |
| `282` 当天实时事件与完整历史事件选表 | `event_realtime` 与 `event` 的选择 | 仅当前自然日、实时或当前时刻问题使用 `event_realtime`；完整历史日期使用 `event`，不得静默换表。 |
| `283` 日期字段用途与范围筛选契约 | 日期字段角色、范围参数和实时日期策略 | `dt` 按当前修仙数据源配置作为日期分区字段；日期参数和实时策略以当前请求及工作空间配置为准。 |

以上平台 Skill 没有可直接抽取的 SQL 代码块，因此本文只记录其约束，不为其人为生成平台 SQL 示例。本文后续所有修仙 SQL 仍必须同时满足平台约束和当前工作空间 Data Skill；发生冲突时，以当前权限、数据源上下文以及更具体的修仙工作空间口径为准。

### 平台 MCP 工具能力

| 平台 Skill | 能力边界 |
| --- | --- |
| `248` SaaS ChatMon MCP 告警过滤项 | 查询当前工作空间绑定 MCP 支持的告警过滤枚举。 |
| `249` SaaS ChatMon MCP 告警数量 | 通过 MCP 统计最近 1-7 天告警数量和分布。 |
| `250` SaaS ChatMon MCP 告警搜索 | 通过 MCP 搜索轻量告警明细。 |
| `251` SaaS ChatMon MCP 告警证据 | 根据告警搜索结果继续查询证据消息。 |

这 4 条是外部工具调用能力，不访问修仙 MySQL 业务表，也不生成本文的业务 SQL；只有当前工作空间实际绑定并授权对应 MCP 时才能使用。

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
