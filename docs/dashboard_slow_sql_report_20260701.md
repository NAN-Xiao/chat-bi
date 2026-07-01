# 看板仪表盘慢 SQL 扫描报告

- 生成时间：2026-07-01T11:34:41
- 慢 SQL 阈值：>10s；单条执行超时：15s
- 扫描看板 SQL 入口：466 个
- 去重后 SQL：186 条
- 实际计时 SQL：183 条
- 命中慢 SQL/超时 SQL：21 条
- 未计入慢 SQL 的连接/语法等不可用项：3 条

> 说明：相同数据源下 SQL 文本完全一致时只执行一次，并列出所有复用看板/仪表盘。MySQL 查询每条单独建连，避免一次超时污染后续结果。

## 1. 超时/失败，耗时 17.51s，数据源 1（SLG BI Mock / pg）

- SQL Hash：`71b161ac09ed`
- 样本行数：None
- 错误：`QueryCanceled: 错误:  由于语句执行超时，正在取消查询命令
`
- 使用位置：
  - 看板：112（`29660c44cd014f49838dfe3f9b7d81e6`）；仪表盘：步骤转化率排行；组件：`2185322546856108032`；路径：new-view
  - 看板：666（`f1ded8fbc95b409f86eae31972e5eeec`）；仪表盘：步骤转化率排行；组件：`2185324965790916608`；路径：new-view

```sql
WITH obs AS
  (SELECT max("event_date") AS "max_date"
   FROM "public"."fact_payments"),
     cohort AS
  (SELECT "p"."player_id"
   FROM "public"."dim_player" "p"
   CROSS JOIN obs
   WHERE "p"."install_date" BETWEEN obs."max_date" - 29 AND obs."max_date"),
     event_flags AS
  (SELECT "e"."player_id",
          bool_or("e"."event_name" = 'tutorial_step'
                  AND ("e"."attributes"->>'step')::int >= 3) AS "did_tutorial_3",
          bool_or("e"."event_name" = 'tutorial_step'
                  AND ("e"."attributes"->>'step')::int >= 7) AS "did_tutorial_7"
   FROM "public"."fact_events" "e"
   JOIN cohort "c" ON "c"."player_id" = "e"."player_id"
   GROUP BY "e"."player_id"),
     player_level AS
  (SELECT "c"."player_id",
          coalesce("ef"."did_tutorial_3", false) AS "did_tutorial_3",
          coalesce("ef"."did_tutorial_7", false) AS "did_tutorial_7",
          EXISTS
     (SELECT 1
      FROM "public"."fact_battles" "b"
      WHERE "b"."player_id" = "c"."player_id") AS "did_first_battle",
                 EXISTS
     (SELECT 1
      FROM "public"."fact_building_upgrades" "bu"
      WHERE "bu"."player_id" = "c"."player_id") AS "did_building_upgrade",
                        EXISTS
     (SELECT 1
      FROM "public"."fact_payments" "p"
      WHERE "p"."player_id" = "c"."player_id"
        AND "p"."payment_status" = 'success'
        AND "p"."net_revenue_usd" > 0
        AND "p"."is_first_pay" = true) AS "did_first_pay"
   FROM cohort "c"
   LEFT JOIN event_flags "ef" ON "ef"."player_id" = "c"."player_id"),
     steps AS
  (SELECT 1 AS "step_order",
          '完成教程第 3 步' AS "step_name",
          count(*) FILTER (
                           WHERE "did_tutorial_3") AS "users"
   FROM player_level
   UNION ALL SELECT 2,
                    '完成教程第 7 步',
                    count(*) FILTER (
                                     WHERE "did_tutorial_3"
                                       AND "did_tutorial_7")
   FROM player_level
   UNION ALL SELECT 3,
                    '首次战斗',
                    count(*) FILTER (
                                     WHERE "did_tutorial_3"
                                       AND "did_tutorial_7"
                                       AND "did_first_battle")
   FROM player_level
   UNION ALL SELECT 4,
                    '首次建筑升级',
                    count(*) FILTER (
                                     WHERE "did_tutorial_3"
                                       AND "did_tutorial_7"
                                       AND "did_first_battle"
                                       AND "did_building_upgrade")
   FROM player_level
   UNION ALL SELECT 5,
                    '首次成功付费',
                    count(*) FILTER (
                                     WHERE "did_tutorial_3"
                                       AND "did_tutorial_7"
                                       AND "did_first_battle"
                                       AND "did_building_upgrade"
                                       AND "did_first_pay")
   FROM player_level),
     base AS
  (SELECT "step_order",
          "step_name",
          "users",
          first_value("users") OVER (
                                     ORDER BY "step_order") AS "start_users",
          lag("users") OVER (
                             ORDER BY "step_order") AS "prev_users"
   FROM steps)
SELECT "step_name" AS "步骤名称",
       "users" AS "通过人数",
       round("users"::numeric / nullif("prev_users", 0) * 100, 2) AS "上步转化率"
FROM base
WHERE "prev_users" IS NOT NULL
ORDER BY "上步转化率" ASC
LIMIT 1000
```

## 2. 超时/失败，耗时 16.34s，数据源 3（flam / mysql）

- SQL Hash：`0a3fcf882f94`
- 样本行数：None
- 错误：`OperationalError: (2013, 'Lost connection to MySQL server during query (timed out)')`
- 使用位置：
  - 看板：新增看板（`bb3ab5f2697a42af98ab90da4679cb77`）；仪表盘：新增首日付费金额；组件：`f784452553f1426ea5097b092deb818a`；路径：new-view

```sql
WITH bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED) AS start_dt,
           CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS end_dt
), cohort AS (
    SELECT e.dt AS cohort_dt,
           e.uid,
           COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.pay1')), '') AS DECIMAL(18,4)), 0) AS pay1
    FROM `event` e
    JOIN bounds b ON e.dt BETWEEN b.start_dt AND b.end_dt
    JOIN `user` u
      ON u.uid = e.uid
     AND u.dt = e.dt
     AND u.prod = 110000038
    WHERE e.prod = 110000038
      AND e.event = 'UserRegister'
)
SELECT STR_TO_DATE(CAST(cohort_dt AS CHAR), '%Y%m%d') AS `日期`,
       ROUND(SUM(pay1), 2) AS `新增首日付费金额`
FROM cohort
GROUP BY cohort_dt
ORDER BY cohort_dt
```

## 3. 超时/失败，耗时 16.30s，数据源 3（flam / mysql）

- SQL Hash：`e2c1ad4a6870`
- 样本行数：None
- 错误：`OperationalError: (2013, 'Lost connection to MySQL server during query (timed out)')`
- 使用位置：
  - 看板：渠道分析（`5cee4cf41a024c56ac9de0e3aef9aefe`）；仪表盘：各渠道新增留存；组件：`63e03c7e2ad34ad58321892998497a85`；路径：new-view
  - 看板：核心看板（`6d50bd7dfc9f46ba961d636814c3294d`）；仪表盘：各渠道新增留存；组件：`f39bac6b01784ca5b92c60ffe4348756`；路径：new-view

```sql
WITH bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 36 DAY), '%Y%m%d') AS SIGNED) AS start_dt,
           CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 8 DAY), '%Y%m%d') AS SIGNED) AS end_dt,
           CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS data_end_dt
), cohort AS (
    SELECT e.dt AS cohort_dt,
           CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS d1_dt,
           CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL 3 DAY), '%Y%m%d') AS SIGNED) AS d3_dt,
           CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED) AS d7_dt,
           e.uid,
           COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.mediaSource')), ''), NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.campaignName')), ''), '未知') AS channel
    FROM `event` e
    JOIN bounds b ON e.dt BETWEEN b.start_dt AND b.end_dt
    WHERE e.prod = 110000038
      AND e.event = 'UserRegister'
), active AS (
    SELECT e.dt,
           e.uid
    FROM `event` e
    JOIN bounds b ON e.dt BETWEEN CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(b.start_dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AND b.data_end_dt
    WHERE e.prod = 110000038
      AND e.event = 'UserActive'
    GROUP BY e.dt, e.uid
)
SELECT STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d') AS `日期`,
       c.channel AS `渠道`,
       COUNT(DISTINCT c.uid) AS `用户注册用户数`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = c.d1_dt THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `第1日`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = c.d3_dt THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `第3日`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = c.d7_dt THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `第7日`
FROM cohort c
LEFT JOIN active a
  ON a.uid = c.uid
 AND a.dt IN (c.d1_dt, c.d3_dt, c.d7_dt)
GROUP BY c.cohort_dt, c.channel
ORDER BY c.cohort_dt, c.channel
LIMIT 300
```

## 4. 超时/失败，耗时 16.29s，数据源 3（flam / mysql）

- SQL Hash：`e6febb2af8c1`
- 样本行数：None
- 错误：`OperationalError: (2013, 'Lost connection to MySQL server during query (timed out)')`
- 使用位置：
  - 看板：渠道分析（`5cee4cf41a024c56ac9de0e3aef9aefe`）；仪表盘：付费金额（按渠道）；组件：`8b1c7fa28da041afaf91d4a834a9a84a`；路径：new-view

```sql
WITH pay_event_users AS (
    SELECT e.dt,
           e.uid
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
      AND e.event IN ('PayBuyRet','PayBuyRetBenifit','PayBuyRetSandBox','PayFinish','ServerPayLog','ep_pay_purchase_finish','ep_pay_update_db_finish')
      AND e.prod = 110000038
    GROUP BY e.dt, e.uid
), user_pay_delta AS (
    SELECT pe.dt,
           pe.uid,
           COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.adinfo, '$.mediaSource')), ''), NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.adinfo, '$.campaignName')), ''), '未知') AS channel,
           GREATEST(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.paytotal')), '') AS DECIMAL(18,4)), 0) - COALESCE(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(p.pay, '$.paytotal')), '') AS DECIMAL(18,4)), 0), 0), 0) AS pay_amount
    FROM pay_event_users pe
    JOIN `user` u
      ON u.dt = pe.dt
     AND u.uid = pe.uid
     AND u.prod = 110000038
    LEFT JOIN `user` p
      ON p.uid = pe.uid
     AND p.dt = CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(pe.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
     AND p.prod = 110000038
)
SELECT STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS `日期`,
       channel AS `渠道`,
       ROUND(SUM(pay_amount), 2) AS `付费金额`
FROM user_pay_delta
GROUP BY dt, channel
ORDER BY dt, channel
LIMIT 300
```

## 5. 超时/失败，耗时 16.29s，数据源 3（flam / mysql）

- SQL Hash：`5a5c5ee0ee5a`
- 样本行数：None
- 错误：`OperationalError: (2013, 'Lost connection to MySQL server during query (timed out)')`
- 使用位置：
  - 看板：333（`3e086461245d4b91b7b1fcaf3f42640b`）；仪表盘：美国 6 月 18 日后新增用户 LTV；组件：`2187046412636823552`；路径：new-view

```sql
WITH cohort AS
  (SELECT `u`.`dt` AS `cohort_dt`,
          `u`.`uid`,
          CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(`u`.`dt` AS CHAR), '%Y%m%d'), INTERVAL 2 DAY), '%Y%m%d') AS SIGNED) AS `d3_dt`,
          CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(`u`.`dt` AS CHAR), '%Y%m%d'), INTERVAL 6 DAY), '%Y%m%d') AS SIGNED) AS `d7_dt`
   FROM `user` `u`
   WHERE `u`.`dt` BETWEEN 20260618 AND 20260630
     AND `u`.`prod` = 110000038
     AND JSON_UNQUOTE(JSON_EXTRACT(`u`.`userinfo`, '$.regdate')) = CAST(`u`.`dt` AS CHAR)
     AND JSON_UNQUOTE(JSON_EXTRACT(`u`.`userinfo`, '$.country')) = 'US')
SELECT STR_TO_DATE(CAST(`c`.`cohort_dt` AS CHAR), '%Y%m%d') AS `注册日期`,
       COUNT(DISTINCT `c`.`uid`) AS `新增用户数`,
       ROUND(SUM(CASE
                     WHEN `s`.`dt` = `c`.`d3_dt` THEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(`s`.`pay`, '$.pay3')), '') AS DECIMAL(18, 4)), 0)
                 END) / NULLIF(COUNT(DISTINCT `c`.`uid`), 0), 2) AS `3 日 LTV`,
       ROUND(SUM(CASE
                     WHEN `s`.`dt` = `c`.`d7_dt` THEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(`s`.`pay`, '$.pay7')), '') AS DECIMAL(18, 4)), 0)
                 END) / NULLIF(COUNT(DISTINCT `c`.`uid`), 0), 2) AS `7 日 LTV`
FROM `cohort` `c`
LEFT JOIN `user` `s` ON `s`.`uid` = `c`.`uid`
AND `s`.`prod` = 110000038
AND `s`.`dt` IN (`c`.`d3_dt`,
                 `c`.`d7_dt`)
GROUP BY `c`.`cohort_dt`
ORDER BY `c`.`cohort_dt`
LIMIT 1000
```

## 6. 超时/失败，耗时 16.27s，数据源 3（flam / mysql）

- SQL Hash：`d406107faa0d`
- 样本行数：None
- 错误：`OperationalError: (2013, 'Lost connection to MySQL server during query (timed out)')`
- 使用位置：
  - 看板：投放看板（`e423819a72454bc9ab71646d41aa5fd6`）；仪表盘：各渠道注册与付费；组件：`531012d01f104a509da2d1926692ee1d`；路径：new-view

```sql
WITH bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED) AS start_dt,
           CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS max_dt
), cohort AS (
    SELECT u.dt AS cohort_dt,
           u.uid,
           COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.adinfo, '$.mediaSource')), ''), NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.adinfo, '$.campaignName')), ''), '未知') AS channel,
           COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.pay1')), '') AS DECIMAL(18,4)), 0) AS pay1,
           CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 6 DAY), '%Y%m%d') AS SIGNED) AS d7_dt,
           b.max_dt
    FROM `user` u
    JOIN bounds b ON u.dt BETWEEN b.start_dt AND b.max_dt
    WHERE u.prod = 110000038
      AND JSON_UNQUOTE(JSON_EXTRACT(u.userinfo, '$.regdate')) = CAST(u.dt AS CHAR)
)
SELECT STR_TO_DATE(CAST(cohort_dt AS CHAR), '%Y%m%d') AS `日期`,
       channel AS `渠道`,
       COUNT(DISTINCT c.uid) AS `账号注册用户数`,
       ROUND(SUM(c.pay1), 2) AS `首日付费金额`,
       ROUND(SUM(CASE WHEN d7.dt IS NOT NULL THEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(d7.pay, '$.pay7')), '') AS DECIMAL(18,4)), 0) END), 2) AS `7日累计付费金额`,
       ROUND(SUM(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(latest.pay, '$.paytotal')), '') AS DECIMAL(18,4)), 0)), 2) AS `累计付费金额`
FROM cohort c
LEFT JOIN `user` d7
  ON d7.uid = c.uid
 AND d7.prod = 110000038
 AND d7.dt = c.d7_dt
LEFT JOIN `user` latest
  ON latest.uid = c.uid
 AND latest.prod = 110000038
 AND latest.dt = c.max_dt
GROUP BY cohort_dt, channel
ORDER BY cohort_dt DESC, `累计付费金额` DESC
LIMIT 300
```

## 7. 超时/失败，耗时 16.27s，数据源 3（flam / mysql）

- SQL Hash：`b8c1ea1174c0`
- 样本行数：None
- 错误：`OperationalError: (2013, 'Lost connection to MySQL server during query (timed out)')`
- 使用位置：
  - 看板：核心看板（`6d50bd7dfc9f46ba961d636814c3294d`）；仪表盘：累计付费用户趋势；组件：`b9043b8bca964589949a11c198154af4`；路径：new-view

```sql
WITH bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED) AS start_dt,
           CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS max_dt
)
SELECT STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d') AS `日期`,
       COUNT(DISTINCT CASE WHEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.paytotal')), '') AS DECIMAL(18,4)), 0) > 0 THEN u.uid END) AS `累计付费用户数`
FROM `user` u
JOIN bounds b ON u.dt BETWEEN b.start_dt AND b.max_dt
WHERE u.prod = 110000038
GROUP BY u.dt
ORDER BY u.dt
```

## 8. 超时/失败，耗时 16.27s，数据源 3（flam / mysql）

- SQL Hash：`2109058600d4`
- 样本行数：None
- 错误：`OperationalError: (2013, 'Lost connection to MySQL server during query (timed out)')`
- 使用位置：
  - 看板：核心看板（`6d50bd7dfc9f46ba961d636814c3294d`）；仪表盘：累计付费率；组件：`e300602c05804ecc93123625f9bafa3a`；路径：new-view

```sql
WITH bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED) AS start_dt,
           CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS max_dt
)
SELECT STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d') AS `日期`,
       ROUND(COUNT(DISTINCT CASE WHEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.paytotal')), '') AS DECIMAL(18,4)), 0) > 0 THEN u.uid END) / NULLIF(COUNT(DISTINCT u.uid), 0) * 100, 2) AS `累计付费率`
FROM `user` u
JOIN bounds b ON u.dt BETWEEN b.start_dt AND b.max_dt
WHERE u.prod = 110000038
GROUP BY u.dt
ORDER BY u.dt
```

## 9. 超时/失败，耗时 16.26s，数据源 3（flam / mysql）

- SQL Hash：`fb202d3678b7`
- 样本行数：None
- 错误：`OperationalError: (2013, 'Lost connection to MySQL server during query (timed out)')`
- 使用位置：
  - 看板：核心看板（`6d50bd7dfc9f46ba961d636814c3294d`）；仪表盘：ARPU与ARPPU；组件：`6fce0cfb227b47828b41fd3c5cc736d5`；路径：new-view

```sql
WITH pay_event_users AS (
    SELECT e.dt,
           e.uid,
           COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.userinfo, '$.country')), ''), '未知') AS country
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
      AND e.event IN ('PayBuyRet','PayBuyRetBenifit','PayBuyRetSandBox','PayFinish','ServerPayLog','ep_pay_purchase_finish','ep_pay_update_db_finish')
      AND e.prod = 110000038
    GROUP BY e.dt, e.uid, country
), user_pay_delta AS (
    SELECT pe.dt,
           pe.country,
           pe.uid,
           GREATEST(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.paytotal')), '') AS DECIMAL(18,4)), 0) - COALESCE(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(p.pay, '$.paytotal')), '') AS DECIMAL(18,4)), 0), 0), 0) AS pay_amount
    FROM pay_event_users pe
    JOIN `user` u
      ON u.dt = pe.dt
     AND u.uid = pe.uid
     AND u.prod = 110000038
    LEFT JOIN `user` p
      ON p.uid = pe.uid
     AND p.dt = CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(pe.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
     AND p.prod = 110000038
), daily_pay AS (
    SELECT dt,
           country,
           ROUND(SUM(pay_amount), 2) AS pay_amount,
           COUNT(DISTINCT CASE WHEN pay_amount > 0 THEN uid END) AS pay_users
    FROM user_pay_delta
    GROUP BY dt, country
), daily_active AS (
    SELECT e.dt,
           COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.userinfo, '$.country')), ''), '未知') AS country,
           COUNT(DISTINCT e.uid) AS active_users
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
      AND e.event IN ('UserActive')
      AND e.prod = 110000038
    GROUP BY e.dt, country
)
SELECT STR_TO_DATE(CAST(d.dt AS CHAR), '%Y%m%d') AS `日期`,
       d.country AS `国家`,
       ROUND(COALESCE(p.pay_amount, 0) / NULLIF(d.active_users, 0), 2) AS `ARPU`,
       ROUND(COALESCE(p.pay_amount, 0) / NULLIF(p.pay_users, 0), 2) AS `ARPPU`
FROM daily_active d
LEFT JOIN daily_pay p ON p.dt = d.dt AND p.country = d.country
ORDER BY d.dt, d.country
```

## 10. 超时/失败，耗时 16.24s，数据源 3（flam / mysql）

- SQL Hash：`d8d76f6a9777`
- 样本行数：None
- 错误：`OperationalError: (2013, 'Lost connection to MySQL server during query (timed out)')`
- 使用位置：
  - 看板：付费概览（`259414f219f94aacaa46f4e531646b9d`）；仪表盘：新增用户30日LTV；组件：`6391d385e5084c0f86351ae088d3c336`；路径：new-view

```sql
WITH bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED) AS start_dt,
           CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS end_dt
), cohort AS (
    SELECT u.dt AS cohort_dt,
           u.uid,
           u.dt AS d1_dt,
           CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 2 DAY), '%Y%m%d') AS SIGNED) AS d3_dt,
           CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 6 DAY), '%Y%m%d') AS SIGNED) AS d7_dt,
           CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 13 DAY), '%Y%m%d') AS SIGNED) AS d14_dt,
           CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 29 DAY), '%Y%m%d') AS SIGNED) AS d30_dt
    FROM `user` u
    JOIN bounds b ON u.dt BETWEEN b.start_dt AND b.end_dt
    WHERE u.prod = 110000038
      AND JSON_UNQUOTE(JSON_EXTRACT(u.userinfo, '$.regdate')) = CAST(u.dt AS CHAR)
), cohort_size AS (
    SELECT cohort_dt,
           COUNT(DISTINCT uid) AS new_users
    FROM cohort
    GROUP BY cohort_dt
), pay_windows AS (
    SELECT c.cohort_dt,
           COUNT(DISTINCT CASE WHEN s.dt = c.d1_dt THEN s.uid END) AS users_1d,
           COUNT(DISTINCT CASE WHEN s.dt = c.d3_dt THEN s.uid END) AS users_3d,
           COUNT(DISTINCT CASE WHEN s.dt = c.d7_dt THEN s.uid END) AS users_7d,
           COUNT(DISTINCT CASE WHEN s.dt = c.d14_dt THEN s.uid END) AS users_14d,
           COUNT(DISTINCT CASE WHEN s.dt = c.d30_dt THEN s.uid END) AS users_30d,
           SUM(CASE WHEN s.dt = c.d1_dt THEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(s.pay, '$.pay1')), '') AS DECIMAL(18,4)), 0) END) AS pay_1d,
           SUM(CASE WHEN s.dt = c.d3_dt THEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(s.pay, '$.pay3')), '') AS DECIMAL(18,4)), 0) END) AS pay_3d,
           SUM(CASE WHEN s.dt = c.d7_dt THEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(s.pay, '$.pay7')), '') AS DECIMAL(18,4)), 0) END) AS pay_7d,
           SUM(CASE WHEN s.dt = c.d14_dt THEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(s.pay, '$.pay14')), '') AS DECIMAL(18,4)), 0) END) AS pay_14d,
           SUM(CASE WHEN s.dt = c.d30_dt THEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(s.pay, '$.pay30')), '') AS DECIMAL(18,4)), 0) END) AS pay_30d
    FROM cohort c
    LEFT JOIN `user` s
      ON s.uid = c.uid
     AND s.prod = 110000038
     AND s.dt IN (c.d1_dt, c.d3_dt, c.d7_dt, c.d14_dt, c.d30_dt)
    GROUP BY c.cohort_dt
)
SELECT DATE_FORMAT(STR_TO_DATE(CAST(cs.cohort_dt AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS cohort_date,
       cs.new_users,
       ROUND(CASE WHEN pw.users_1d > 0 THEN pw.pay_1d / NULLIF(cs.new_users, 0) END, 4) AS ltv_1d,
       ROUND(CASE WHEN pw.users_3d > 0 THEN pw.pay_3d / NULLIF(cs.new_users, 0) END, 4) AS ltv_3d,
       ROUND(CASE WHEN pw.users_7d > 0 THEN pw.pay_7d / NULLIF(cs.new_users, 0) END, 4) AS ltv_7d,
       ROUND(CASE WHEN pw.users_14d > 0 THEN pw.pay_14d / NULLIF(cs.new_users, 0) END, 4) AS ltv_14d,
       ROUND(CASE WHEN pw.users_30d > 0 THEN pw.pay_30d / NULLIF(cs.new_users, 0) END, 4) AS ltv_30d
FROM cohort_size cs
JOIN pay_windows pw ON pw.cohort_dt = cs.cohort_dt
ORDER BY cs.cohort_dt
```

## 11. 超时/失败，耗时 16.23s，数据源 3（flam / mysql）

- SQL Hash：`f1eb2a2c05e4`
- 样本行数：None
- 错误：`OperationalError: (2013, 'Lost connection to MySQL server during query (timed out)')`
- 使用位置：
  - 看板：核心看板（`6d50bd7dfc9f46ba961d636814c3294d`）；仪表盘：新手引导漏斗转化；组件：`73cfeb49a58a44799e5a91371fbe296d`；路径：new-view

```sql
WITH cohort AS (
    SELECT u.uid,
           u.dt AS cohort_dt
    FROM `user` u
    WHERE u.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
      AND u.prod = 110000038
      AND JSON_UNQUOTE(JSON_EXTRACT(u.userinfo, '$.regdate')) = CAST(u.dt AS CHAR)
), event_window AS (
    SELECT e.uid,
           e.event
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
      AND e.event IN ('EnterGame','Login','UserLogin','NewUserGuideStart','DialogueStart','NewUserGuide','DialogueEnd','ChapterTaskReward','TaskReward')
      AND e.prod = 110000038
), step_users AS (
    SELECT 1 AS step_order, '账号注册' AS step_name, COUNT(DISTINCT c.uid) AS users
    FROM cohort c
    UNION ALL
    SELECT 2, '进入游戏', COUNT(DISTINCT c.uid)
    FROM cohort c
    JOIN event_window e ON e.uid = c.uid AND e.event IN ('EnterGame','Login','UserLogin')
    UNION ALL
    SELECT 3, '引导开始', COUNT(DISTINCT c.uid)
    FROM cohort c
    JOIN event_window e ON e.uid = c.uid AND e.event IN ('NewUserGuideStart','DialogueStart')
    UNION ALL
    SELECT 4, '引导完成', COUNT(DISTINCT c.uid)
    FROM cohort c
    JOIN event_window e ON e.uid = c.uid AND e.event IN ('NewUserGuide','DialogueEnd')
    UNION ALL
    SELECT 5, '章节/任务领奖', COUNT(DISTINCT c.uid)
    FROM cohort c
    JOIN event_window e ON e.uid = c.uid AND e.event IN ('ChapterTaskReward','TaskReward')
), calc AS (
    SELECT s.step_order,
           s.step_name,
           s.users,
           base.users AS start_users,
           COALESCE(prev.users, s.users) AS prev_users
    FROM step_users s
    LEFT JOIN step_users base ON base.step_order = 1
    LEFT JOIN step_users prev ON prev.step_order = s.step_order - 1
)
SELECT step_order,
       step_name AS `新手步骤`,
       users AS `用户数`,
       ROUND(users / NULLIF(start_users, 0) * 100, 2) AS `整体转化率`,
       ROUND(users / NULLIF(COALESCE(prev_users, users), 0) * 100, 2) AS `上步转化率`,
       GREATEST(COALESCE(prev_users, users) - users, 0) AS `流失人数`
FROM calc
ORDER BY step_order
```

## 12. 超时/失败，耗时 16.23s，数据源 3（flam / mysql）

- SQL Hash：`2544613ecaa9`
- 样本行数：None
- 错误：`OperationalError: (2013, 'Lost connection to MySQL server during query (timed out)')`
- 使用位置：
  - 看板：付费概览（`259414f219f94aacaa46f4e531646b9d`）；仪表盘：付费情况；组件：`f75122a83c84441381fe77a551f69a28`；路径：new-view

```sql
WITH pay_event_users AS (
    SELECT e.dt,
           e.uid
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
      AND e.event IN ('PayBuyRet','PayBuyRetBenifit','PayBuyRetSandBox','PayFinish','ServerPayLog','ep_pay_purchase_finish','ep_pay_update_db_finish')
      AND e.prod = 110000038
    GROUP BY e.dt, e.uid
), user_pay_delta AS (
    SELECT pe.dt,
           pe.uid,
           GREATEST(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.paytotal')), '') AS DECIMAL(18,4)), 0) - COALESCE(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(p.pay, '$.paytotal')), '') AS DECIMAL(18,4)), 0), 0), 0) AS pay_amount
    FROM pay_event_users pe
    JOIN `user` u
      ON u.dt = pe.dt
     AND u.uid = pe.uid
     AND u.prod = 110000038
    LEFT JOIN `user` p
      ON p.uid = pe.uid
     AND p.dt = CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(pe.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
     AND p.prod = 110000038
), daily_pay AS (
    SELECT dt,
           ROUND(SUM(pay_amount), 2) AS pay_amount,
           COUNT(DISTINCT CASE WHEN pay_amount > 0 THEN uid END) AS pay_users
    FROM user_pay_delta
    GROUP BY dt
), daily_active AS (
    SELECT e.dt,
           COUNT(DISTINCT e.uid) AS active_users
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
      AND e.event IN ('UserActive')
      AND e.prod = 110000038
    GROUP BY e.dt
)
SELECT STR_TO_DATE(CAST(d.dt AS CHAR), '%Y%m%d') AS `日期`,
       COALESCE(p.pay_users, 0) AS `付费用户数`,
       COALESCE(p.pay_amount, 0) AS `付费总额`,
       ROUND(COALESCE(p.pay_amount, 0) / NULLIF(d.active_users, 0), 2) AS `ARPU`,
       ROUND(COALESCE(p.pay_amount, 0) / NULLIF(p.pay_users, 0), 2) AS `ARPPU`,
       ROUND(COALESCE(p.pay_users, 0) / NULLIF(d.active_users, 0) * 100, 2) AS `付费渗透率`
FROM daily_active d
LEFT JOIN daily_pay p ON p.dt = d.dt
ORDER BY d.dt
```

## 13. 超时/失败，耗时 16.22s，数据源 3（flam / mysql）

- SQL Hash：`00384c4bc344`
- 样本行数：None
- 错误：`OperationalError: (2013, 'Lost connection to MySQL server during query (timed out)')`
- 使用位置：
  - 看板：222（`5028ab5aceda4ddbba77e4e10ef4cd09`）；仪表盘：七日留存趋势；组件：`2186803509163368448`；路径：new-view

```sql
WITH bounds AS
  (SELECT CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 36 DAY), '%Y%m%d') AS SIGNED) AS start_dt,
          CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 8 DAY), '%Y%m%d') AS SIGNED) AS end_dt,
          CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS data_end_dt),
     cohort AS
  (SELECT e.dt AS cohort_dt,
          CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED) AS d7_dt,
          e.uid
   FROM `event` e
   JOIN bounds b ON e.dt BETWEEN b.start_dt AND b.end_dt
   WHERE e.prod = 110000038
     AND e.event = 'UserRegister'),
     active AS
  (SELECT e.dt,
          e.uid
   FROM `event` e
   JOIN bounds b ON e.dt BETWEEN CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(b.start_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED) AND b.data_end_dt
   WHERE e.prod = 110000038
     AND e.event = 'UserActive'
   GROUP BY e.dt,
            e.uid),
     retained AS
  (SELECT c.cohort_dt,
          COUNT(DISTINCT c.uid) AS d7_retained_users
   FROM cohort c
   JOIN active a ON a.uid = c.uid
   AND a.dt = c.d7_dt
   GROUP BY c.cohort_dt)
SELECT STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d') AS `日期`,
       COUNT(DISTINCT c.uid) AS `注册用户数`,
       COALESCE(r.d7_retained_users, 0) AS `七日留存用户数`,
       ROUND(COALESCE(r.d7_retained_users, 0) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `七日留存率`
FROM cohort c
LEFT JOIN retained r ON r.cohort_dt = c.cohort_dt
GROUP BY c.cohort_dt,
         r.d7_retained_users
ORDER BY c.cohort_dt
LIMIT 1000
```

## 14. 超时/失败，耗时 16.21s，数据源 3（flam / mysql）

- SQL Hash：`e1996858bc18`
- 样本行数：None
- 错误：`OperationalError: (2013, 'Lost connection to MySQL server during query (timed out)')`
- 使用位置：
  - 看板：养成看板（`1683de014d814e90b2c6dc002df8da1f`）；仪表盘：SSR英雄的等级分布；组件：`78ddbc37336844b1852ddeaef72f7ecc`；路径：new-view

```sql
WITH latest_key AS (
    SELECT e.uid,
           COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.ed_heroId')), ''), NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.captainId')), ''), '未知') AS hero_id,
           MAX(CONCAT(CAST(e.dt AS CHAR), LPAD(CAST(e.time AS CHAR), 20, '0'))) AS latest_key
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 29 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
      AND e.event IN ('HeroLevelUp','HeroStarUp')
      AND e.prod = 110000038
    GROUP BY e.uid, hero_id
), latest AS (
    SELECT e.uid,
           COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.ed_heroId')), ''), NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.captainId')), ''), '未知') AS hero_id,
           COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.ed_heroStar')), ''), NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.ed_newStar')), ''), '未知') AS hero_star,
           COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.ed_currentLevel')), '') AS DECIMAL(18,4)), CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.ed_heroLevel')), '') AS DECIMAL(18,4)), 0) AS hero_level
    FROM `event` e
    JOIN latest_key l
      ON l.uid = e.uid
     AND l.hero_id = COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.ed_heroId')), ''), NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.captainId')), ''), '未知')
     AND l.latest_key = CONCAT(CAST(e.dt AS CHAR), LPAD(CAST(e.time AS CHAR), 20, '0'))
    WHERE e.event IN ('HeroLevelUp','HeroStarUp')
      AND e.prod = 110000038
)
SELECT hero_id AS `将领ID`,
       hero_star AS `英雄星级`,
       COUNT(DISTINCT uid) AS `全部用户`,
       COUNT(DISTINCT CASE WHEN hero_level BETWEEN 1 AND 10 THEN uid END) AS `1-10`,
       COUNT(DISTINCT CASE WHEN hero_level BETWEEN 11 AND 20 THEN uid END) AS `11-20`,
       COUNT(DISTINCT CASE WHEN hero_level >= 21 THEN uid END) AS `21+`
FROM latest
GROUP BY hero_id, hero_star
ORDER BY `全部用户` DESC
LIMIT 50
```

## 15. 成功，耗时 15.45s，数据源 3（flam / mysql）

- SQL Hash：`477f078a9476`
- 样本行数：12
- 使用位置：
  - 看板：活跃看板（`8c93878ee7af41b9b3832547856d25e6`）；仪表盘：周登录天数分布；组件：`f0793fb6af7845c8be2b39e2d7ea523f`；路径：new-view

```sql
WITH weeks AS (
    SELECT DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY) AS latest_week_start
), bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(latest_week_start, INTERVAL 11 WEEK), '%Y%m%d') AS SIGNED) AS start_dt,
           CAST(DATE_FORMAT(DATE_ADD(latest_week_start, INTERVAL 6 DAY), '%Y%m%d') AS SIGNED) AS end_dt
    FROM weeks
), user_week AS (
    SELECT DATE_SUB(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL WEEKDAY(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d')) DAY) AS week_start,
           e.uid,
           COUNT(DISTINCT e.dt) AS login_days
    FROM `event` e
    JOIN bounds b ON TRUE
    WHERE e.dt BETWEEN b.start_dt AND b.end_dt
      AND e.event IN ('UserActive')
      AND e.prod = 110000038
    GROUP BY week_start, e.uid
)
SELECT week_start AS `周`,
       COUNT(DISTINCT uid) AS `全部用户`,
       SUM(CASE WHEN login_days = 1 THEN 1 ELSE 0 END) AS `1天`,
       SUM(CASE WHEN login_days = 2 THEN 1 ELSE 0 END) AS `2天`,
       SUM(CASE WHEN login_days = 3 THEN 1 ELSE 0 END) AS `3天`,
       SUM(CASE WHEN login_days = 4 THEN 1 ELSE 0 END) AS `4天`,
       SUM(CASE WHEN login_days = 5 THEN 1 ELSE 0 END) AS `5天`,
       SUM(CASE WHEN login_days = 6 THEN 1 ELSE 0 END) AS `6天`,
       SUM(CASE WHEN login_days >= 7 THEN 1 ELSE 0 END) AS `7天`
FROM user_week
GROUP BY week_start
ORDER BY week_start
```

## 16. 成功，耗时 15.28s，数据源 3（flam / mysql）

- SQL Hash：`ec21aca4ff5a`
- 样本行数：28
- 使用位置：
  - 看板：活动分析（`29ea652e2969440b91899cfb254dd0ca`）；仪表盘：参与节日活动的后续7日付费留存率；组件：`095b1cf41cd64844b1f78f07ceccb7bf`；路径：new-view

```sql
WITH participants AS (
    SELECT e.uid, MIN(e.dt) AS participate_dt
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 35 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
      AND e.event IN ('ActivityAllianceBossBattleRet','ActivityAllianceBossChoose','ActivityAllianceBossDonation','ActivityAllianceBossReward','ActivityWorldBoss','AllianceDuelAlliancePoint','AllianceDuelPersonalPoint','AllianceDuelBoxOpen')
      AND e.prod = 110000038
    GROUP BY e.uid
), user_pay AS (
    SELECT p.participate_dt,
           COUNT(DISTINCT p.uid) AS participants,
           COUNT(DISTINCT CASE WHEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.pay1')), '') AS DECIMAL(18,4)), 0) > 0 THEN p.uid END) AS pay0,
           COUNT(DISTINCT CASE WHEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.pay7')), '') AS DECIMAL(18,4)), 0) > 0 THEN p.uid END) AS pay7
    FROM participants p
    LEFT JOIN `user` u ON u.uid = p.uid AND u.dt = p.participate_dt AND u.prod = 110000038
    WHERE p.participate_dt <= CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 8 DAY), '%Y%m%d') AS SIGNED)
    GROUP BY p.participate_dt
)
SELECT STR_TO_DATE(CAST(participate_dt AS CHAR), '%Y%m%d') AS `日期`,
       participants AS `参与节日活动用户数`,
       ROUND(pay0 / NULLIF(participants, 0) * 100, 2) AS `当日`,
       ROUND(pay7 / NULLIF(participants, 0) * 100, 2) AS `第7日`
FROM user_pay
ORDER BY participate_dt
```

## 17. 成功，耗时 14.24s，数据源 3（flam / mysql）

- SQL Hash：`04177a9655d1`
- 样本行数：28
- 使用位置：
  - 看板：新增看板（`bb3ab5f2697a42af98ab90da4679cb77`）；仪表盘：新增用户次日留存；组件：`f0d759307a304043883a23499a281b97`；路径：new-view

```sql
WITH bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 29 DAY), '%Y%m%d') AS SIGNED) AS start_dt,
           CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 2 DAY), '%Y%m%d') AS SIGNED) AS end_dt
), cohort AS (
    SELECT e.dt AS cohort_dt,
           CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS d1_dt,
           e.uid
    FROM `event` e
    JOIN bounds b ON e.dt BETWEEN b.start_dt AND b.end_dt
    WHERE e.prod = 110000038
      AND e.event = 'UserRegister'
), active AS (
    SELECT e.dt,
           e.uid
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 28 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
      AND e.prod = 110000038
      AND e.event = 'UserActive'
    GROUP BY e.dt, e.uid
), retained AS (
    SELECT c.cohort_dt,
           COUNT(DISTINCT c.uid) AS d1_retained_users
    FROM cohort c
    JOIN active a ON a.uid = c.uid AND a.dt = c.d1_dt
    GROUP BY c.cohort_dt
)
SELECT STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d') AS cohort_date,
       COUNT(DISTINCT c.uid) AS new_users,
       COALESCE(r.d1_retained_users, 0) AS d1_retained_users,
       ROUND(COALESCE(r.d1_retained_users, 0) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS d1_retention_pct
FROM cohort c
LEFT JOIN retained r ON r.cohort_dt = c.cohort_dt
GROUP BY c.cohort_dt, r.d1_retained_users
ORDER BY c.cohort_dt
```

## 18. 成功，耗时 13.86s，数据源 3（flam / mysql）

- SQL Hash：`1333837a9e78`
- 样本行数：127
- 使用位置：
  - 看板：渠道分析（`5cee4cf41a024c56ac9de0e3aef9aefe`）；仪表盘：付费用户数（按渠道）；组件：`24a51da63ed84379adbec45927500dce`；路径：new-view

```sql
WITH pay_event_users AS (
    SELECT e.dt,
           e.uid
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
      AND e.event IN ('PayBuyRet','PayBuyRetBenifit','PayBuyRetSandBox','PayFinish','ServerPayLog','ep_pay_purchase_finish','ep_pay_update_db_finish')
      AND e.prod = 110000038
    GROUP BY e.dt, e.uid
), user_pay_delta AS (
    SELECT pe.dt,
           pe.uid,
           COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.adinfo, '$.mediaSource')), ''), NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.adinfo, '$.campaignName')), ''), '未知') AS channel,
           GREATEST(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.paytotal')), '') AS DECIMAL(18,4)), 0) - COALESCE(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(p.pay, '$.paytotal')), '') AS DECIMAL(18,4)), 0), 0), 0) AS pay_amount
    FROM pay_event_users pe
    JOIN `user` u
      ON u.dt = pe.dt
     AND u.uid = pe.uid
     AND u.prod = 110000038
    LEFT JOIN `user` p
      ON p.uid = pe.uid
     AND p.dt = CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(pe.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
     AND p.prod = 110000038
)
SELECT STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS `日期`,
       channel AS `渠道`,
       COUNT(DISTINCT CASE WHEN pay_amount > 0 THEN uid END) AS `付费用户数`
FROM user_pay_delta
GROUP BY dt, channel
ORDER BY dt, channel
LIMIT 300
```

## 19. 成功，耗时 13.49s，数据源 3（flam / mysql）

- SQL Hash：`f520095fe2ec`
- 样本行数：30
- 使用位置：
  - 看板：核心看板（`6d50bd7dfc9f46ba961d636814c3294d`）；仪表盘：累计付费金额趋势；组件：`65f52e391c5a430b8c8d2575195082f4`；路径：new-view

```sql
WITH bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED) AS start_dt,
           CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS max_dt
)
SELECT STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d') AS `日期`,
       ROUND(SUM(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.paytotal')), '') AS DECIMAL(18,4)), 0)), 2) AS `累计付费金额`
FROM `user` u
JOIN bounds b ON u.dt BETWEEN b.start_dt AND b.max_dt
WHERE u.prod = 110000038
GROUP BY u.dt
ORDER BY u.dt
```

## 20. 成功，耗时 11.37s，数据源 3（flam / mysql）

- SQL Hash：`f50d554df5d9`
- 样本行数：11
- 使用位置：
  - 看板：活跃看板（`8c93878ee7af41b9b3832547856d25e6`）；仪表盘：MAU；组件：`77aa7f9c7c2c4eb38d821d10379978e7`；路径：new-view

```sql
WITH months AS (
    SELECT DATE_FORMAT(CURDATE(), '%Y-%m-01') AS latest_month_start
), bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(latest_month_start, '%Y-%m-%d'), INTERVAL 11 MONTH), '%Y%m%d') AS SIGNED) AS start_dt,
           CAST(DATE_FORMAT(LAST_DAY(STR_TO_DATE(latest_month_start, '%Y-%m-%d')), '%Y%m%d') AS SIGNED) AS end_dt
    FROM months
)
SELECT DATE_FORMAT(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), '%Y-%m') AS `月份`,
       COUNT(DISTINCT e.uid) AS `MAU`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.end_dt
  AND e.event IN ('UserActive')
  AND e.prod = 110000038
GROUP BY `月份`
ORDER BY `月份`
```

## 21. 成功，耗时 10.82s，数据源 3（flam / mysql）

- SQL Hash：`3b398ef9a08e`
- 样本行数：28
- 使用位置：
  - 看板：活动分析（`29ea652e2969440b91899cfb254dd0ca`）；仪表盘：参与新手活动的后续7日留存率；组件：`9684a569ed034fb0b8a106a9817effaa`；路径：new-view

```sql
WITH participants AS (
    SELECT e.uid, MIN(e.dt) AS participate_dt
    FROM `event` e
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 35 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
      AND e.event IN ('ActivityCommanderTask','ActivityArmsRaceTask','ActivityChestCount')
      AND e.prod = 110000038
    GROUP BY e.uid
), retained AS (
    SELECT p.participate_dt,
           COUNT(DISTINCT p.uid) AS participants,
           COUNT(DISTINCT CASE WHEN u.dt = CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(p.participate_dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
                                AND JSON_UNQUOTE(JSON_EXTRACT(u.remain, '$.remain1')) = '1' THEN p.uid END) AS r1,
           COUNT(DISTINCT CASE WHEN u.dt = CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(p.participate_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED)
                                AND JSON_UNQUOTE(JSON_EXTRACT(u.remain, '$.remain7')) = '1' THEN p.uid END) AS r7
    FROM participants p
    LEFT JOIN `user` u
      ON u.uid = p.uid
     AND u.dt BETWEEN p.participate_dt AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
     AND u.prod = 110000038
    WHERE p.participate_dt <= CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 8 DAY), '%Y%m%d') AS SIGNED)
    GROUP BY p.participate_dt
)
SELECT STR_TO_DATE(CAST(participate_dt AS CHAR), '%Y%m%d') AS `日期`,
       participants AS `参与新手活动用户数`,
       ROUND(r1 / NULLIF(participants, 0) * 100, 2) AS `第1日`,
       ROUND(r7 / NULLIF(participants, 0) * 100, 2) AS `第7日`
FROM retained
ORDER BY participate_dt
```

# 附录：不可用但未计入 >10s 的项目

- 1. 数据源 2（SLG BI Mock 2 - Season War / pg），看板：新建仪表板，仪表盘：开服以来总收入增长曲线，错误：`connect OperationalError: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
`
- 2. 数据源 2（SLG BI Mock 2 - Season War / pg），看板：新建仪表板，仪表盘：欧美市场渠道质量分析，错误：`connect OperationalError: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
`
- 3. 数据源 2（SLG BI Mock 2 - Season War / pg），看板：新建仪表板，仪表盘：赛季水晶经济平衡分析，错误：`connect OperationalError: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
`