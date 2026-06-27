"""Seed 统一业务口径 Data Skills into the 星通智数系统库。

- 不修改任何应用代码，只向系统库 custom_prompt 写入 DATA_SKILL 配置。
- 幂等：重复运行不会产生重复记录，已存在记录会更新到最新口径。
- 目标数据源固定为 core_datasource 中的 'SLG BI Mock'（按名称自动定位 id）。
- Skill 中的示例 SQL 片段均为只读 SELECT，指标在查询时从明细表计算，符合仓库 AGENTS.md 约束。
- Data Skills 写入 custom_prompt：6 个工作空间公开 Skill，4 个 xiaonan 私人 Skill。

运行：
    backend/.venv/Scripts/python.exe tools/seed_slg_bi_training.py
运行后即可在「Data Skills」中看到这些记录，新问答会读取最新配置。
"""
from __future__ import annotations

import datetime

import psycopg
from psycopg.types.json import Jsonb

DB = dict(host="127.0.0.1", port=15432, user="root", password="Password123@pg", dbname="zhishu_bi")
DATASOURCE_NAME = "SLG BI Mock"
XIAONAN_ACCOUNT = "xiaonan"


DATA_SKILLS: list[dict[str, str]] = [
    {
        "slug": "workspace-onboarding-funnel",
        "visibility_scope": "ADMIN_PUBLIC",
        "owner_account": "",
        "name": "SLG Skill：新手引导与早期激活漏斗",
        "description": "用于新手任务通过率、新手引导通过率、新手教程通过率、教程步骤掉点、首次战斗、首次建筑/科技、首付等早期激活链路；教程步骤使用 tutorial_step 和 attributes step，不把事件次数误当用户漏斗。",
        "prompt": """
<!-- data-skill-source:slg-bi-mock:workspace:onboarding-funnel -->
# SLG Skill：新手引导与早期激活漏斗

适用问题：
- 新用户从安装、登录、新手教程、首次战斗、首次建筑升级、首次科技研究到首次付费的转化。
- 新手教程第 3/7/12 步掉点、早期关键节点流失、不同渠道或设备的新手链路对比。
- “新手任务通过率”“新手引导通过率”“新手教程通过率”“新手任务漏斗”“教程步骤掉点”等问题。

必须使用的明细表：
- cohort 用 `dim_player.install_date` 锁定新增玩家。
- 教程步骤用 `fact_events` 中 `event_name='tutorial_step'`，步骤号取 `attributes->>'step'`，转整数可写 `(attributes->>'step')::int`。
- 首战用 `fact_battles`，建筑/科技用 `fact_building_upgrades`、`fact_research`，首付用 `fact_payments`。

SQL 口径：
- 先构造玩家级 `player_level`，一行一个 `player_id`，用 `bool_or` / `exists` 标记每个节点是否完成。
- 漏斗人数必须带前序条件，例如完成第 7 步人数必须同时完成登录、第 3 步和第 7 步。
- 禁止每个步骤独立 `count(distinct player_id)` 后直接 `UNION`，那会导致后序步骤人数大于前序步骤。
- 当用户只问“新手任务/新手引导/新手教程通过率”且未指定首次战斗、建筑、科技、首付等后续节点时，默认返回 `tutorial_step` 每一步的 `step_order`, `step_name`, `users`, `conversion_from_start_pct`, `conversion_from_prev_pct`, `drop_off_users`。
- 不要使用 `activity_type`、`activity_stage` 分析新手任务通过率；它们是活动字段，不是新手教程步骤。
- 不要使用 `fact_events.task_id`，该字段不存在；新手教程步骤在 `attributes` 中。
- 首付只统计 `payment_status='success' AND net_revenue_usd > 0`，不要用 `amount_usd`。

推荐输出：
- 漏斗图：`step_order`, `step_name`, `users`。
- 表格/辅助指标：`conversion_from_start_pct`, `conversion_from_prev_pct`, `drop_off_users`, `drop_off_from_prev_pct`。
- 维度拆解时每次只按一个维度拆，例如 `channel`、`campaign`、`device_tier` 或 `register_server_id`。

参考 SQL：
```sql
WITH obs AS (
  SELECT max(session_start::date) AS max_date FROM fact_sessions
),
cohort AS (
  SELECT p.player_id, p.channel, p.campaign
  FROM dim_player p CROSS JOIN obs
  WHERE p.install_date BETWEEN obs.max_date - 29 AND obs.max_date
),
event_flags AS (
  SELECT e.player_id,
         bool_or(e.event_name = 'login') AS did_login,
         bool_or(e.event_name = 'tutorial_step' AND (e.attributes->>'step')::int >= 3) AS did_tutorial_3,
         bool_or(e.event_name = 'tutorial_step' AND (e.attributes->>'step')::int >= 7) AS did_tutorial_7,
         bool_or(e.event_name = 'tutorial_step' AND (e.attributes->>'step')::int >= 12) AS did_tutorial_12
  FROM fact_events e
  JOIN cohort c ON c.player_id = e.player_id
  GROUP BY e.player_id
),
player_level AS (
  SELECT c.player_id,
         coalesce(ef.did_login, false) AS did_login,
         coalesce(ef.did_tutorial_3, false) AS did_tutorial_3,
         coalesce(ef.did_tutorial_7, false) AS did_tutorial_7,
         coalesce(ef.did_tutorial_12, false) AS did_tutorial_12,
         EXISTS (SELECT 1 FROM fact_battles b WHERE b.player_id = c.player_id) AS did_first_battle,
         EXISTS (SELECT 1 FROM fact_building_upgrades bu WHERE bu.player_id = c.player_id) AS did_building_upgrade,
         EXISTS (SELECT 1 FROM fact_research r WHERE r.player_id = c.player_id) AS did_research,
         EXISTS (
           SELECT 1 FROM fact_payments p
           WHERE p.player_id = c.player_id
             AND p.payment_status = 'success'
             AND p.net_revenue_usd > 0
             AND p.is_first_pay = true
         ) AS did_first_pay
  FROM cohort c
  LEFT JOIN event_flags ef ON ef.player_id = c.player_id
),
steps AS (
  SELECT 1 AS step_order, '登录' AS step_name, count(*) FILTER (WHERE did_login) AS users FROM player_level
  UNION ALL SELECT 2, '完成教程第3步', count(*) FILTER (WHERE did_login AND did_tutorial_3) FROM player_level
  UNION ALL SELECT 3, '完成教程第7步', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7) FROM player_level
  UNION ALL SELECT 4, '完成教程第12步', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12) FROM player_level
  UNION ALL SELECT 5, '首次战斗', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12 AND did_first_battle) FROM player_level
  UNION ALL SELECT 6, '首次建筑升级', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12 AND did_first_battle AND did_building_upgrade) FROM player_level
  UNION ALL SELECT 7, '首次科技研究', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12 AND did_first_battle AND did_building_upgrade AND did_research) FROM player_level
  UNION ALL SELECT 8, '首次成功付费', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12 AND did_first_battle AND did_building_upgrade AND did_research AND did_first_pay) FROM player_level
),
base AS (
  SELECT step_order, step_name, users,
         first_value(users) OVER (ORDER BY step_order) AS start_users,
         lag(users) OVER (ORDER BY step_order) AS prev_users
  FROM steps
)
SELECT step_order,
       step_name,
       users,
       round(users::numeric / nullif(start_users, 0) * 100, 2) AS conversion_from_start_pct,
       round(users::numeric / nullif(prev_users, 0) * 100, 2) AS conversion_from_prev_pct,
       CASE WHEN prev_users IS NULL THEN NULL ELSE prev_users - users END AS drop_off_users
FROM base
ORDER BY step_order;
```
""",
    },
    {
        "slug": "workspace-retention-return-churn",
        "visibility_scope": "ADMIN_PUBLIC",
        "owner_account": "",
        "name": "SLG Skill：留存、沉默与回流",
        "description": "用于 Dn 精确日留存、滚动留存、连续留存、沉默和回流分析，固定 cohort 分母和成熟窗口。",
        "prompt": """
<!-- data-skill-source:slg-bi-mock:workspace:retention-return-churn -->
# SLG Skill：留存、沉默与回流

适用问题：
- D1/D3/D7/D14 留存、某日新增用户后续留存曲线、渠道留存对比。
- 回流用户、沉默用户、连续不活跃 N 天后的召回效果。

必须使用的明细表：
- 新增 cohort 用 `dim_player.install_date`。
- 活跃行为用 `fact_sessions.session_start::date`，不要用 `fact_events` 事件人数替代 DAU/留存活跃。
- 观察基准日取 `fact_sessions` 最大活跃日期，而不是系统当前日期。

SQL 口径：
- 默认 Dn 留存是精确日留存：分母为已成熟 cohort 玩家数，分子为 `lifecycle_day = n` 当天有会话的去重玩家。
- 按生命周期日输出时分母固定，不允许按当天有行为人数重新当分母。
- 未成熟生命周期日返回 NULL 或标注未成熟，不能当 0。
- 回流必须先定义沉默阈值，默认可用连续 7 天无 `fact_sessions` 后再次登录；精确日留存曲线回升不能直接解释为回流。

推荐输出：
- 趋势图：`cohort_date` 或 `lifecycle_day` 为 x，`retention_pct` 为 y。
- 分析表：`cohort_users`, `retained_users`, `retention_pct`, `matured_flag`。
- 回流分析输出：`return_date`, `returned_users`, `inactive_days_before_return`, `prior_active_date`。

参考 SQL：
```sql
WITH obs AS (
  SELECT max(session_start::date) AS max_date FROM fact_sessions
),
days AS (
  SELECT * FROM (VALUES (1), (3), (7), (14)) AS d(lifecycle_day)
),
cohort AS (
  SELECT p.player_id, p.install_date
  FROM dim_player p CROSS JOIN obs
  WHERE p.install_date BETWEEN obs.max_date - 29 AND obs.max_date - 1
),
mature_cohort AS (
  SELECT d.lifecycle_day, c.player_id
  FROM days d
  CROSS JOIN obs
  JOIN cohort c ON c.install_date <= obs.max_date - d.lifecycle_day
)
SELECT m.lifecycle_day,
       count(DISTINCT m.player_id) AS cohort_users,
       count(DISTINCT s.player_id) AS retained_users,
       round(count(DISTINCT s.player_id)::numeric / nullif(count(DISTINCT m.player_id), 0) * 100, 2) AS retention_pct
FROM mature_cohort m
LEFT JOIN fact_sessions s
  ON s.player_id = m.player_id
 AND s.lifecycle_day = m.lifecycle_day
GROUP BY m.lifecycle_day
ORDER BY m.lifecycle_day;
```
""",
    },
    {
        "slug": "workspace-monetization-first-pay-product",
        "visibility_scope": "ADMIN_PUBLIC",
        "owner_account": "",
        "name": "SLG Skill：首付转化与商品收入结构",
        "description": "用于付费率、首充、ARPU/ARPPU、礼包/商品结构，统一使用成功订单净收入。",
        "prompt": """
<!-- data-skill-source:slg-bi-mock:workspace:monetization-first-pay-product -->
# SLG Skill：首付转化与商品收入结构

适用问题：
- 付费率、首付率、ARPU、ARPPU、收入趋势、渠道收入质量。
- 首充礼包、月卡、加速、资源、战争动员、英雄礼包等商品结构。

必须使用的明细表：
- 收入和订单用 `fact_payments`。
- 商品类型和商品名用 `dim_product`。
- 活跃分母用 `fact_sessions`，新增 cohort 分母用 `dim_player.install_date`。

SQL 口径：
- 正式收入默认 `sum(net_revenue_usd)`，必须过滤 `payment_status='success' AND net_revenue_usd > 0`。
- `amount_usd` 是订单原始金额/标价，不可当正式收入。
- 付费用户为成功净收入订单的 `count(distinct player_id)`；订单明细保留 `order_id` 粒度。
- 分析“某一天/某批新增用户的后续付费情况”时，目标 cohort 使用 `dim_player.install_date` 锁定，生命周期使用 `fact_payments.lifecycle_day`，收入使用 `net_revenue_usd`。
- 首付用户优先用 `is_first_pay=true`，或用玩家最早成功支付日推导。
- ARPU/ARPPU 的收入分子均使用成功净收入 `net_revenue_usd`。

推荐输出：
- 指标卡：`cohort_users`, `cumulative_payers`, `total_revenue`, `payer_rate_pct`, `ltv`, `arppu`。
- 生命周期趋势：`lifecycle_day`, `daily_payers`, `daily_revenue`, `cumulative_payers`, `cumulative_revenue`, `cumulative_payer_rate_pct`, `ltv`。
- 商品结构：`product_type`, `product_name`, `orders`, `payers`, `revenue`, `revenue_share_pct`, `arppu`。
- 渠道/国家收入贡献：`channel`, `country`, `payers`, `revenue`, `revenue_share_pct`, `arppu`；图表的主 y 轴必须使用 `revenue` 或 `revenue_share_pct`，不要用 `payers` 代表收入贡献。
- 图表：每日付费节奏可用柱/线；累计收入、累计付费率、LTV 用折线；商品/渠道收入占比可用饼图但只能表达单一收入占比指标；若同时比较收入、人数、ARPPU，优先用表格或柱图。

字段展示名约定：
- 自动生成图表配置时，SELECT 输出别名优先直接使用中文业务名，例如 PostgreSQL 写 `AS "付费人数"`、`AS "净收入"`；图表配置的 value 必须与 SQL 输出别名完全一致。
- 只有在数据库或外部工具明确不支持中文/特殊字符别名时，才退回英文小写别名，并通过 field_labels/chart.name 使用中文展示名。
- `lifecycle_day`/`x_lifecycle_day` 对应中文输出别名“生命周期日”；`cohort_users` 对应“新增用户数”；`daily_payers`/`payers`/`payer_count`/`y_payer_count` 对应“付费人数”；`cumulative_payers` 对应“累计付费人数”。
- `revenue`/`daily_revenue`/`y_revenue` 对应“净收入”；`total_revenue`/`total_net_revenue` 对应“总净收入”；`cumulative_revenue` 对应“累计净收入”。
- `payer_rate_pct`/`daily_pay_rate_pct` 对应“付费率”；`cumulative_payer_rate_pct` 对应“累计付费率”；`revenue_share_pct` 对应“收入占比”；`orders` 对应“订单数”；`arppu` 对应“ARPPU”；`ltv` 对应“LTV”。

新增 cohort 后续付费参考 SQL：
```sql
WITH cohort_params AS (
  SELECT DATE '<用户指定开始日期>' AS cohort_start_date,
         DATE '<用户指定结束日期>' AS cohort_end_date,
         30 AS max_lifecycle_day
),
cohort AS (
  SELECT p.player_id
  FROM dim_player p
  CROSS JOIN cohort_params cp
  WHERE p.install_date BETWEEN cp.cohort_start_date AND cp.cohort_end_date
),
cohort_size AS (
  SELECT count(DISTINCT player_id) AS cohort_users
  FROM cohort
),
days AS (
  SELECT generate_series(0, (SELECT max_lifecycle_day FROM cohort_params)) AS lifecycle_day
),
pay AS (
  SELECT fp.player_id,
         fp.order_id,
         fp.lifecycle_day,
         fp.net_revenue_usd
  FROM fact_payments fp
  JOIN cohort c ON c.player_id = fp.player_id
  CROSS JOIN cohort_params cp
  WHERE fp.payment_status = 'success'
    AND fp.net_revenue_usd > 0
    AND fp.lifecycle_day BETWEEN 0 AND cp.max_lifecycle_day
),
daily AS (
  SELECT lifecycle_day,
         count(DISTINCT player_id) AS daily_payers,
         round(sum(net_revenue_usd)::numeric, 2) AS daily_revenue
  FROM pay
  GROUP BY lifecycle_day
),
first_pay AS (
  SELECT player_id,
         min(lifecycle_day) AS first_pay_day
  FROM pay
  GROUP BY player_id
),
series AS (
  SELECT d.lifecycle_day,
         coalesce(daily.daily_payers, 0) AS daily_payers,
         coalesce(daily.daily_revenue, 0) AS daily_revenue,
         count(DISTINCT first_pay.player_id) AS cumulative_payers
  FROM days d
  LEFT JOIN daily ON daily.lifecycle_day = d.lifecycle_day
  LEFT JOIN first_pay ON first_pay.first_pay_day <= d.lifecycle_day
  GROUP BY d.lifecycle_day, daily.daily_payers, daily.daily_revenue
)
SELECT s.lifecycle_day,
       cs.cohort_users,
       s.daily_payers,
       s.daily_revenue,
       round(s.daily_payers * 100.0 / nullif(cs.cohort_users, 0), 2) AS daily_pay_rate_pct,
       s.cumulative_payers,
       round(s.cumulative_payers * 100.0 / nullif(cs.cohort_users, 0), 2) AS cumulative_payer_rate_pct,
       round(sum(s.daily_revenue) OVER (ORDER BY s.lifecycle_day)::numeric, 2) AS cumulative_revenue,
       round(sum(s.daily_revenue) OVER (ORDER BY s.lifecycle_day)::numeric / nullif(cs.cohort_users, 0), 4) AS ltv
FROM series s
CROSS JOIN cohort_size cs
ORDER BY s.lifecycle_day;
```

商品结构参考 SQL：
```sql
WITH obs AS (
  SELECT max(event_date) AS max_date FROM fact_payments
),
win AS (
  SELECT max_date - 29 AS start_date, max_date FROM obs
),
pay AS (
  SELECT p.player_id,
         p.order_id,
         p.net_revenue_usd,
         p.is_first_pay,
         dp.product_type,
         dp.product_name
  FROM fact_payments p
  JOIN dim_product dp ON dp.product_id = p.product_id
  CROSS JOIN win
  WHERE p.event_date BETWEEN win.start_date AND win.max_date
    AND p.payment_status = 'success'
    AND p.net_revenue_usd > 0
),
by_product AS (
  SELECT product_type,
         product_name,
         count(*) AS orders,
         count(DISTINCT player_id) AS payers,
         count(DISTINCT player_id) FILTER (WHERE is_first_pay) AS first_payers,
         round(sum(net_revenue_usd), 2) AS revenue,
         round(sum(net_revenue_usd) / nullif(count(DISTINCT player_id), 0), 2) AS arppu
  FROM pay
  GROUP BY product_type, product_name
),
total AS (
  SELECT sum(revenue) AS total_revenue FROM by_product
)
SELECT b.product_type,
       b.product_name,
       b.orders,
       b.payers,
       b.first_payers,
       b.revenue,
       b.arppu,
       round(b.revenue / nullif(t.total_revenue, 0) * 100, 2) AS revenue_share_pct
FROM by_product b CROSS JOIN total t
ORDER BY b.revenue DESC;
```
""",
    },
    {
        "slug": "workspace-battle-ecosystem-loss",
        "visibility_scope": "ADMIN_PUBLIC",
        "owner_account": "",
        "name": "SLG Skill：战斗生态、胜率与兵损",
        "description": "用于 PVE、野怪、资源点、PVP 的战斗次数、人数、胜率、兵损、资源掠夺和体力消耗分析。",
        "prompt": """
<!-- data-skill-source:slg-bi-mock:workspace:battle-ecosystem-loss -->
# SLG Skill：战斗生态、胜率与兵损

适用问题：
- PVE 章节、世界野怪、资源点、PVP 的参与规模、胜率、兵损和收益。
- 战斗生态是否健康、某类目标是否过难、PVP 是否导致大量流失风险。

必须使用的明细表：
- 战斗明细用 `fact_battles`，一行是一场战斗结算。
- 玩家当前画像可关联 `dim_player`，但要说明 `current_*` 是当前状态，不代表战斗发生时状态。
- 区服信息可关联 `dim_server`。

SQL 口径：
- 战斗次数 `count(*)`，战斗人数 `count(distinct player_id)`。
- 胜率 = `result='win'` 的战斗次数 / 总战斗次数 * 100。
- 兵损、伤兵、战力变化、资源掠夺、体力消耗分别来自 `troops_lost`, `wounded`, `power_delta`, `resource_looted`, `stamina_spent`。
- 按 `battle_type`, `target_type`, `server_id` 分析；若要按等级/战力段分析，优先说明使用的是 `dim_player.current_level/current_power` 当前状态。

推荐输出：
- 表格/柱图：`battle_type`, `target_type`, `battles`, `battle_users`, `win_rate_pct`, `avg_troops_lost`, `avg_resource_looted`。
- 趋势图：`event_date`, `battles`, `battle_users`, `win_rate_pct`。
- 结论中不要只看胜率，也要结合 `troops_lost`、`wounded`、`stamina_spent` 和 `resource_looted` 判断体验成本。

参考 SQL：
```sql
WITH obs AS (
  SELECT max(event_date) AS max_date FROM fact_battles
),
win AS (
  SELECT max_date - 29 AS start_date, max_date FROM obs
)
SELECT b.battle_type,
       b.target_type,
       count(*) AS battles,
       count(DISTINCT b.player_id) AS battle_users,
       round(count(*) FILTER (WHERE b.result = 'win')::numeric / nullif(count(*), 0) * 100, 2) AS win_rate_pct,
       round(avg(b.troops_sent), 2) AS avg_troops_sent,
       round(avg(b.troops_lost), 2) AS avg_troops_lost,
       round(avg(b.wounded), 2) AS avg_wounded,
       round(avg(b.resource_looted), 2) AS avg_resource_looted,
       round(avg(b.stamina_spent), 2) AS avg_stamina_spent
FROM fact_battles b CROSS JOIN win
WHERE b.event_date BETWEEN win.start_date AND win.max_date
GROUP BY b.battle_type, b.target_type
ORDER BY battles DESC;
```
""",
    },
    {
        "slug": "workspace-resource-growth-economy",
        "visibility_scope": "ADMIN_PUBLIC",
        "owner_account": "",
        "name": "SLG Skill：资源经济与成长消耗",
        "description": "用于资源产出/消耗、建筑升级、科技研究、练兵成长和加速消耗，不用净值掩盖规模。",
        "prompt": """
<!-- data-skill-source:slg-bi-mock:workspace:resource-growth-economy -->
# SLG Skill：资源经济与成长消耗

适用问题：
- 食物、木材、石头、铁、金币的产出消耗结构。
- 建筑、科技、练兵哪个系统消耗最多、成长效率如何、是否存在卡点。

必须使用的明细表：
- 资源流水用 `fact_resource_transactions`。
- 建筑升级用 `fact_building_upgrades`，科技研究用 `fact_research`，练兵用 `fact_army_training`。

SQL 口径：
- 资源产出和消耗必须分开输出：`gain_amount` 看正向资源，`sink_amount` 看消耗绝对值，`net_change_amount` 才是净变化。
- 不要只看正负相加后的净值，否则会掩盖经济系统真实吞吐规模。
- `payment_grant` 是付费相关资源发放，不等同于收入；收入仍来自 `fact_payments.net_revenue_usd`。
- 建筑/科技/练兵可 UNION 成统一任务粒度，比较 `completed_tasks`, `users`, `power_gain`, `duration_seconds`, `speedup_seconds`。

推荐输出：
- 资源结构：`resource_type`, `reason`, `gain_amount`, `sink_amount`, `net_change_amount`, `transactions`, `users`。
- 成长任务：`task_type`, `item_type`, `completed_tasks`, `users`, `total_power_gain`, `avg_duration_hours`, `avg_speedup_hours`。
- 图表：资源产出/消耗用堆叠柱或分组柱；成长效率用表格或条形图。

参考 SQL：
```sql
WITH obs AS (
  SELECT max(event_date) AS max_date FROM fact_resource_transactions
),
win AS (
  SELECT max_date - 29 AS start_date, max_date FROM obs
),
resource_base AS (
  SELECT r.resource_type,
         r.reason,
         coalesce(sum(r.change_amount) FILTER (WHERE r.change_amount > 0), 0) AS gain_amount,
         coalesce(abs(sum(r.change_amount) FILTER (WHERE r.change_amount < 0)), 0) AS sink_amount,
         sum(r.change_amount) AS net_change_amount,
         count(*) AS transactions,
         count(DISTINCT r.player_id) AS users
  FROM fact_resource_transactions r CROSS JOIN win
  WHERE r.event_date BETWEEN win.start_date AND win.max_date
  GROUP BY r.resource_type, r.reason
)
SELECT resource_type,
       reason,
       gain_amount,
       sink_amount,
       net_change_amount,
       transactions,
       users
FROM resource_base
ORDER BY resource_type, gain_amount + sink_amount DESC;
```

成长任务对比：
```sql
WITH obs AS (
  SELECT max(day) AS max_date
  FROM (
    SELECT max(finish_time::date) AS day FROM fact_building_upgrades
    UNION ALL SELECT max(finish_time::date) FROM fact_research
    UNION ALL SELECT max(finish_time::date) FROM fact_army_training
  ) d
),
win AS (
  SELECT max_date - 29 AS start_date, max_date FROM obs
),
tasks AS (
  SELECT 'building' AS task_type, building_type AS item_type, player_id,
         finish_time::date AS finish_date, duration_seconds, speedup_seconds, power_gain
  FROM fact_building_upgrades
  UNION ALL
  SELECT 'research', research_type, player_id,
         finish_time::date, duration_seconds, speedup_seconds, power_gain
  FROM fact_research
  UNION ALL
  SELECT 'army_training', troop_type, player_id,
         finish_time::date, duration_seconds, speedup_seconds, power_gain
  FROM fact_army_training
)
SELECT task_type,
       item_type,
       count(*) AS completed_tasks,
       count(DISTINCT player_id) AS users,
       sum(power_gain) AS total_power_gain,
       round(avg(duration_seconds) / 3600.0, 2) AS avg_duration_hours,
       round(avg(speedup_seconds) / 3600.0, 2) AS avg_speedup_hours
FROM tasks CROSS JOIN win
WHERE finish_date BETWEEN win.start_date AND win.max_date
GROUP BY task_type, item_type
ORDER BY task_type, completed_tasks DESC;
```
""",
    },
    {
        "slug": "workspace-quality-device-release",
        "visibility_scope": "ADMIN_PUBLIC",
        "owner_account": "",
        "name": "SLG Skill：客户端质量、设备与版本问题",
        "description": "用于崩溃、客户端错误、网络错误按设备、平台、版本和构建号定位问题。",
        "prompt": """
<!-- data-skill-source:slg-bi-mock:workspace:quality-device-release -->
# SLG Skill：客户端质量、设备与版本问题

适用问题：
- 崩溃、客户端错误、网络错误的规模、受影响用户、设备/系统/版本分布。
- 某个 app_build、平台、低端设备或网络类型是否异常。

必须使用的明细表：
- 质量事件来自 `fact_events`，条件为 `event_category='quality'` 或 `event_name in ('crash','client_error','network_error')`。
- 会话基数可用 `fact_sessions` 计算同窗口 sessions / active_users，用于归一化问题率。

SQL 口径：
- 问题次数 `count(*)`，受影响用户 `count(distinct player_id)`。
- 维度优先使用 `platform`, `device_tier`, `device_model`, `os_version`, `network_type`, `app_build`, `event_name`。
- 若计算每千会话问题数，分母必须来自同窗口、同维度的 `fact_sessions`，不要用全局会话数。

推荐输出：
- 排查表：`platform`, `device_tier`, `device_model`, `os_version`, `network_type`, `app_build`, `event_name`, `issue_events`, `affected_users`。
- 归一化指标：`issues_per_1k_sessions`, `affected_user_rate_pct`。
- 图表：Top 设备/版本用条形图；问题趋势用折线；高维排查用表格。

参考 SQL：
```sql
WITH obs AS (
  SELECT max(event_date) AS max_date FROM fact_events
),
win AS (
  SELECT max_date - 29 AS start_date, max_date FROM obs
),
issues AS (
  SELECT e.platform,
         e.device_tier,
         e.device_model,
         e.os_version,
         e.network_type,
         e.app_build,
         e.event_name,
         count(*) AS issue_events,
         count(DISTINCT e.player_id) AS affected_users
  FROM fact_events e CROSS JOIN win
  WHERE e.event_date BETWEEN win.start_date AND win.max_date
    AND (e.event_category = 'quality' OR e.event_name IN ('crash', 'client_error', 'network_error'))
  GROUP BY e.platform, e.device_tier, e.device_model, e.os_version, e.network_type, e.app_build, e.event_name
),
sessions AS (
  SELECT s.platform,
         s.device_tier,
         s.device_model,
         s.os_version,
         s.network_type,
         s.app_build,
         count(*) AS sessions,
         count(DISTINCT s.player_id) AS active_users
  FROM fact_sessions s CROSS JOIN win
  WHERE s.session_start::date BETWEEN win.start_date AND win.max_date
  GROUP BY s.platform, s.device_tier, s.device_model, s.os_version, s.network_type, s.app_build
)
SELECT i.platform,
       i.device_tier,
       i.device_model,
       i.os_version,
       i.network_type,
       i.app_build,
       i.event_name,
       i.issue_events,
       i.affected_users,
       round(i.issue_events::numeric / nullif(s.sessions, 0) * 1000, 2) AS issues_per_1k_sessions,
       round(i.affected_users::numeric / nullif(s.active_users, 0) * 100, 2) AS affected_user_rate_pct
FROM issues i
LEFT JOIN sessions s
  ON s.platform = i.platform
 AND s.device_tier = i.device_tier
 AND s.device_model = i.device_model
 AND s.os_version = i.os_version
 AND s.network_type = i.network_type
 AND s.app_build = i.app_build
ORDER BY i.issue_events DESC;
```
""",
    },
    {
        "slug": "xiaonan-channel-retention-payback",
        "visibility_scope": "USER_PRIVATE",
        "owner_account": XIAONAN_ACCOUNT,
        "name": "xiaonan Skill：渠道新增质量与早期回收",
        "description": "xiaonan 私人偏好：看渠道/campaign 新增质量时，同屏比较 D1/D7 留存、首付转化和早期收入。",
        "prompt": """
<!-- data-skill-source:slg-bi-mock:xiaonan:channel-retention-payback -->
# xiaonan Skill：渠道新增质量与早期回收

适用问题：
- “哪个渠道新增质量好”“买量 campaign 留存和付费怎么样”“最近新增的早期回收如何”。

个人分析偏好：
- 默认按 `dim_player.channel` + `campaign` 看新增 cohort，不只看新增人数。
- 至少同时输出：新增人数、D1 留存、D7 留存、首付用户、首付率、D7 内净收入、D7 ARPU。
- 如果 D7 未成熟，要标注未成熟，不要把缺失当 0。

SQL 口径：
- cohort 用 `dim_player.install_date`。
- D1/D7 留存用 `fact_sessions.lifecycle_day in (1,7)`。
- 早期收入用 `fact_payments.lifecycle_day between 0 and 7` 且 `payment_status='success' AND net_revenue_usd > 0`。
- 首付用户用 `is_first_pay=true` 或该 cohort 的首次成功支付。

推荐输出：
- `channel`, `campaign`, `new_users`, `d1_retention_pct`, `d7_retention_pct`, `first_payers`, `first_pay_rate_pct`, `d7_revenue`, `d7_arpu`。
- 排序默认先看 `d7_revenue`，但结论必须同时解释留存和付费，不能只按收入判定渠道好坏。

参考 SQL：
```sql
WITH obs AS (
  SELECT max(session_start::date) AS max_date FROM fact_sessions
),
cohort AS (
  SELECT p.player_id, p.channel, p.campaign, p.install_date
  FROM dim_player p CROSS JOIN obs
  WHERE p.install_date BETWEEN obs.max_date - 13 AND obs.max_date - 7
),
ret AS (
  SELECT c.channel,
         c.campaign,
         count(DISTINCT c.player_id) AS new_users,
         count(DISTINCT s.player_id) FILTER (WHERE s.lifecycle_day = 1) AS d1_users,
         count(DISTINCT s.player_id) FILTER (WHERE s.lifecycle_day = 7) AS d7_users
  FROM cohort c
  LEFT JOIN fact_sessions s ON s.player_id = c.player_id AND s.lifecycle_day IN (1, 7)
  GROUP BY c.channel, c.campaign
),
pay AS (
  SELECT c.channel,
         c.campaign,
         count(DISTINCT p.player_id) FILTER (WHERE p.is_first_pay) AS first_payers,
         round(sum(p.net_revenue_usd), 2) AS d7_revenue
  FROM cohort c
  LEFT JOIN fact_payments p
    ON p.player_id = c.player_id
   AND p.lifecycle_day BETWEEN 0 AND 7
   AND p.payment_status = 'success'
   AND p.net_revenue_usd > 0
  GROUP BY c.channel, c.campaign
)
SELECT r.channel,
       r.campaign,
       r.new_users,
       round(r.d1_users::numeric / nullif(r.new_users, 0) * 100, 2) AS d1_retention_pct,
       round(r.d7_users::numeric / nullif(r.new_users, 0) * 100, 2) AS d7_retention_pct,
       coalesce(p.first_payers, 0) AS first_payers,
       round(coalesce(p.first_payers, 0)::numeric / nullif(r.new_users, 0) * 100, 2) AS first_pay_rate_pct,
       coalesce(p.d7_revenue, 0) AS d7_revenue,
       round(coalesce(p.d7_revenue, 0) / nullif(r.new_users, 0), 2) AS d7_arpu
FROM ret r
LEFT JOIN pay p ON p.channel = r.channel AND p.campaign = r.campaign
ORDER BY d7_revenue DESC, d7_retention_pct DESC;
```
""",
    },
    {
        "slug": "xiaonan-whale-payer-followup",
        "visibility_scope": "USER_PRIVATE",
        "owner_account": XIAONAN_ACCOUNT,
        "name": "xiaonan Skill：鲸鱼与中高付费玩家追踪",
        "description": "xiaonan 私人偏好：关注 mid/whale revenue_tier 的付费、活跃、战斗和商品偏好。",
        "prompt": """
<!-- data-skill-source:slg-bi-mock:xiaonan:whale-payer-followup -->
# xiaonan Skill：鲸鱼与中高付费玩家追踪

适用问题：
- “鲸鱼玩家最近买什么”“高付费玩家还活跃吗”“中高付费玩家更偏战争包还是资源/加速包”。

必须使用的明细表：
- 支付用 `fact_payments`，分层可看 `revenue_tier in ('mid','whale')` 或 `dim_player.payer_segment in ('dolphin','whale')`。
- 商品偏好关联 `dim_product`。
- 付费后活跃用 `fact_sessions`，付费后战斗用 `fact_battles`。

SQL 口径：
- 只统计成功净收入订单：`payment_status='success' AND net_revenue_usd > 0`。
- 追踪窗口默认从最近一次成功支付日开始看后续 7 天活跃和战斗；如果用户指定窗口，以用户为准。
- 不要把 `amount_usd` 当收入；退款和失败订单只在用户明确问支付问题时单独分析。

推荐输出：
- 付费表：`revenue_tier`, `product_type`, `orders`, `payers`, `revenue`, `arppu`, `revenue_share_pct`。
- 追踪表：`payer_segment`, `last_pay_date`, `active_users_7d_after_pay`, `battle_users_7d_after_pay`, `revenue_7d`。
- 结论优先指出：高付费贡献来自哪些商品、付费后是否继续活跃、是否参与 PVP/战争玩法。

参考 SQL：
```sql
WITH high_pay AS (
  SELECT p.player_id,
         max(p.event_date) AS last_pay_date,
         sum(p.net_revenue_usd) AS revenue
  FROM fact_payments p
  WHERE p.payment_status = 'success'
    AND p.net_revenue_usd > 0
    AND p.revenue_tier IN ('mid', 'whale')
  GROUP BY p.player_id
),
product_mix AS (
  SELECT fp.revenue_tier,
         dp.product_type,
         count(*) AS orders,
         count(DISTINCT fp.player_id) AS payers,
         round(sum(fp.net_revenue_usd), 2) AS revenue
  FROM fact_payments fp
  JOIN dim_product dp ON dp.product_id = fp.product_id
  JOIN high_pay hp ON hp.player_id = fp.player_id
  WHERE fp.payment_status = 'success'
    AND fp.net_revenue_usd > 0
  GROUP BY fp.revenue_tier, dp.product_type
),
total AS (
  SELECT sum(revenue) AS total_revenue FROM product_mix
)
SELECT pm.revenue_tier,
       pm.product_type,
       pm.orders,
       pm.payers,
       pm.revenue,
       round(pm.revenue / nullif(pm.payers, 0), 2) AS arppu,
       round(pm.revenue / nullif(t.total_revenue, 0) * 100, 2) AS revenue_share_pct
FROM product_mix pm CROSS JOIN total t
ORDER BY pm.revenue DESC;
```
""",
    },
    {
        "slug": "xiaonan-alliance-social-growth",
        "visibility_scope": "USER_PRIVATE",
        "owner_account": XIAONAN_ACCOUNT,
        "name": "xiaonan Skill：联盟社交与活跃成长",
        "description": "xiaonan 私人偏好：把联盟加入、帮助、捐献、集结和聊天放在一起看活跃质量。",
        "prompt": """
<!-- data-skill-source:slg-bi-mock:xiaonan:alliance-social-growth -->
# xiaonan Skill：联盟社交与活跃成长

适用问题：
- “加入联盟的玩家留存是不是更好”“联盟帮助/捐献/集结是否带动活跃”“社交玩家表现如何”。

必须使用的明细表：
- 联盟相关事件用 `fact_events`：`alliance_join`, `alliance_help`, `alliance_donate`, `rally_join`。
- 聊天事件用 `chat_send`。
- 活跃和留存仍用 `fact_sessions`。
- 联盟维表用 `dim_alliance`，事件发生时联盟优先用 `fact_events.alliance_id`。

SQL 口径：
- 先做玩家级社交参与标签，例如是否加入联盟、是否帮助/捐献、是否参加集结、是否聊天。
- 对比社交参与组和未参与组时，cohort 分母要一致，默认用同一 install_date 窗口新增玩家。
- 历史行为分析优先用事件时点的 `alliance_id`；`dim_player.current_alliance_id` 只表示当前归属。

推荐输出：
- `social_segment`, `players`, `d1_retention_pct`, `d7_retention_pct`, `avg_sessions`, `payer_rate_pct`。
- 联盟排行：`alliance_id`, `alliance_tag`, `alliance_name`, `active_members`, `help_events`, `donate_events`, `rally_users`。
- 结论要区分相关性和因果，不要直接说“联盟导致留存提升”，除非 SQL 设计支持因果判断。

参考 SQL：
```sql
WITH obs AS (
  SELECT max(session_start::date) AS max_date FROM fact_sessions
),
cohort AS (
  SELECT p.player_id
  FROM dim_player p CROSS JOIN obs
  WHERE p.install_date BETWEEN obs.max_date - 29 AND obs.max_date - 7
),
social_flags AS (
  SELECT c.player_id,
         bool_or(e.event_name IN ('alliance_join', 'alliance_help', 'alliance_donate', 'rally_join', 'chat_send')) AS did_social
  FROM cohort c
  LEFT JOIN fact_events e
    ON e.player_id = c.player_id
   AND e.lifecycle_day BETWEEN 0 AND 7
  GROUP BY c.player_id
),
sessions AS (
  SELECT c.player_id,
         count(*) AS sessions,
         bool_or(s.lifecycle_day = 1) AS d1_active,
         bool_or(s.lifecycle_day = 7) AS d7_active
  FROM cohort c
  LEFT JOIN fact_sessions s ON s.player_id = c.player_id AND s.lifecycle_day BETWEEN 0 AND 7
  GROUP BY c.player_id
),
payers AS (
  SELECT c.player_id,
         bool_or(p.payment_status = 'success' AND p.net_revenue_usd > 0 AND p.lifecycle_day BETWEEN 0 AND 7) AS did_pay
  FROM cohort c
  LEFT JOIN fact_payments p ON p.player_id = c.player_id
  GROUP BY c.player_id
)
SELECT CASE WHEN coalesce(sf.did_social, false) THEN 'social_participant' ELSE 'non_social' END AS social_segment,
       count(*) AS players,
       round(count(*) FILTER (WHERE s.d1_active)::numeric / nullif(count(*), 0) * 100, 2) AS d1_retention_pct,
       round(count(*) FILTER (WHERE s.d7_active)::numeric / nullif(count(*), 0) * 100, 2) AS d7_retention_pct,
       round(avg(s.sessions), 2) AS avg_sessions,
       round(count(*) FILTER (WHERE p.did_pay)::numeric / nullif(count(*), 0) * 100, 2) AS payer_rate_pct
FROM cohort c
LEFT JOIN social_flags sf ON sf.player_id = c.player_id
LEFT JOIN sessions s ON s.player_id = c.player_id
LEFT JOIN payers p ON p.player_id = c.player_id
GROUP BY social_segment
ORDER BY players DESC;
```
""",
    },
    {
        "slug": "xiaonan-city-speedup-bottleneck",
        "visibility_scope": "USER_PRIVATE",
        "owner_account": XIAONAN_ACCOUNT,
        "name": "xiaonan Skill：主城成长与加速卡点",
        "description": "xiaonan 私人偏好：看主城、科技、练兵在低中等级阶段的耗时、加速和资源卡点。",
        "prompt": """
<!-- data-skill-source:slg-bi-mock:xiaonan:city-speedup-bottleneck -->
# xiaonan Skill：主城成长与加速卡点

适用问题：
- “主城升级卡在哪”“玩家是否大量用加速”“建筑、科技、练兵哪个系统拖慢成长”。

必须使用的明细表：
- 主城和建筑用 `fact_building_upgrades`，其中 `building_type='main_city'` 表示主城。
- 科技用 `fact_research`，练兵用 `fact_army_training`。
- 资源消耗用 `fact_resource_transactions`，原因包括 `building_upgrade`, `research`, `troop_training`。

SQL 口径：
- 成长任务一行是一项完成任务，不能用 `fact_events` 的 start/finish 事件数代替。
- 对比耗时时输出原始耗时和加速秒数：`duration_seconds`, `speedup_seconds`。
- 如果看卡点，按 `to_level`、`task_type`、`resource_type` 分组，结合任务人数、平均耗时、平均加速、资源消耗。
- `finish_reason` 当前数据里主要是 normal，不要基于它发明完成原因。

推荐输出：
- `task_type`, `item_type`, `to_level`, `completed_tasks`, `users`, `avg_duration_hours`, `avg_speedup_hours`, `total_power_gain`。
- 资源卡点：`reason`, `resource_type`, `sink_amount`, `users`, `transactions`。
- 结论优先指出：哪个等级段耗时增长、加速使用是否集中、资源消耗是否和主城/科技/练兵同步增加。

参考 SQL：
```sql
WITH obs AS (
  SELECT max(finish_time::date) AS max_date FROM fact_building_upgrades
),
win AS (
  SELECT max_date - 29 AS start_date, max_date FROM obs
),
main_city AS (
  SELECT bu.to_level,
         count(*) AS completed_tasks,
         count(DISTINCT bu.player_id) AS users,
         round(avg(bu.duration_seconds) / 3600.0, 2) AS avg_duration_hours,
         round(avg(bu.speedup_seconds) / 3600.0, 2) AS avg_speedup_hours,
         sum(bu.power_gain) AS total_power_gain
  FROM fact_building_upgrades bu CROSS JOIN win
  WHERE bu.finish_time::date BETWEEN win.start_date AND win.max_date
    AND bu.building_type = 'main_city'
  GROUP BY bu.to_level
),
resource_sink AS (
  SELECT r.resource_type,
         abs(sum(r.change_amount)) AS sink_amount,
         count(DISTINCT r.player_id) AS users
  FROM fact_resource_transactions r CROSS JOIN win
  WHERE r.event_date BETWEEN win.start_date AND win.max_date
    AND r.reason = 'building_upgrade'
    AND r.change_amount < 0
  GROUP BY r.resource_type
)
SELECT 'main_city' AS task_type,
       to_level::text AS item_type,
       completed_tasks,
       users,
       avg_duration_hours,
       avg_speedup_hours,
       total_power_gain,
       NULL::text AS resource_type,
       NULL::numeric AS sink_amount
FROM main_city
UNION ALL
SELECT 'resource_sink',
       'building_upgrade',
       NULL,
       users,
       NULL,
       NULL,
       NULL,
       resource_type,
       sink_amount
FROM resource_sink
ORDER BY task_type, item_type;
```
""",
    },
]


def _skill_prompt(skill: dict[str, str]) -> str:
    return (skill["prompt"] or "").strip()


def _find_user_id(cur, account: str, tenant_id: int) -> int:
    cur.execute(
        """
        SELECT u.id
        FROM sys_user u
        JOIN sys_tenant_user tu ON tu.user_id = u.id
        WHERE u.account = %s
          AND tu.tenant_id = %s
          AND tu.status = 1
        ORDER BY tu.is_primary DESC, u.id
        LIMIT 1
        """,
        (account, tenant_id),
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"未找到账号 {account!r} 在数据源空间 tenant_id={tenant_id} 下的有效成员关系。")
    return int(row[0])


def _upsert_data_skill(
        cur,
        *,
        now: datetime.datetime,
        tenant_id: int,
        ds_id: int,
        skill: dict[str, str],
        owner_user_id: int | None,
) -> bool:
    prompt = _skill_prompt(skill)
    marker = prompt.splitlines()[0].strip()
    visibility_scope = skill["visibility_scope"]
    create_by = owner_user_id if visibility_scope == "USER_PRIVATE" else None
    cur.execute(
        """
        SELECT id FROM custom_prompt
        WHERE type = 'DATA_SKILL'
          AND position(%s in COALESCE(prompt, '')) > 0
        ORDER BY id
        LIMIT 1
        """,
        (marker,),
    )
    existing = cur.fetchone()
    if existing:
        cur.execute(
            """
            UPDATE custom_prompt
            SET tenant_id = %s,
                name = %s,
                description = %s,
                target_scope = 'ALL',
                active = TRUE,
                ai_model_id = NULL,
                create_by = %s,
                visibility_scope = %s,
                prompt = %s,
                specific_ds = TRUE,
                datasource_ids = %s
            WHERE id = %s
            """,
            (
                tenant_id,
                skill["name"][:255],
                skill["description"],
                create_by,
                visibility_scope,
                prompt,
                Jsonb([ds_id]),
                existing[0],
            ),
        )
        return False

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
            ai_model_id,
            create_by,
            visibility_scope,
            prompt,
            specific_ds,
            datasource_ids
        )
        VALUES (%s, 'DATA_SKILL', %s, %s, %s, 'ALL', TRUE, NULL, %s, %s, %s, TRUE, %s)
        """,
        (
            tenant_id,
            now,
            skill["name"][:255],
            skill["description"],
            create_by,
            visibility_scope,
            prompt,
            Jsonb([ds_id]),
        ),
    )
    return True


def main() -> None:
    now = datetime.datetime.now()
    with psycopg.connect(**DB) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, tenant_id FROM core_datasource WHERE name = %s ORDER BY id LIMIT 1",
            (DATASOURCE_NAME,),
        )
        row = cur.fetchone()
        if not row:
            raise SystemExit(f"未找到数据源 {DATASOURCE_NAME!r}，请确认 core_datasource 已存在该记录。")
        ds_id = row[0]
        tenant_id = row[1]
        print(f"目标数据源: id={ds_id} tenant_id={tenant_id} name={DATASOURCE_NAME!r}")

        xiaonan_user_id = _find_user_id(cur, XIAONAN_ACCOUNT, tenant_id)
        skill_added = skill_updated = 0
        for skill in DATA_SKILLS:
            owner_user_id = None
            if skill["visibility_scope"] == "USER_PRIVATE":
                owner_user_id = xiaonan_user_id
            created = _upsert_data_skill(
                cur,
                now=now,
                tenant_id=tenant_id,
                ds_id=ds_id,
                skill=skill,
                owner_user_id=owner_user_id,
            )
            if created:
                skill_added += 1
            else:
                skill_updated += 1

        conn.commit()
        print(f"数据 Skills: 新增 {skill_added} 条，更新 {skill_updated} 条")
        print(f"xiaonan 用户: id={xiaonan_user_id}")
        cur.execute(
            """
            SELECT visibility_scope, create_by, count(*)
            FROM custom_prompt
            WHERE type = 'DATA_SKILL'
              AND tenant_id = %s
              AND specific_ds = TRUE
              AND datasource_ids @> jsonb_build_array(%s)
              AND position('<!-- data-skill-source:slg-bi-mock:' in COALESCE(prompt, '')) > 0
            GROUP BY visibility_scope, create_by
            ORDER BY visibility_scope, create_by
            """,
            (tenant_id, ds_id),
        )
        print("SLG BI Mock 专属 Skills:", cur.fetchall())


if __name__ == "__main__":
    main()
