# flam 业务术语与 SQL 示例

> 适用范围：flam 工作空间 `datasource_id=3`（MySQL）。内容来源于活动 Data Skill `225, 226, 229-233, 235-243`。本文只提供参考知识，发布前必须声明实际关联对象，并通过当前 Schema、权限和 Data Skill 校验。

## 1. 新增用户

```yaml
term: 新增用户
aliases: [注册用户, 新增注册用户]
definition: 统计窗口内触发 UserRegister 事件的去重用户数。
formula: COUNT(DISTINCT uid)
constraints:
  - 新增日期使用注册事件的 dt，不能使用后续活跃日期替代。
  - 仅统计 prod=110000038 且 event=UserRegister 的记录。
related_objects:
  - table: event
  - fields: [dt, uid, prod, event]
source_skills: [226]
examples:
  - name: 每日新增用户趋势
    question: 指定日期范围内每天有多少新增用户？
    dialect: mysql
    sql: |
      SELECT
          STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
          COUNT(DISTINCT e.uid) AS `新增用户数`
      FROM `event` e
      WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
        AND e.prod = 110000038
        AND e.event = 'UserRegister'
      GROUP BY e.dt
      ORDER BY e.dt;
```

## 2. DAU

```yaml
term: DAU
aliases: [日活, 日活跃用户数, Daily Active Users]
definition: 一个自然日内触发有效活跃事件的去重用户数。
formula: COUNT(DISTINCT uid)
constraints:
  - 有效活跃行为固定为当前 flam Data Skill 定义的 UserActive 事件。
  - 事件次数不能作为 DAU，必须按 uid 去重。
related_objects:
  - table: event
  - fields: [dt, uid, prod, event]
source_skills: [229]
examples:
  - name: DAU 趋势
    question: 指定日期范围内的 DAU 趋势是什么？
    dialect: mysql
    sql: |
      SELECT
          STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
          COUNT(DISTINCT e.uid) AS `DAU`
      FROM `event` e
      WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
        AND e.event = 'UserActive'
        AND e.prod = 110000038
      GROUP BY e.dt
      ORDER BY e.dt;
```

## 3. 日付费与效率指标

```yaml
term: 日付费与效率指标
aliases: [日收入, 付费率, ARPU, ARPPU]
definition: 使用 ServerPayLog 的真实交易金额和付费用户，结合当日活跃用户计算日收入、ARPU、ARPPU 和付费渗透率。
formula: "ARPU=日收入/DAU；ARPPU=日收入/日付费用户数；付费渗透率=日付费用户数/DAU"
constraints:
  - 日收入使用 personal.money，不使用用户快照累计付费字段。
  - 分母固定为同日 UserActive 去重用户；其他分母必须使用对应业务口径。
  - 分母为 0 时返回 NULL，不制造虚假比例。
related_objects:
  - table: event
  - fields: [dt, uid, prod, event, personal]
  - json_paths: [personal.$.money]
source_skills: [230]
examples:
  - name: 每日收入与付费效率
    question: 每天的收入、付费人数、ARPU、ARPPU 和付费渗透率是多少？
    dialect: mysql
    sql: |
      WITH daily_pay AS (
          SELECT
              e.dt,
              ROUND(SUM(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')), '') AS DECIMAL(18, 4))), 2) AS pay_amount,
              COUNT(DISTINCT e.uid) AS pay_users
          FROM `event` e
          WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
            AND e.event = 'ServerPayLog'
            AND e.prod = 110000038
          GROUP BY e.dt
      ), daily_active AS (
          SELECT e.dt, COUNT(DISTINCT e.uid) AS active_users
          FROM `event` e
          WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
            AND e.event = 'UserActive'
            AND e.prod = 110000038
          GROUP BY e.dt
      )
      SELECT
          STR_TO_DATE(CAST(d.dt AS CHAR), '%Y%m%d') AS `日期`,
          COALESCE(p.pay_users, 0) AS `付费用户数`,
          COALESCE(p.pay_amount, 0) AS `付费总额`,
          ROUND(COALESCE(p.pay_amount, 0) / NULLIF(d.active_users, 0), 2) AS `ARPU`,
          ROUND(COALESCE(p.pay_amount, 0) / NULLIF(p.pay_users, 0), 2) AS `ARPPU`,
          ROUND(COALESCE(p.pay_users, 0) / NULLIF(d.active_users, 0) * 100, 2) AS `付费渗透率`
      FROM daily_active d
      LEFT JOIN daily_pay p ON p.dt = d.dt
      ORDER BY d.dt;
```

## 4. D1 留存

```yaml
term: D1 留存
aliases: [次日留存, 第1日留存]
definition: 某日新增 cohort 中，在注册后的第 1 个自然日再次触发 UserActive 的去重用户占比。
formula: D1留存用户数 / 新增用户数 * 100%
constraints:
  - 分母为注册日 UserRegister 去重用户。
  - 分子为同一批用户在注册日加 1 天触发 UserActive 的去重用户。
  - 注册日加 1 天超出观察结束日时，不输出成熟留存结论。
related_objects:
  - table: event
  - fields: [dt, uid, prod, event]
source_skills: [226]
examples:
  - name: 每日新增 D1 留存
    question: 指定日期范围内每日新增用户的 D1 留存率是多少？
    dialect: mysql
    sql: |
      WITH cohort AS (
          SELECT
              e.dt AS cohort_dt,
              CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS d1_dt,
              e.uid
          FROM `event` e
          WHERE e.prod = 110000038
            AND e.event = 'UserRegister'
            AND e.dt BETWEEN {{dashboard_start_yyyymmdd}}
                AND CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
      ), active AS (
          SELECT e.dt, e.uid
          FROM `event` e
          WHERE e.dt BETWEEN
                CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
                AND {{dashboard_end_yyyymmdd}}
            AND e.prod = 110000038
            AND e.event = 'UserActive'
          GROUP BY e.dt, e.uid
      ), retained AS (
          SELECT c.cohort_dt, COUNT(DISTINCT c.uid) AS d1_retained_users
          FROM cohort c
          JOIN active a ON a.uid = c.uid AND a.dt = c.d1_dt
          GROUP BY c.cohort_dt
      )
      SELECT
          STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d') AS `日期`,
          COUNT(DISTINCT c.uid) AS `新增用户数`,
          COALESCE(r.d1_retained_users, 0) AS `次日留存用户数`,
          ROUND(COALESCE(r.d1_retained_users, 0) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `次日留存率`
      FROM cohort c
      LEFT JOIN retained r ON r.cohort_dt = c.cohort_dt
      GROUP BY c.cohort_dt, r.d1_retained_users
      ORDER BY c.cohort_dt;
```

## 5. 新手引导漏斗

```yaml
term: 新手引导漏斗
aliases: [新手流程转化, 新手任务漏斗]
definition: 以注册用户为 cohort，按注册、进入游戏、引导开始、引导完成、章节或任务领奖的顺序统计到达用户数和转化率。
formula: "整体转化率=当前步骤用户数/注册用户数；上步转化率=当前步骤用户数/上一步用户数"
constraints:
  - 漏斗主体必须是同一 uid。
  - 步骤人数使用去重用户数，不能使用事件次数。
  - 事件定义和步骤顺序以当前工作空间事件字典为准。
related_objects:
  - tables: [user, event]
  - fields: [user.dt, user.uid, user.prod, user.userinfo, event.dt, event.uid, event.prod, event.event]
  - json_paths: [userinfo.$.regdate]
source_skills: [233]
examples:
  - name: 新手步骤转化
    question: 新手引导各步骤的用户数和转化率是多少？
    dialect: mysql
    sql: |
      WITH cohort AS (
          SELECT u.uid
          FROM `user` u
          WHERE u.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
            AND u.prod = 110000038
            AND JSON_UNQUOTE(JSON_EXTRACT(u.userinfo, '$.regdate')) = CAST(u.dt AS CHAR)
      ), event_window AS (
          SELECT e.uid, e.event
          FROM `event` e
          WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
            AND e.prod = 110000038
            AND e.event IN ('EnterGame','Login','UserLogin','NewUserGuideStart','DialogueStart','NewUserGuide','DialogueEnd','ChapterTaskReward','TaskReward')
      ), step_users AS (
          SELECT 1 AS step_order, '账号注册' AS step_name, COUNT(DISTINCT c.uid) AS users FROM cohort c
          UNION ALL
          SELECT 2, '进入游戏', COUNT(DISTINCT c.uid) FROM cohort c JOIN event_window e ON e.uid = c.uid AND e.event IN ('EnterGame','Login','UserLogin')
          UNION ALL
          SELECT 3, '引导开始', COUNT(DISTINCT c.uid) FROM cohort c JOIN event_window e ON e.uid = c.uid AND e.event IN ('NewUserGuideStart','DialogueStart')
          UNION ALL
          SELECT 4, '引导完成', COUNT(DISTINCT c.uid) FROM cohort c JOIN event_window e ON e.uid = c.uid AND e.event IN ('NewUserGuide','DialogueEnd')
          UNION ALL
          SELECT 5, '章节/任务领奖', COUNT(DISTINCT c.uid) FROM cohort c JOIN event_window e ON e.uid = c.uid AND e.event IN ('ChapterTaskReward','TaskReward')
      ), calc AS (
          SELECT s.*, base.users AS start_users, COALESCE(prev.users, s.users) AS prev_users
          FROM step_users s
          LEFT JOIN step_users base ON base.step_order = 1
          LEFT JOIN step_users prev ON prev.step_order = s.step_order - 1
      )
      SELECT
          step_order,
          step_name AS `新手步骤`,
          users AS `用户数`,
          ROUND(users / NULLIF(start_users, 0) * 100, 2) AS `整体转化率`,
          ROUND(users / NULLIF(prev_users, 0) * 100, 2) AS `上步转化率`,
          GREATEST(prev_users - users, 0) AS `流失人数`
      FROM calc
      ORDER BY step_order;
```

## 6. 钻石获取、消耗与净变化

```yaml
term: 钻石获取、消耗与净变化
aliases: [钻石经济, 钻石流水]
definition: 按钻石变动事件区分免费钻石和付费钻石的正向获取、负向消耗和净变化。
formula: "获取量=正数求和；消耗量=负数绝对值求和；净变化=原始正负值求和"
constraints:
  - 仅统计 GoldChange 事件。
  - 免费钻石和付费钻石必须分别统计，不能合并字段。
related_objects:
  - table: event
  - fields: [dt, prod, event, personal]
  - json_paths: [personal.$.ed_changeFree, personal.$.ed_changePaid]
source_skills: [238]
examples:
  - name: 每日钻石流水
    question: 每天免费钻石和付费钻石的获取量、消耗量和净变化分别是多少？
    dialect: mysql
    sql: |
      SELECT
          STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
          ROUND(SUM(GREATEST(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_changeFree')), '') AS DECIMAL(18,4)), 0), 0)), 2) AS `免费钻石获取量`,
          ROUND(ABS(SUM(LEAST(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_changeFree')), '') AS DECIMAL(18,4)), 0), 0))), 2) AS `免费钻石消耗量`,
          ROUND(SUM(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_changeFree')), '') AS DECIMAL(18,4)), 0)), 2) AS `免费钻石净变化`,
          ROUND(SUM(GREATEST(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_changePaid')), '') AS DECIMAL(18,4)), 0), 0)), 2) AS `付费钻石获取量`,
          ROUND(ABS(SUM(LEAST(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_changePaid')), '') AS DECIMAL(18,4)), 0), 0))), 2) AS `付费钻石消耗量`,
          ROUND(SUM(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_changePaid')), '') AS DECIMAL(18,4)), 0)), 2) AS `付费钻石净变化`
      FROM `event` e
      WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
        AND e.event = 'GoldChange'
        AND e.prod = 110000038
      GROUP BY e.dt
      ORDER BY e.dt;
```

## 7. 英雄养成

```yaml
term: 英雄养成
aliases: [英雄升级, 英雄升星]
definition: 按英雄统计升级、升星事件次数及对应去重用户数。
formula: "事件次数=事件行数；养成用户数=COUNT(DISTINCT uid)"
constraints:
  - HeroLevelUp 表示升级，HeroStarUp 表示升星。
  - 英雄 ID 到展示名称的映射必须来自当前工作空间字典。
related_objects:
  - table: event
  - fields: [dt, uid, event, personal]
  - json_paths: [personal.$.ed_heroId]
source_skills: [241]
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
        AND e.event IN ('HeroLevelUp', 'HeroStarUp')
        AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_heroId')), '') IS NOT NULL
      GROUP BY `将领ID`
      ORDER BY (`升星次数` + `升级次数`) DESC;
```

## 8. 当前等级分布

```yaml
term: 当前等级分布
aliases: [用户等级分布, 当前等级段]
definition: 使用指定快照日的用户当前等级字段，将用户划分到业务确认的等级区间并统计去重用户数。
formula: COUNT(DISTINCT uid) BY 等级区间
constraints:
  - 使用 user 当前态快照，不能用历史升级事件直接推断当前等级。
  - 快照日必须是当前日期规则允许的完整数据日。
  - 等级字段和分箱边界必须在 flam 工作空间确认。
related_objects:
  - table: user
  - fields: [dt, uid, prod, lastinfo]
source_skills: [231]
examples: []
```
