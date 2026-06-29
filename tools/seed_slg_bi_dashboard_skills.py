"""Seed dashboard-aligned SLG BI Mock workspace Data Skills.

This script keeps each dashboard/business topic as an independent DATA_SKILL so
semantic retrieval can match a focused skill instead of a mixed dashboard brief.
It is idempotent: rerunning updates rows identified by their source marker.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from core_system_db import core_system_db_config, export_postgres_compat_env


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"

DB = core_system_db_config()
DATASOURCE_NAME = "SLG BI Mock"


def _workspace_guard(title: str) -> str:
    return f"""# {title}

本 Skill 只适用于 SLG BI Mock 工作空间绑定的数据源（core_datasource.id=1，tenant_id=7473600346187632640）。如果当前会话不是这个工作空间/数据源，不得套用这里的表名、字段名、事件名、指标口径或业务枚举。

业务库按只读处理；本 Skill 是工作空间级数据字典/口径配置，不要求写回业务库。
"""


DASHBOARD_SKILLS: list[dict[str, str]] = [
    {
        "slug": "realtime-operations",
        "name": "SLG BI Mock 看板 Skill：实时经营监控",
        "description": "实时看板独立业务 Skill；用于实时在线人数、实时付费金额、累计付费金额、分钟/小时趋势、fact_sessions、fact_payments、实时折线图。",
        "prompt": f"""<!-- data-skill-source:slg-bi-mock:dashboard:realtime-operations -->
{_workspace_guard("实时经营监控")}

## 适用问题
- “实时在线人数”“实时付费金额”“累计付费金额”“今天截至当前的收入/在线趋势”。
- 推荐看板来源：实时看板。

## 表与口径
- 实时在线/会话趋势使用 `fact_sessions.session_start/session_end`，按分钟或小时桶聚合。
- 实时付费使用 `fact_payments.event_time/event_date`，默认过滤 `payment_status='success' AND net_revenue_usd > 0`。
- “累计付费金额”是在选定日期内按时间排序累计 `net_revenue_usd`，不要把历史全量收入混入当天累计。
- 观察日期优先取数据中的最大业务日期，例如 `max(session_start::date)` 或 `max(event_date)`，不要直接用系统当前日期。

## 推荐输出
- 在线趋势：`time_bucket`, `online_users`，图表用折线图。
- 实时收入：`time_bucket`, `revenue_usd`，图表用折线图。
- 累计收入：`time_bucket`, `cumulative_revenue_usd`，图表用折线图。
""",
    },
    {
        "slug": "acquisition-roi",
        "name": "SLG BI Mock 看板 Skill：投放买量与 ROI",
        "description": "投放看板独立业务 Skill；用于每日买量成本、单用户买量成本、渠道 ROI、投放回收、acquisition_cost_usd/cny、channel、campaign、fact_payments。",
        "prompt": f"""<!-- data-skill-source:slg-bi-mock:dashboard:acquisition-roi -->
{_workspace_guard("投放买量与 ROI")}

## 适用问题
- “每日买量成本”“单用户买量成本”“各渠道 ROI”“渠道回收”“买量效果”。
- 推荐看板来源：投放看板、渠道分析、核心看板的渠道收入排行。

## 表与口径
- 新增 cohort 与投放成本来自 `dim_player.install_date`、`channel`、`campaign`、`bi_channel_name`、`bi_channel_group`、`acquisition_network`、`acquisition_cost_usd`、`acquisition_cost_cny`。
- 收入回收来自 `fact_payments`，默认过滤 `payment_status='success' AND net_revenue_usd > 0`。
- ROI = 指定窗口内净收入 / 同 cohort 买量成本；必须说明币种，默认用 USD：`net_revenue_usd / acquisition_cost_usd`。
- 单用户买量成本 = `sum(acquisition_cost_usd) / count(distinct player_id)`；不要用活跃人数当新增买量分母。
- 若用户问 D7/D30 ROI，必须用生命周期窗口 `fact_payments.lifecycle_day <= 7/30`，且只统计已成熟 cohort。

## 推荐输出
- `install_date`, `channel`, `campaign`, `new_users`, `cost_usd`, `cost_per_new_user_usd`, `revenue_usd`, `roi_pct`。
- 成本/新增趋势用柱状或折线；渠道 ROI 用柱状或表格，不建议用饼图。
""",
    },
    {
        "slug": "new-user-quality",
        "name": "SLG BI Mock 看板 Skill：新增用户与早期质量",
        "description": "新增看板独立业务 Skill；用于新增用户数、按渠道/系统新增、D1 留存、新增首日付费、install_date cohort、fact_sessions、fact_payments。",
        "prompt": f"""<!-- data-skill-source:slg-bi-mock:dashboard:new-user-quality -->
{_workspace_guard("新增用户与早期质量")}

## 适用问题
- “新增用户数”“按渠道新增”“按系统新增”“新增用户次日留存”“新增首日付费金额”“某天新增用户后续表现”。
- 推荐看板来源：新增看板。

## 表与口径
- 新增用户固定使用 `dim_player.install_date`，分母为 `count(distinct player_id)`。
- 渠道维度优先用 `dim_player.channel/campaign/bi_channel_name/bi_channel_group`；系统维度用 `platform`。
- 新增 D1 留存使用 `fact_sessions.lifecycle_day = 1`，按 `player_id` 去重。
- 新增首日付费使用 `fact_payments.lifecycle_day = 0` 且 `payment_status='success' AND net_revenue_usd > 0`。
- “后续付费情况”应输出生命周期日曲线，不要只给一个总指标。

## 推荐输出
- `install_date`, `new_users`, `d1_retained_users`, `d1_retention_pct`, `day0_payers`, `day0_revenue_usd`。
- 按渠道/系统拆解时增加 `channel` 或 `platform`；趋势图用折线，拆解对比用柱状图。
""",
    },
    {
        "slug": "tutorial-funnel",
        "name": "SLG BI Mock 看板 Skill：新手引导与任务通过率",
        "description": "新手引导漏斗独立业务 Skill；用于新手任务通过率、新手教程通过率、新手引导漏斗、tutorial_step、attributes step、完成教程后付费。",
        "prompt": f"""<!-- data-skill-source:slg-bi-mock:dashboard:tutorial-funnel -->
{_workspace_guard("新手引导与任务通过率")}

## 适用问题
- “新手任务通过率”“新手引导通过率”“新手教程通过率”“新手引导漏斗转化”“教程步骤掉点”“完成教程后付费转化”。
- 推荐看板来源：核心看板的新手引导漏斗转化。

## 表与口径
- 新手教程步骤只使用 `fact_events` 中 `event_name='tutorial_step'` 的记录，步骤号取 `(attributes->>'step')::int`。
- 不要使用 `activity_type`、`activity_stage` 分析新手任务通过率；它们属于活动分析，不是教程步骤。
- 默认 cohort 使用 `dim_player.install_date` 的新增玩家；未指定窗口时优先使用数据最大日期向前 30 天的新增玩家。
- 为了对齐核心看板“新手引导漏斗转化”，未指定筛选时第 1 步是最近 30 天账号注册/新增用户数，后续步骤是这些新增用户在同窗口内完成的 `tutorial_step`。
- 用户说“从登录到新手引导每一步/首次付费”但没有明确要求真实登录事件时，默认仍采用看板的账号注册/新增 cohort 起点；若明确要求真实登录，用 `event_name='login'` 或 `fact_sessions` 去重登录玩家并说明与看板起点不同。
- 教程漏斗需要玩家级去重：先构造一行一个 `player_id` 的完成标记，再按步骤顺序汇总。
- 后序步骤必须带前序完成条件，避免后序人数大于前序人数。
- “完成教程后付费”先取完成最终教程步骤的首次时间，再统计该时间之后成功净收入付费：`payment_status='success' AND net_revenue_usd > 0 AND payment.event_time >= tutorial_complete_time`。

## 推荐输出
- 漏斗主字段：`step_order`, `step_name`, `users`，图表用漏斗图；如用户要求也允许切柱状图。
- 辅助字段：`conversion_from_start_pct`, `conversion_from_prev_pct`, `drop_off_users`, `drop_off_from_prev_pct`。
- 维度拆解时一次只拆一个维度，例如 `channel`、`campaign`、`platform`、`device_tier`。
""",
    },
    {
        "slug": "active-session-lifecycle",
        "name": "SLG BI Mock 看板 Skill：活跃、会话与生命周期构成",
        "description": "活跃看板独立业务 Skill；用于 DAU、WAU、MAU、活跃生命周期构成、按渠道/系统活跃、周登录天数分布、fact_sessions。",
        "prompt": f"""<!-- data-skill-source:slg-bi-mock:dashboard:active-session-lifecycle -->
{_workspace_guard("活跃、会话与生命周期构成")}

## 适用问题
- “DAU/WAU/MAU”“活跃用户生命周期构成”“活跃用户数按渠道/系统”“周登录天数分布”。
- 推荐看板来源：活跃看板、核心看板 DAU 趋势。

## 表与口径
- 活跃用户、会话次数、在线时长统一使用 `fact_sessions`，不要用 `fact_events` 事件人数替代 DAU。
- DAU = 按 `session_start::date` 的 `count(distinct player_id)`。
- WAU/MAU = 按自然周/月窗口内去重活跃玩家；不要把每日 DAU 简单相加当 WAU/MAU。
- 活跃生命周期构成优先使用 `fact_sessions.active_lifecycle_segment`；渠道/系统可用 `channel`、`bi_channel_name`、`platform`。
- 周登录天数分布需要先做玩家级 `count(distinct session_start::date)`，再按登录天数分桶。

## 推荐输出
- 趋势：`stat_date`, `active_users`, `sessions`, `avg_duration_seconds`，图表用折线。
- 构成：`active_lifecycle_segment`, `active_users`, `share_pct`，分类少时可用饼图，分类多时用柱状/表格。
- 周登录：`login_days`, `players`，图表用柱状图。
""",
    },
    {
        "slug": "retention-dashboard",
        "name": "SLG BI Mock 看板 Skill：留存分析",
        "description": "留存分析看板独立业务 Skill；用于 D1/D3/D7/D14 留存、各渠道新增留存、生命周期留存热力、install_date cohort、fact_sessions.lifecycle_day。",
        "prompt": f"""<!-- data-skill-source:slg-bi-mock:dashboard:retention-dashboard -->
{_workspace_guard("留存分析")}

## 适用问题
- “D1/D7 留存”“各渠道新增留存”“新增 cohort 留存曲线”“留存热力图”。
- 推荐看板来源：留存分析、核心看板各渠道新增留存、渠道分析各渠道新增留存。

## 表与口径
- cohort 分母固定使用 `dim_player.install_date` 的新增玩家。
- 留存分子使用 `fact_sessions.lifecycle_day = n` 当天有会话的去重玩家。
- Dn 留存默认是精确日留存，不是 0 到 n 日滚动留存；如果用户要滚动留存需明确写 `lifecycle_day BETWEEN 0 AND n`。
- 未成熟 cohort 必须排除、标注未成熟或返回 NULL，不能把尚未观察到的留存当 0。
- 渠道留存拆解使用 `dim_player.channel/campaign/bi_channel_name/bi_channel_group`。

## 推荐输出
- `cohort_date`, `lifecycle_day`, `cohort_users`, `retained_users`, `retention_pct`, `matured_flag`。
- 多生命周期日可用折线或热力图；渠道对比可用柱状或表格。
""",
    },
    {
        "slug": "payment-overview-ltv",
        "name": "SLG BI Mock 看板 Skill：付费概览与 LTV",
        "description": "付费概览看板独立业务 Skill；用于付费情况、近7日累充排名、日充值次数/人数、7日 LTV、首购、等级 ARPPU、fact_payments。",
        "prompt": f"""<!-- data-skill-source:slg-bi-mock:dashboard:payment-overview-ltv -->
<!-- data-skill-validation:{{
  "match":["后续付费","生命周期","ltv","LTV","7 日 LTV","累计收入"],
  "day_field":["lifecycle_day","生命周期日"],
  "require_continuous_sequence":true,
  "continuous_sequence_message":"生命周期趋势结果缺少连续日期 {{missing_days}}。请使用 generate_series 或日期序列表补齐观察窗口，让无付费日期返回 0，并保持累计字段不下降。",
  "required_fields":["ltv_usd"],
  "required_field_message":"LTV 趋势分析缺少 {{field}} 字段。请按本 Skill 输出 cohort_users、lifecycle_day、cumulative_revenue_usd 和 ltv_usd。",
  "required_field_keywords":[["cumulative_revenue","累计收入","累计净收入"]],
  "required_field_keywords_message":"LTV 趋势分析缺少累计收入字段。请先按生命周期日补齐每日收入，再输出累计收入与 LTV。",
  "non_decreasing_field_keywords":[["cumulative_revenue","累计收入","累计净收入"],["ltv"]],
  "non_decreasing_message":"LTV 累计字段 {{field}} 在 {{previous_sequence}}={{previous_value}} 到 {{sequence}}={{value}} 出现下降；请检查是否混用了不同 cohort、分母或累计口径。"
}} -->
{_workspace_guard("付费概览与 LTV")}

## 适用问题
- “付费情况”“日充值总次数”“日充值用户数”“近 7 日累充排名”“7 日 LTV”“首次购买情况”“各等级段人均付费金额”。
- 推荐看板来源：付费概览、核心看板 ARPU/ARPPU/日付费率/收入趋势。

## 表与口径
- 支付事实使用 `fact_payments`，默认过滤 `payment_status='success' AND net_revenue_usd > 0`。
- 收入使用 `net_revenue_usd`，不要把 `amount_usd` 当正式收入。
- 充值次数用 `count(distinct order_id)`，充值用户数用 `count(distinct player_id)`。
- 近 7 日累充排名按玩家聚合 `sum(net_revenue_usd)` 后排序。
- 7 日 LTV 使用 `dim_player.install_date` 建 cohort，并统计 `fact_payments.lifecycle_day BETWEEN 0 AND 7` 的净收入 / cohort 用户数；只统计已成熟 cohort。
- 首次购买优先用 `is_first_pay = true` 或 `pay_sequence = 1`。

## 推荐输出
- 日趋势：`stat_date`, `orders`, `pay_users`, `net_revenue_usd`, `pay_rate_pct`, `arpu`, `arppu`。
- 累充排名：`rank_no`, `player_id`, `total_revenue_usd`, `orders`，图表用表格。
- LTV：`cohort_date`, `cohort_users`, `lifecycle_day`, `cumulative_revenue_usd`, `ltv_usd`，图表用折线。
""",
    },
    {
        "slug": "gift-package-product",
        "name": "SLG BI Mock 看板 Skill：礼包、商品与复购留存",
        "description": "礼包付费看板独立业务 Skill；用于新手礼包复购率、月卡30日留存、礼包类型/分组/购买阶段、gift_package_type、dim_product、fact_payments。",
        "prompt": f"""<!-- data-skill-source:slg-bi-mock:dashboard:gift-package-product -->
{_workspace_guard("礼包、商品与复购留存")}

## 适用问题
- “购买新手礼包用户复购率”“购买月卡用户 30 日留存”“礼包付费概览”“商品/礼包购买结构”。
- 推荐看板来源：礼包付费概览、核心看板礼包购买情况。

## 表与口径
- 礼包购买使用 `fact_payments`，默认过滤 `payment_status='success' AND net_revenue_usd > 0`。
- 礼包字段优先用 `gift_package_type`、`gift_package_group`、`gift_purchase_stage`；商品详情可关联 `dim_product.product_id`。
- 新手礼包复购率：先定位购买新手礼包的玩家，再看指定窗口内是否再次成功净收入支付；分母是购买新手礼包玩家数。
- 月卡 30 日留存：先定位购买月卡的玩家，再用购买后第 30 天或窗口内 `fact_sessions` 活跃判断留存；需要说明精确日或滚动窗口。
- 商品/礼包结构只展示成功净收入订单，失败和退款单独分析。

## 推荐输出
- `gift_package_type`, `orders`, `payers`, `revenue_usd`, `repeat_payers`, `repeat_rate_pct`。
- 月卡留存：`cohort_date`, `card_buyers`, `retained_users_30d`, `retention_30d_pct`。
- 复购/留存用折线或表格；商品排行用柱状或表格。
""",
    },
    {
        "slug": "activity-participation-quality",
        "name": "SLG BI Mock 看板 Skill：活动参与与后续质量",
        "description": "活动分析看板独立业务 Skill；用于活动参与率、人均参与次数、等级段活动人数、新手活动7日留存、节日活动7日付费留存、activity_type/stage。",
        "prompt": f"""<!-- data-skill-source:slg-bi-mock:dashboard:activity-participation-quality -->
{_workspace_guard("活动参与与后续质量")}

## 适用问题
- “各类活动参与率”“各类活动人均参与次数”“各等级段参与活动人数”“参与新手活动后的 7 日留存”“参与节日活动后的 7 日付费留存”。
- 推荐看板来源：活动分析。

## 表与口径
- 活动参与使用 `fact_events` 的 `activity_id`、`activity_type`、`activity_stage`、`activity_participation_count`。
- 参与人数 = `count(distinct player_id)`；参与次数 = `count(*)` 或 `sum(activity_participation_count)`，需按字段含义明确。
- 活动参与率分母应是同窗口活跃用户，来自 `fact_sessions`；不要用全量注册玩家当默认分母。
- 活动后 7 日留存：先定位参与活动的玩家和参与日期，再用后续 `fact_sessions` 判断活跃。
- 活动后 7 日付费留存：先定位参与活动的玩家，再用后续 7 天成功净收入支付 `fact_payments` 判断。
- 这套规则只用于活动分析；不要用 `activity_type/activity_stage` 分析新手教程通过率。

## 推荐输出
- 活动参与：`activity_type`, `active_users`, `participants`, `participation_rate_pct`, `participation_events`, `avg_participations_per_user`。
- 后续质量：`activity_type`, `participants`, `retained_users_7d`, `retention_7d_pct`, `paid_users_7d`, `paid_retention_7d_pct`。
- 参与率和人均次数可用柱状图；后续留存/付费留存可用表格或柱状图。
""",
    },
    {
        "slug": "city-growth-construction",
        "name": "SLG BI Mock 看板 Skill：主城建设与成长任务",
        "description": "主城建设看板独立业务 Skill；用于主城平均等级、建筑/科技升级、兵种招募、加速、主城升级漏斗、fact_building_upgrades、fact_research、fact_army_training。",
        "prompt": f"""<!-- data-skill-source:slg-bi-mock:dashboard:city-growth-construction -->
{_workspace_guard("主城建设与成长任务")}

## 适用问题
- “主城平均等级”“当日主城/建筑/科技升级次数”“各主城等级玩家数”“各建筑/科技升级次数”“各兵种招募情况”“各类型加速情况”“主城升级漏斗”。
- 推荐看板来源：主城建设。

## 表与口径
- 建筑升级使用 `fact_building_upgrades`，主城为 `building_type='main_city'`。
- 科技升级/研究使用 `fact_research`；练兵/招募使用 `fact_army_training`。
- 升级次数默认按任务明细行或 `count(distinct task_id)`；升级用户数为 `count(distinct player_id)`。
- 耗时和加速使用 `duration_seconds`、`speedup_seconds`，换算小时展示。
- 当前主城等级分布可用 `dim_player.current_city_level`；历史升级分析使用事实表 `from_level/to_level`。
- 主城升级漏斗按 `to_level` 逐级累计玩家，并保证高等级人数不能超过低等级前序人数。

## 推荐输出
- 成长任务：`task_type`, `item_type`, `to_level`, `completed_tasks`, `users`, `avg_duration_hours`, `avg_speedup_hours`, `total_power_gain`。
- 主城漏斗：`step_order`, `city_level`, `users`, `conversion_from_start_pct`, `conversion_from_prev_pct`，图表用漏斗图。
""",
    },
    {
        "slug": "economy-resource-path",
        "name": "SLG BI Mock 看板 Skill：经济系统与资源路径",
        "description": "经济系统看板独立业务 Skill；用于钻石消耗获取、资源获取途径、资源消耗途径、resource_path_type/name、source_sink、fact_resource_transactions。",
        "prompt": f"""<!-- data-skill-source:slg-bi-mock:dashboard:economy-resource-path -->
{_workspace_guard("经济系统与资源路径")}

## 适用问题
- “钻石消耗获取情况”“钻石获取途径分布”“钻石消耗途径分布”“资源经济系统”。
- 推荐看板来源：经济系统。

## 表与口径
- 资源流水使用 `fact_resource_transactions`，一行一次资源变化。
- 获得/消耗必须分开看：`source_sink='gain'` 或 `change_amount > 0` 为获得；`source_sink='sink'` 或 `change_amount < 0` 为消耗。
- 消耗金额建议输出绝对值 `abs(sum(change_amount))`，净变化才使用 `sum(change_amount)`。
- 路径维度优先使用 `resource_path_type`、`resource_path_name`、`economy_action`、`reason`。
- 付费相关资源只用 `is_paid_related=true` 识别，不等同于收入；收入仍来自 `fact_payments.net_revenue_usd`。
- 余额使用 `balance_after`，不能把余额简单累加当库存。

## 推荐输出
- `resource_type`, `resource_path_type`, `resource_path_name`, `gain_amount`, `sink_amount`, `net_change_amount`, `transactions`, `users`。
- 获取/消耗路径分布用柱状或表格；同时展示获得和消耗时用分组柱。
""",
    },
    {
        "slug": "expedition-march",
        "name": "SLG BI Mock 看板 Skill：出征、演习与行军表现",
        "description": "出征数据看板独立业务 Skill；用于出征总量、出征士兵总量、平均战斗力、出征耗时、兵种/将领/等级胜率、演习次数、fact_expeditions。",
        "prompt": f"""<!-- data-skill-source:slg-bi-mock:dashboard:expedition-march -->
{_workspace_guard("出征、演习与行军表现")}

## 适用问题
- “出征总量”“出征士兵总量”“出征平均战斗力”“出征总耗时”“出征明细”“各兵种出征”“各将领出征量/胜率”“各等级出征胜率”“各主城等级参与演习次数”。
- 推荐看板来源：出征数据。

## 表与口径
- 问“出征/演习/行军表现”优先使用 `fact_expeditions`，不要默认改用 `fact_battles`。
- `fact_expeditions` 一行是一次出征/演习/行军记录，核心字段：`expedition_type`, `drill_type`, `target_type`, `result`, `troop_type`, `troop_tier`, `troops_sent`, `troops_lost`, `troops_remaining`, `team_power`, `duration_seconds`, `hero_id`, `hero_name`, `hero_level`, `city_level`, `stamina_spent`, `resource_looted`。
- 出征总量 = `count(*)`；出征人数 = `count(distinct player_id)`；士兵总量 = `sum(troops_sent)`。
- 胜率 = `result='win'` 的记录数 / 总记录数；按将领、兵种、主城等级拆解时必须保留分母。
- 平均战斗力用 `avg(team_power)`；出征总耗时用 `sum(duration_seconds)`，展示时可换算小时。

## 推荐输出
- 总览指标：`expeditions`, `expedition_users`, `troops_sent`, `avg_team_power`, `duration_hours`。
- 拆解表：`troop_type`, `hero_name`, `city_level`, `expeditions`, `win_rate_pct`, `avg_team_power`, `avg_troops_lost`。
- 趋势用折线，兵种/将领排行用柱状或表格。
""",
    },
    {
        "slug": "hero-growth",
        "name": "SLG BI Mock 看板 Skill：英雄养成",
        "description": "养成看板独立业务 Skill；用于英雄养成情况、SSR 英雄等级分布、hero_action、hero_level/star、dim_hero、fact_events 英雄字段。",
        "prompt": f"""<!-- data-skill-source:slg-bi-mock:dashboard:hero-growth -->
{_workspace_guard("英雄养成")}

## 适用问题
- “英雄养成情况”“SSR 英雄等级分布”“英雄升级/升星行为”“不同品质英雄养成分布”。
- 推荐看板来源：养成看板。

## 表与口径
- 英雄维表使用 `dim_hero`，字段包括 `hero_id`, `hero_name`, `hero_quality`, `hero_type`, `release_date`, `default_star`。
- 英雄养成事件使用 `fact_events` 的 `hero_id`, `hero_name`, `hero_quality`, `hero_type`, `hero_action`, `hero_level_before/after`, `hero_star_before/after`。
- SSR 英雄筛选使用 `hero_quality='SSR'`。
- 英雄等级分布按玩家-英雄最新养成状态统计时，需要先按 `player_id, hero_id` 取最新 `event_time` 的 `hero_level_after`，不要直接按事件次数当拥有人数。
- 如果用户只问养成行为次数，可按 `hero_action`、`hero_quality` 聚合事件数和玩家数。

## 推荐输出
- 行为概览：`hero_quality`, `hero_action`, `events`, `users`, `heroes`。
- 等级分布：`hero_name`, `hero_quality`, `hero_level_after`, `players`，图表用柱状或表格。
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
          AND position(%s in COALESCE(prompt, '')) > 0
        ORDER BY id
        LIMIT 1
        """,
        (marker,),
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
    with psycopg.connect(**DB) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, tenant_id FROM core_datasource WHERE name = %s ORDER BY id LIMIT 1",
                (DATASOURCE_NAME,),
            )
            row = cur.fetchone()
            if not row:
                raise SystemExit(f"Cannot find datasource {DATASOURCE_NAME!r}")
            datasource_id = int(row[0])
            tenant_id = int(row[1])

            ids: list[int] = []
            for skill in DASHBOARD_SKILLS:
                ids.append(_upsert_skill(cur, tenant_id=tenant_id, datasource_id=datasource_id, skill=skill, now=now))
        conn.commit()

    saved = _save_embeddings(ids, tenant_id)
    print(f"Upserted dashboard skills: {len(ids)}")
    print(f"Embedding refreshed: {saved}")
    print("Skill ids:", ids)


if __name__ == "__main__":
    main()
