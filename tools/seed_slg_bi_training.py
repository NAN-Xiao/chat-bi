"""Seed 统一业务口径（术语 + 数据训练 SQL 示例 + Data Skills）into the 星通智数系统库。

- 不修改任何应用代码，只向系统库 terminology / data_training 表插入配置数据。
- 幂等：重复运行不会产生重复记录，已存在记录会更新到最新口径。
- 目标数据源固定为 core_datasource 中的 'SLG BI Mock'（按名称自动定位 id）。
- 所有 SQL 示例均为只读 SELECT，指标在查询时从明细表计算，符合仓库 AGENTS.md 约束。
- Data Skills 写入 custom_prompt：6 个工作空间公开 Skill，4 个 xiaonan 私人 Skill。

运行：
    backend/.venv/Scripts/python.exe tools/seed_slg_bi_training.py
运行后即可在「设置 - 术语 / 数据训练 / 数据 Skills」中看到这些记录，新问答会读取最新配置。
"""
from __future__ import annotations

import datetime

import psycopg
from psycopg.types.json import Jsonb

DB = dict(host="127.0.0.1", port=15432, user="root", password="Password123@pg", dbname="zhishu_bi")
DATASOURCE_NAME = "SLG BI Mock"
XIAONAN_ACCOUNT = "xiaonan"


# ---------------------------------------------------------------------------
# 术语口径：word 主词 / synonyms 同义词（用户问题里可能出现）/ description 统一口径定义
# ---------------------------------------------------------------------------
TERMS: list[tuple[str, list[str], str]] = [
    # 数据集边界与通用 SQL 规则
    (
        "SLG BI Mock数据集",
        ["mock数据", "mock表", "SLG明细数据", "SLG BI Mock", "当前mock"],
        "SLG BI Mock 是明细层演示数据源，不包含预聚合 KPI 表。"
        "维表包括 dim_player、dim_server、dim_alliance、dim_product、dim_event_name；"
        "事实表包括 fact_sessions、fact_events、fact_payments、fact_battles、"
        "fact_resource_transactions、fact_building_upgrades、fact_research、fact_army_training。"
        "所有 DAU、留存、收入、付费率、漏斗、战斗、资源和成长指标都应在查询时从这些明细表计算，"
        "不要假设存在 agg_*、daily_kpis、snapshot 或其他汇总表。",
    ),
    (
        "观察基准日",
        ["数据最大日期", "统计截止日", "观测日期", "观察窗口", "最近N天"],
        "涉及“最近 N 天”“近一个月”“截至目前”的问题，观察基准日必须从当前分析所用事实表取最大业务日期，"
        "不要使用系统当前日期。活跃/会话用 fact_sessions.session_start::date，"
        "统一事件、支付、战斗、资源用各表 event_date，建筑/科技/练兵可用 start_time::date 或 finish_time::date，"
        "新增用户用 dim_player.install_date。最近 N 天通常是闭区间 [max_date - N + 1, max_date]。",
    ),
    (
        "明细表粒度",
        ["表粒度", "事实表粒度", "去重粒度", "join粒度"],
        "fact_sessions 一行是一段登录到登出会话；fact_events 一行是一次客户端/服务端/SDK 埋点事件；"
        "fact_payments 一行是一个订单的最终生命周期状态；fact_battles 一行是一场战斗结算；"
        "fact_resource_transactions 一行是一笔资源增减流水；"
        "fact_building_upgrades、fact_research、fact_army_training 一行分别是一项建筑、科技、练兵任务完成明细。"
        "做人数指标时优先 count(DISTINCT player_id)，做次数/订单/任务数时才 count(*)；"
        "跨事实表关联前必须先按 player_id、日期或任务粒度预聚合，避免多对多 join 放大指标。",
    ),
    (
        "百分比指标",
        ["比例指标", "比率指标", "转化率指标", "率指标", "percent metric", "rate metric"],
        "百分比/比率类指标包括留存率、转化率、付费率、流失率、胜率、占比等。"
        "用于图表 y 轴时应返回数值型百分比（0~100，例如 37.52），不要拼接 '%' 成文本；"
        "只有用户明确要求表格文本展示时，才额外提供带 '%' 的展示列。"
        "这类指标不可直接累加，也不适合饼图表达，按时间看趋势用折线，按维度对比用柱状/条形。",
    ),
    (
        "混合指标图表",
        ["双轴图", "组合图", "混合图", "多指标图", "combo chart"],
        "混合指标图表口径：不要把总量、均值、百分比三个量级差异很大的指标全部塞进同一个同轴图。"
        "推荐主图只混合一个总量指标和一个比率指标，例如活跃人数用左轴柱、留存率用右轴折线，"
        "或总收入用左轴柱、付费率用右轴折线。"
        "ARPU、ARPPU、平均时长、LTV 等均值/人均指标应放入表格、摘要，或单独生成第二张趋势图。"
        "如果必须在同一结果中返回这些字段，图表配置的 y 轴不要把均值类字段加入 multi-quota。",
    ),

    # 用户、维度、活跃与留存
    (
        "玩家维表",
        ["用户画像", "玩家画像", "用户属性", "玩家属性", "dim_player"],
        "dim_player 是玩家维表，包含注册安装、归因、设备、国家语言、注册区服、当前等级/战力/VIP/城堡等级、"
        "当前联盟、首付时间、累计付费和最近活跃日期等当前状态字段。"
        "install_date/register_time 用于新增 cohort；channel/campaign/platform/country/device_tier 用于归因和画像拆分；"
        "current_* 字段是当前状态，不代表历史某一天的状态。做历史时点分析应优先使用事实表中的 event_time、player_level、vip_level、power 等事件时点字段。",
    ),
    (
        "新增用户",
        ["新增", "新注册用户", "新增玩家", "新增注册", "拉新", "new users"],
        "新增用户口径：按 dim_player.install_date 统计当日首次安装/注册的去重玩家数。"
        "“最近 N 天新增”指 install_date 落在 [最大 install_date - N + 1, 最大 install_date] 区间的玩家 cohort，"
        "是已经发生的历史新增，不是未来新增；不要和“新增用户的日活”混淆。",
    ),
    (
        "归因和设备维度",
        ["渠道", "广告渠道", "campaign", "国家", "平台", "设备档位", "设备分层"],
        "归因和设备拆分优先使用 dim_player 的 channel、campaign、platform、country、language、device_tier、device_model、os_version。"
        "会话、事件、支付等事实表也冗余了 channel/campaign/platform/country/device_tier，适合按事件发生时的记录拆分；"
        "如果问题是“这批新增用户来自哪里”，用 dim_player；如果问题是“某段时间事件/收入按渠道表现”，可用事实表当时字段或关联 dim_player，但要保持同一口径。",
    ),
    (
        "区服和联盟维度",
        ["区服", "服务器", "王国", "server", "联盟", "alliance"],
        "区服信息来自 dim_server，玩家注册区服是 dim_player.register_server_id，事件/会话/支付/战斗等事实发生区服是各 fact 表的 server_id。"
        "联盟信息来自 dim_alliance，玩家当前联盟是 dim_player.current_alliance_id，事件时点联盟可看 fact_events.alliance_id。"
        "分析历史行为时不要把当前联盟或当前区服误当作历史时点状态，除非问题明确只看当前归属。",
    ),
    (
        "生命周期日",
        ["lifecycle_day", "生命周期天数", "D0", "D1", "D7", "第N天"],
        "lifecycle_day 表示玩家从 install_date 起算的生命周期天数，D0 为安装/注册当天。"
        "fact_sessions、fact_events、fact_payments 均有 lifecycle_day 字段，可用于新增 cohort 的留存、付费、事件、行为曲线。"
        "按生命周期日分析时必须固定 cohort 分母，不要让每个 day 的分母随当天有行为的人变化。",
    ),
    (
        "DAU",
        ["日活", "日活跃用户", "日活跃", "活跃用户数", "活跃用户", "WAU", "MAU"],
        "日活跃用户（DAU）口径：某一个自然日内有登录/会话行为的去重玩家数。"
        "标准算法：以 fact_sessions.session_start::date 分组，count(DISTINCT player_id)。"
        "WAU/MAU 同口径，分别按最近 7 天 / 30 天窗口去重活跃玩家。"
        "不要用 fact_events 的事件人数替代 DAU，除非用户明确问某类事件触达人数。",
    ),
    (
        "会话分析",
        ["会话", "登录次数", "启动次数", "在线时长", "游戏时长", "人均时长", "session"],
        "会话分析使用 fact_sessions。session_id/session_uid 表示一次登录到登出；"
        "session_start/session_end 是会话起止时间，duration_seconds 是会话时长。"
        "登录次数可 count(*) 或 count(DISTINCT session_id)，活跃人数 count(DISTINCT player_id)，"
        "人均会话次数 = sessions / active_users，人均在线时长 = sum(duration_seconds) / active_users。"
        "app_start/login/logout 事件在 fact_events 中可用于埋点事件分析，但 DAU 和时长优先用 fact_sessions。",
    ),
    (
        "留存率",
        [
            "留存",
            "留存情况",
            "每日留存",
            "新增用户留存",
            "新增用户留存情况",
            "单日新增留存",
            "当日留存",
            "第N天留存",
            "精确日留存",
            "retention",
            "exact-day retention",
            "N日留存",
            "Dn留存",
            "7日留存",
            "次周留存",
            "月留存",
        ],
        "Dn 留存口径：成熟 cohort。分母 = install_date <= 观察最大日期 - n 的玩家；"
        "分子 = 这些玩家在 lifecycle_day = n 于 fact_sessions 有活跃行为的去重数；"
        "留存率 = 分子 / 分母。D0 可视为 100% 安装基准，D1 及以后必须从 fact_sessions 行为计算，"
        "默认 Dn 留存是精确日/当日留存：只看 lifecycle_day = n 当天是否活跃，不要求 D1 到 Dn 连续活跃；"
        "因此留存率曲线可以上下波动，允许 D6 高于 D5。"
        "这种回升不能直接解释为“回流用户”，除非问题明确要求回流并定义连续沉默/流失阈值；"
        "若用户要求单调下降的剩余用户曲线，应改用连续留存/未流失存量或滚动留存口径，不能沿用精确日 Dn 留存 SQL。"
        "当用户指定某一天新增用户（如 6月1号新增用户）时，分母必须固定为该 install_date cohort 的总新增人数，"
        "不要在按 lifecycle_day 分组后用当天有 session 的玩家数重新计算分母，否则会得到错误的 100% 留存；"
        "留存率字段应返回 0~100 的数值，不要拼接 '%' 成文本；"
        "若同图展示活跃人数和留存率，必须使用左轴人数、右轴百分比的双轴/组合图，不能共用同一个 Y 轴；"
        "样本未成熟时输出“样本未成熟/暂不判断”，不要输出 0% 或全量流失。",
    ),
    (
        "次日留存",
        ["次留", "D1留存", "1日留存", "次日留存率"],
        "次日留存（D1）是 Dn 留存的 n=1 特例。采用成熟 cohort："
        "分母 = install_date <= 观察最大日期 - 1 的玩家；"
        "分子 = 这些玩家在 lifecycle_day = 1 时于 fact_sessions 有会话/登录行为的去重数。"
        "未满 1 天观察窗口的 cohort 不计入，也不能把缺失当作 0% 留存。",
    ),
    (
        "连续留存",
        ["连续留存率", "未流失存量", "剩余用户", "连续活跃留存", "strict retention"],
        "连续留存口径：分母固定为同一 install_date cohort 人数；"
        "分子为从 D1 到 Dn 每一天均在 fact_sessions 有会话/登录活跃的去重玩家。"
        "该指标回答“这批用户是否连续留下来/仍未流失”，随 lifecycle_day 单调不增。"
        "如果用户要求类似单调下降的剩余用户曲线，不要使用默认精确日 Dn 留存 SQL。",
    ),
    (
        "滚动留存",
        ["rolling retention", "第N天后留存", "N日后留存", "后续留存"],
        "滚动留存口径：分母固定为同一 install_date cohort 人数；"
        "分子为 lifecycle_day >= n 的任意一天曾在 fact_sessions 再次活跃的去重玩家。"
        "该指标回答“第 N 天及以后是否回来过”，通常随 n 单调不增；"
        "它不同于只看 lifecycle_day = n 当天活跃的精确日 Dn 留存，也不同于需要连续沉默阈值的回流用户。",
    ),
    (
        "流失用户",
        ["流失", "沉默用户", "不活跃用户", "churn"],
        "流失/沉默用户必须先定义连续不活跃天数 N。"
        "在 SLG BI Mock 中可用 fact_sessions 的相邻活跃日期或 dim_player.last_active_date 与观察基准日比较。"
        "默认不要把某个 lifecycle_day 没有活跃的用户直接称为流失，因为精确日留存允许之后再次活跃。",
    ),
    (
        "回流用户",
        ["回流", "流失回归", "召回用户", "回归玩家"],
        "回流用户口径：曾连续 N 天（通常 7 天）无任何 fact_sessions 活跃、随后又重新登录的玩家。"
        "基于 fact_sessions 相邻活跃日期间隔判定，与“新增用户”互斥。"
        "精确日 Dn 留存曲线从 D5 到 D6 回升，只表示 D6 当天活跃人数高于 D5，"
        "不能自动解释为回流用户；只有逐用户满足连续沉默/流失阈值后再次活跃，才计入回流。",
    ),

    # 统一事件与漏斗
    (
        "事件明细",
        ["埋点", "事件", "行为事件", "fact_events", "event_name"],
        "fact_events 是统一原始埋点明细表，一行代表一次客户端、服务端或 SDK 事件。"
        "事件含义和必填属性来自 dim_event_name，常用字段包括 event_date/event_time、event_name、event_category、player_id、session_id、lifecycle_day、"
        "player_level、vip_level、power、platform、channel、country、event_source、sequence_in_session 和 attributes。"
        "用 fact_events 分析事件次数、事件人数、行为路径和事件属性；不要用它替代 fact_sessions 的 DAU/时长口径。",
    ),
    (
        "事件次数和事件人数",
        ["事件量", "触发次数", "触发人数", "行为人数", "UV", "PV"],
        "事件次数 = fact_events 中满足条件的行数 count(*)；事件人数 = count(DISTINCT player_id)。"
        "按 event_name/event_category 分组可查看各类行为规模。"
        "如果同一个事件可能重复触发，漏斗或完成率必须转成玩家级 bool_or/exists 后再统计，不能直接用事件条数当用户数。",
    ),
    (
        "漏斗分析",
        ["转化漏斗", "转化路径", "流失分析", "用户流失", "任务节点流失", "节点流失", "引导任务漏斗", "再引导任务", "funnel"],
        "漏斗分析口径：先确定同一目标 cohort 和同一时间窗口，再按玩家粒度生成每个步骤是否完成的状态。"
        "漏斗主图字段使用 step_order、step_name、users，users 必须是完成当前步骤且已完成所有前序步骤的 distinct player_id，"
        "因此人数应单调不增。禁止直接对 fact_events、fact_battles、fact_payments 等事件/明细表 count(*) 当作用户数；"
        "禁止每个步骤独立 count 后直接 UNION，因为这会导致后续步骤人数大于前序步骤。"
        "正确做法是先构造 player_level，一行一个 player_id，用 bool_or/exists 标记每个节点是否完成，再用 count(*) FILTER 按前序条件逐级过滤。"
        "如果生成结果出现后续步骤人数大于前序步骤、完成率超过 100% 或流失率为负数，说明 SQL 口径错误，必须重写。"
        "多维度流失拆解用同一 player_level 明细按渠道、设备、服务器等分组汇总，不把多个维度混在同一个 funnel 图里。",
    ),
    (
        "新手教程步骤",
        ["教程步骤", "新手步骤", "tutorial", "tutorial_step"],
        "tutorial_step 是新手步骤明细事件，必须读取 fact_events.attributes->>'step' 区分具体步骤。"
        "发生过任意 tutorial_step 只能表示进入过新手流程，不能表示完成教程；"
        "教程完成应使用实际最大步骤或关键里程碑步骤判断。"
        "按步骤漏斗统计时先在玩家级别判断是否完成 step>=N，再按前序步骤逐级过滤。",
    ),
    (
        "买量事件",
        ["广告曝光", "广告点击", "ad_impression", "ad_click", "投放事件"],
        "广告曝光和点击来自 fact_events 中 event_name = 'ad_impression' / 'ad_click'，事件属性里包含 ad_network、campaign_id。"
        "这些事件用于买量触达/点击行为分析；新增、渠道归因和 cohort 仍以 dim_player.install_date、channel、campaign 为准。",
    ),
    (
        "质量事件",
        ["崩溃", "客户端错误", "网络错误", "crash", "client_error", "network_error"],
        "质量问题来自 fact_events：event_name 包括 crash、client_error、network_error，event_category = 'quality'。"
        "问题次数用 count(*)，受影响用户数用 count(DISTINCT player_id)，可按 platform、device_model、os_version、network_type、app_build 拆分。",
    ),

    # 付费、收入与商品
    (
        "流水",
        ["收入", "营收", "revenue", "付费金额", "充值", "付费收入", "GMV"],
        "收入/流水口径：默认使用净收入 net_revenue_usd（退款订单该字段为 0），从 fact_payments 明细 sum 计算；"
        "必须过滤 payment_status = 'success' 且 net_revenue_usd > 0。"
        "不要用 amount_usd 作为正式收入，amount_usd 只能表示订单原始金额/标价，可能包含失败、取消或退款订单；"
        "如需毛流水用 gross_revenue_usd，退款金额用 refund_amount_usd。"
        "统计收入时按 fact_payments.event_date 落在统计周期内汇总。",
    ),
    (
        "订单状态",
        ["支付状态", "成功订单", "失败订单", "取消订单", "退款订单", "payment_status"],
        "fact_payments.payment_status 包括 success、failed、cancelled、refunded。"
        "正式收入、付费用户、ARPU、ARPPU、LTV 默认只统计 payment_status = 'success' 且 net_revenue_usd > 0 的订单。"
        "失败/取消订单可用于支付失败率或取消率分析；退款订单的净收入 net_revenue_usd 为 0，退款金额看 refund_amount_usd。",
    ),
    (
        "毛收入和退款",
        ["毛流水", "退款金额", "净收入", "gross revenue", "refund", "net revenue"],
        "amount_usd 是订单原始金额/标价，gross_revenue_usd 是毛收入，refund_amount_usd 是退款金额，net_revenue_usd 是净收入。"
        "经营收入默认用 net_revenue_usd；分析退款时使用 payment_status='refunded' 或 refund_amount_usd > 0；"
        "不要把 amount_usd 直接当正式收入，因为失败、取消或退款订单也可能有原始金额。",
    ),
    (
        "付费用户",
        ["付费玩家", "付费人数", "payer", "付费人群"],
        "付费用户口径：统计周期内在 fact_payments 中 payment_status = 'success' 且 net_revenue_usd > 0 的去重 player_id。"
        "不要只用 amount_usd > 0 判断付费用户，因为失败、取消或退款订单也可能有原始订单金额。"
        "首充用户可用 is_first_pay = true 或 dim_player.first_pay_time 落在周期内判定。",
    ),
    (
        "付费率",
        ["付费转化率", "付费渗透率", "payer rate", "付费占比"],
        "付费率口径：付费用户数 / 活跃（或新增）用户数 × 100%。必须明确分母是活跃用户还是新增用户，"
        "默认用同周期活跃用户（DAU 口径去重）。付费率是非累加比率指标，取值 0~100%，"
        "按维度对比时使用柱状图而非饼图。",
    ),
    (
        "首付成功",
        ["首充成功", "首次付费成功", "first pay", "first purchase"],
        "首付/首充成功口径：使用 fact_payments 时必须过滤 payment_status = 'success' 且 net_revenue_usd > 0，"
        "再结合 is_first_pay = true 或 pay_sequence = 1 统计首次成功付费玩家。"
        "failed、cancelled、refunded 订单不能计入成功首付。",
    ),
    (
        "ARPU",
        ["人均收入", "平均每用户收入", "每用户平均收入"],
        "ARPU 口径：统计周期净收入 sum(fact_payments.net_revenue_usd) / 活跃用户数（DAU 口径去重）。"
        "付费过滤 payment_status='success' 且 net_revenue_usd>0；活跃分母来自 fact_sessions。"
        "ARPU 为人均值、非累加指标，按维度对比用柱状图，不要用饼图，也不要用总收入替代。",
    ),
    (
        "ARPPU",
        ["付费用户人均收入", "每付费用户收入", "人均付费"],
        "ARPPU 口径：统计周期净收入 / 付费用户数，付费用户为 fact_payments 中 payment_status='success' 且 net_revenue_usd>0 的去重 player_id。"
        "ARPPU 为付费人群人均值、非累加指标，按维度对比用柱状图。",
    ),
    (
        "LTV",
        ["生命周期价值", "用户终身价值", "生命周期收入", "长期价值"],
        "LTV 口径：对同一 install cohort，LTV(n) = 该 cohort 截至 lifecycle_day <= n 的累计净收入 / cohort 人数。"
        "收入来自 fact_payments，必须过滤 payment_status='success' 且 net_revenue_usd>0。"
        "累计 LTV 必须随生命周期天数单调不下降；同一条曲线必须使用同一批 cohort 和同一个分母。"
        "若出现 D30 < D7 或增长倍率 < 1，说明口径错误需重写，不能解释为真实业务现象。"
        "需要展示总收入时字段须明确命名为 cumulative_revenue/total_revenue，不要把分组总收入命名为 LTV。",
    ),
    (
        "生命周期日付费率",
        ["新增用户生命周期付费率", "新增用户每日付费率", "生命周期日付费留存", "daily payer rate"],
        "生命周期日付费率口径：针对同一新增 install_date cohort，统计 lifecycle_day = n 当天发生成功支付的去重玩家数 / cohort 新增用户数。"
        "它描述的是某一天是否付费，不是累计转化，也不是连续留存；因此曲线可以波动，允许出现 D1=0 但 D2>0。"
        "分子必须过滤 payment_status = 'success' 且 net_revenue_usd > 0，分母固定为该 install_date cohort 新增用户数。"
        "图表标题和 y 轴建议使用“生命周期日付费率”，不要只写“付费留存率”造成单调递减或累计指标的误解。",
    ),
    (
        "付费留存",
        ["付费留存率", "新增用户付费留存", "付费回访", "payer retention", "paid retention"],
        "付费留存必须先判断用户想看的分母和行为："
        "若问题是“新增用户的付费留存/生命周期付费曲线”，默认按“生命周期日付费率”处理，即 lifecycle_day=n 当天成功付费人数 / 新增 cohort 人数，曲线可波动；"
        "若问题是“D0付费用户后续是否继续付费/复购留存”，分母应固定为 D0 成功付费用户，D0=100%；"
        "若用户问“累计付费转化/累计付费率”，应统计 lifecycle_day<=n 曾成功付费的玩家 / cohort 新增用户数，曲线应单调不下降。"
        "最近 N 天新增用户应以数据最大日期为观察截止日回推 N 天；未成熟 lifecycle_day 返回 NULL，不要当作 0%。",
    ),
    (
        "累计付费转化",
        ["累计付费率", "累计付费转化率", "累计付费留存", "cumulative payer conversion"],
        "累计付费转化口径：针对同一新增 cohort，统计截至 lifecycle_day<=n 曾发生成功支付的去重玩家数 / cohort 新增用户数。"
        "分子必须过滤 payment_status = 'success' 且 net_revenue_usd > 0。该指标是累计指标，随 lifecycle_day 单调不下降；"
        "如果结果出现下降，说明 SQL 口径错误或分母变化，需要重写。",
    ),
    (
        "首日付费用户复购留存",
        ["D0付费用户留存", "付费用户复购留存", "付费用户回访", "repeat payer retention"],
        "首日付费用户复购留存口径：先锁定 lifecycle_day=0 且成功付费的玩家作为 base，分母固定为 D0 成功付费用户数；"
        "Dn = base 用户中在 lifecycle_day=n 再次成功付费的去重玩家数 / base 用户数，D0=100%。"
        "这是复购行为指标，不等同于新增用户生命周期日付费率，也不等同于累计付费转化。",
    ),
    (
        "商品付费结构",
        ["礼包付费结构", "商品收入结构", "礼包收入结构", "商品分析", "礼包分析", "商品类型收入", "product revenue mix"],
        "商品/礼包付费结构分析口径：从 fact_payments 关联 dim_product，必须过滤 payment_status = 'success' 且 net_revenue_usd > 0。"
        "收入字段用 sum(net_revenue_usd)，购买人数用 count(DISTINCT player_id)，订单数用 count(*)。"
        "不要用 sum(amount_usd) 作为正式收入；amount_usd 会让失败、取消或退款订单影响结构判断。"
        "按 product_type 看大类结构可以用饼图；若同时展示收入、购买人数、订单数、ARPPU、复购率，优先用表格或柱图，不要全部塞进饼图。",
    ),

    # 战斗、资源、成长与社交
    (
        "战斗分析",
        ["战斗", "战斗次数", "战斗人数", "PVE", "PVP", "野怪", "资源点", "fact_battles"],
        "战斗明细使用 fact_battles，一行是一场战斗结算。"
        "战斗次数 count(*)，战斗人数 count(DISTINCT player_id)，可按 event_date、battle_type、target_type、server_id、channel、result 分组。"
        "battle_type 包括 pve_chapter、world_monster、resource_tile、pvp；target_type 包括 npc、monster、player。"
        "如需玩家属性拆分可关联 dim_player，但收入或会话指标要先预聚合后再 join。",
    ),
    (
        "战斗胜率",
        ["胜率", "战斗胜率", "win rate"],
        "战斗胜率 = fact_battles 中 result='win' 的战斗次数 / 总战斗次数 × 100。"
        "如果用户问玩家胜率，可先按 player_id 聚合胜负次数后再求玩家维度分布；"
        "不要把胜利玩家数 / 活跃玩家数误写成战斗胜率。",
    ),
    (
        "兵损和战力变化",
        ["兵损", "伤兵", "战损", "战力变化", "power_delta"],
        "战斗兵损和战力变化来自 fact_battles：troops_sent、troops_lost、wounded、power_delta。"
        "资源掠夺看 resource_looted，体力消耗看 stamina_spent。"
        "这些是战斗结算明细指标，按 battle_type/result/target_type 分组时可 sum 或 avg；"
        "按玩家分析时先聚合到 player_id，避免和其他事实表直接多对多关联。",
    ),
    (
        "资源流水",
        ["资源", "资源变动", "资源流水", "resource_change", "fact_resource_transactions"],
        "资源流水使用 fact_resource_transactions，一行是一笔资源增减。"
        "resource_type 包括 food、wood、stone、iron、gold；change_amount 为带符号变动量，balance_after 为变动后余额。"
        "source_sink 标记 gain 或 sink，reason 标记来源/消耗原因，例如 quest_reward、battle_loot、offline_reward、payment_grant、building_upgrade、research、troop_training。"
        "总产出/消耗建议分别按 source_sink 或 change_amount 正负统计，不要把正负直接相加后当作总流水。",
    ),
    (
        "资源产出和消耗",
        ["资源产出", "资源消耗", "资源缺口", "资源通胀", "source_sink"],
        "资源产出 = fact_resource_transactions 中 source_sink='gain' 或 change_amount>0 的资源变动量；"
        "资源消耗 = source_sink='sink' 或 change_amount<0 的绝对值。"
        "分析资源缺口时同时返回 gain_amount、sink_amount、net_change_amount，不要只看净变化。"
        "gold 主要来自 payment_grant，food/wood/stone/iron 同时存在任务、战斗、离线奖励、建筑、科技、练兵等来源/消耗。",
    ),
    (
        "付费相关资源",
        ["付费资源", "礼包发放资源", "payment_grant", "is_paid_related"],
        "付费相关资源来自 fact_resource_transactions.is_paid_related = true 或 reason='payment_grant'。"
        "这表示资源变化与支付发放相关，不等同于收入金额；收入仍以 fact_payments.net_revenue_usd 为准。"
        "如需分析付费带来的资源投放，可按 resource_type、event_date、player_id 聚合资源变化，再与支付用户分层关联。",
    ),
    (
        "建筑升级",
        ["建筑", "建筑升级", "building_upgrade", "主城", "城堡等级"],
        "建筑升级明细使用 fact_building_upgrades，一行是一项建筑升级完成任务。"
        "building_type 表示建筑类型，from_level/to_level 表示升级前后等级，duration_seconds 为原始耗时，speedup_seconds 为加速秒数，"
        "power_gain 为战力增长，cost_json 为资源消耗 JSON。"
        "主城/城堡当前等级也可看 dim_player.current_city_level，但历史升级过程应使用 fact_building_upgrades。",
    ),
    (
        "科技研究",
        ["科技", "研究", "research", "科技升级"],
        "科技研究明细使用 fact_research，一行是一项科技研究完成任务。"
        "research_type 表示科技类型，from_level/to_level 表示升级前后等级，duration_seconds、speedup_seconds、power_gain、cost_json 分别表示耗时、加速、战力增长和资源消耗。"
        "分析科技完成率、研究耗时或科技带来的战力时，优先使用 fact_research，不要只用 fact_events 的 research_start/research_finish 事件数。",
    ),
    (
        "士兵训练",
        ["练兵", "训练士兵", "兵种训练", "troop training", "army training"],
        "士兵训练明细使用 fact_army_training，一行是一项训练完成任务。"
        "troop_type 包括 infantry、archer、cavalry、siege；troop_tier 为兵阶，troop_count 为训练数量，"
        "duration_seconds、speedup_seconds、power_gain、cost_json 分别表示耗时、加速、战力增长和资源消耗。",
    ),
    (
        "加速使用",
        ["加速", "加速道具", "speedup", "speedup_use"],
        "加速行为可从 fact_events 中 event_name='speedup_use' 分析触发次数和人数；"
        "建筑、科技、练兵任务实际缩短时间分别在 fact_building_upgrades、fact_research、fact_army_training 的 speedup_seconds 字段。"
        "如果用户问加速对任务耗时的影响，应使用任务明细表的 speedup_seconds，而不是只统计 speedup_use 事件数。",
    ),
    (
        "玩家成长",
        ["等级成长", "战力成长", "VIP成长", "level_up", "power"],
        "玩家成长可从 fact_events 的 player_level、vip_level、power 观察事件时点状态，level_up 事件表示玩家升级；"
        "当前等级、当前 VIP、当前战力和当前城堡等级在 dim_player 的 current_level、current_vip_level、current_power、current_city_level。"
        "分析历史趋势时用事实表时点字段；分析当前分布时用 dim_player.current_* 字段。",
    ),
    (
        "联盟行为",
        ["联盟加入", "联盟帮助", "联盟捐献", "集结", "alliance"],
        "联盟行为来自 fact_events：alliance_join、alliance_help、alliance_donate、rally_join。"
        "联盟维度表 dim_alliance 包含 alliance_tag/name/language/tier/member_count/active_member_7d/total_power。"
        "当前联盟归属可用 dim_player.current_alliance_id；历史行为分析优先使用 fact_events.alliance_id 或事件发生时记录。",
    ),
    (
        "活跃用户分层",
        ["活跃分层", "活跃度分层", "activity segment", "付费分层", "payer_segment"],
        "活跃分层使用 dim_player.activity_segment；付费分层使用 dim_player.payer_segment。"
        "做人群结构分析时优先复用这两个已有分层字段，不要临时自定义阈值。"
        "注意这是当前玩家画像分层，不一定代表历史某一天的状态。",
    ),
    (
        "预测分析",
        ["预测", "预估", "预计", "推算", "forecast", "predict"],
        "预测分析口径：先明确目标对象、预测指标、已观测窗口和预测周期。"
        "预测结果应区分 actual_value（已观测）、benchmark_value（历史成熟基准）和 predicted_value（预测值），"
        "并提供 sample_size、forecast_basis、confidence。"
        "只有部分生命周期已成熟时，用目标 cohort 已成熟的真实观测点作为锚点，结合历史成熟 cohort 曲线外推；"
        "已观测天数越多、样本越大，置信度越高。",
    ),
]


# ---------------------------------------------------------------------------
# 数据训练 SQL 示例：question 示例问法 / answer 口径说明 + 标准 SQL
# 全部为只读 SELECT，指标在查询时从明细表计算（符合 AGENTS.md）。
# ---------------------------------------------------------------------------
EXAMPLES: list[tuple[str, str]] = [
    (
        "最近30天每日DAU趋势",
        "DAU = 每个自然日 fact_sessions 去重活跃玩家。观察基准日取 fact_sessions 最大日期。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(session_start::date) AS max_date FROM fact_sessions)\n"
        "SELECT s.session_start::date AS stat_date,\n"
        "       count(DISTINCT s.player_id) AS dau\n"
        "FROM fact_sessions s CROSS JOIN obs\n"
        "WHERE s.session_start::date > obs.max_date - 30\n"
        "GROUP BY 1 ORDER BY 1;\n"
        "```",
    ),
    (
        "最近7天每日新增用户",
        "新增用户按 dim_player.install_date 统计，基准日取最大 install_date。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(install_date) AS max_date FROM dim_player)\n"
        "SELECT p.install_date AS stat_date,\n"
        "       count(*) AS new_users\n"
        "FROM dim_player p CROSS JOIN obs\n"
        "WHERE p.install_date > obs.max_date - 7\n"
        "GROUP BY 1 ORDER BY 1;\n"
        "```",
    ),
    (
        "新增用户的次日/3日/7日/14日/30日留存率",
        "成熟 cohort 留存：每个 Dn 的分母只含 install_date <= 观察最大日期 - n 的玩家，"
        "分子是这些玩家在 lifecycle_day = n 于 fact_sessions 活跃的去重数。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(session_start::date) AS max_date FROM fact_sessions),\n"
        "days(n) AS (VALUES (1),(3),(7),(14),(30)),\n"
        "base AS (\n"
        "  SELECT d.n,\n"
        "         count(DISTINCT p.player_id) AS cohort_size,\n"
        "         count(DISTINCT s.player_id) AS retained_users\n"
        "  FROM days d\n"
        "  CROSS JOIN obs\n"
        "  JOIN dim_player p ON p.install_date <= obs.max_date - d.n\n"
        "  LEFT JOIN fact_sessions s\n"
        "    ON s.player_id = p.player_id AND s.lifecycle_day = d.n\n"
        "  GROUP BY d.n\n"
        ")\n"
        "SELECT 'D' || n AS lifecycle_day, n AS day_index,\n"
        "       cohort_size, retained_users,\n"
        "       round(retained_users::numeric / nullif(cohort_size,0) * 100, 2) AS retention_pct\n"
        "FROM base ORDER BY n;\n"
        "```",
    ),
    (
        "帮我分析5月18号新增用户的留存情况",
        "单日新增 cohort 留存：先锁定 2026-05-18 新增用户，分母固定为该日新增总人数；"
        "分子必须来自 fact_sessions 的会话/登录活跃，不要用 fact_events 代替留存活跃口径。"
        "这里的 retention_pct 是精确日/当日 Dn 留存，只看 lifecycle_day = n 当天是否活跃，"
        "不要求 D1 到 Dn 连续活跃，因此折线可以下降后再回升；"
        "这种起伏不能直接解释为回流用户，回流必须另按连续沉默阈值逐用户判定。"
        "若用户要单调下降的曲线，应改问连续留存/未流失存量或滚动留存。"
        "结果同时返回 active_users 与 retention_pct 时，retention_pct 返回 0~100 数值，不拼接 '%'；"
        "图表建议：活跃人数用左轴柱，留存率用右轴折线，避免人数和百分比共用同一 Y 轴。\n"
        "```sql\n"
        "WITH cohort AS (\n"
        "  SELECT p.player_id\n"
        "  FROM dim_player p\n"
        "  WHERE p.install_date = DATE '2026-05-18'\n"
        "),\n"
        "cohort_size AS (\n"
        "  SELECT count(*) AS new_users FROM cohort\n"
        "),\n"
        "days AS (\n"
        "  SELECT generate_series(\n"
        "           0,\n"
        "           (SELECT coalesce(max(s.lifecycle_day), 0)\n"
        "            FROM fact_sessions s\n"
        "            JOIN cohort c ON c.player_id = s.player_id)\n"
        "         ) AS day_index\n"
        "),\n"
        "active AS (\n"
        "  SELECT s.lifecycle_day AS day_index,\n"
        "         count(DISTINCT s.player_id) AS active_users\n"
        "  FROM fact_sessions s\n"
        "  JOIN cohort c ON c.player_id = s.player_id\n"
        "  GROUP BY s.lifecycle_day\n"
        ")\n"
        "SELECT d.day_index,\n"
        "       'D' || d.day_index AS lifecycle_day,\n"
        "       cs.new_users,\n"
        "       coalesce(a.active_users, 0) AS active_users,\n"
        "       round(coalesce(a.active_users, 0)::numeric / nullif(cs.new_users, 0) * 100, 2) AS retention_pct\n"
        "FROM days d\n"
        "CROSS JOIN cohort_size cs\n"
        "LEFT JOIN active a ON a.day_index = d.day_index\n"
        "ORDER BY d.day_index;\n"
        "```",
    ),
    (
        "分析6月1号新增用户的每日留存趋势",
        "单日新增 cohort 留存：先锁定指定 install_date 的 cohort，分母固定为该日新增总人数；"
        "再按 lifecycle_day 统计这些玩家当天在 fact_sessions 中活跃的去重人数。"
        "本示例返回的是精确日/当日 Dn 留存，曲线允许波动，后一天高于前一天不等于回流用户；"
        "回流用户必须另设连续沉默/流失阈值，连续留存或滚动留存也应使用不同 SQL。"
        "不要在按 s.lifecycle_day 分组后使用 count(distinct p.player_id) 当分母，"
        "因为 LEFT JOIN 后每个分组只剩当天活跃玩家，会导致 cohort_size = active_users、留存率恒为 100%。"
        "留存率字段返回 0~100 的数值，不拼接 '%'；D0 可为 100%，D1 及以后必须按活跃人数 / 固定 cohort_size 计算。\n"
        "```sql\n"
        "WITH cohort AS (\n"
        "  SELECT p.player_id\n"
        "  FROM dim_player p\n"
        "  WHERE p.install_date = DATE '2026-06-01'\n"
        "),\n"
        "cohort_size AS (\n"
        "  SELECT count(*) AS new_users FROM cohort\n"
        "),\n"
        "days AS (\n"
        "  SELECT generate_series(\n"
        "           0,\n"
        "           (SELECT max(s.lifecycle_day) FROM fact_sessions s JOIN cohort c ON c.player_id = s.player_id)\n"
        "         ) AS day_index\n"
        "),\n"
        "active AS (\n"
        "  SELECT s.lifecycle_day AS day_index,\n"
        "         count(DISTINCT s.player_id) AS active_users\n"
        "  FROM fact_sessions s\n"
        "  JOIN cohort c ON c.player_id = s.player_id\n"
        "  GROUP BY s.lifecycle_day\n"
        ")\n"
        "SELECT d.day_index,\n"
        "       'D' || d.day_index AS lifecycle_day,\n"
        "       cs.new_users,\n"
        "       coalesce(a.active_users, 0) AS active_users,\n"
        "       round(coalesce(a.active_users, 0)::numeric / nullif(cs.new_users, 0) * 100, 2) AS retention_pct\n"
        "FROM days d\n"
        "CROSS JOIN cohort_size cs\n"
        "LEFT JOIN active a ON a.day_index = d.day_index\n"
        "ORDER BY d.day_index;\n"
        "```",
    ),
    (
        "帮我分析最近一个月新增用户的留存情况",
        "按 install_date 展示最近一个月新增 cohort 的 D1/D7/D14/D30 留存。"
        "每个 Dn 只有 install_date <= 观察最大日期 - n 时才成熟，否则返回 NULL，不把未成熟样本当作 0%。"
        "留存率字段返回 0~100 的数值，便于图表按百分比轴展示；不要拼接 '%'。\n"
        "```sql\n"
        "WITH obs AS (\n"
        "  SELECT max(session_start::date) AS max_date FROM fact_sessions\n"
        "),\n"
        "cohort AS (\n"
        "  SELECT p.player_id, p.install_date\n"
        "  FROM dim_player p CROSS JOIN obs\n"
        "  WHERE p.install_date BETWEEN obs.max_date - 29 AND obs.max_date\n"
        "),\n"
        "retained AS (\n"
        "  SELECT c.install_date,\n"
        "         count(DISTINCT c.player_id) AS new_users,\n"
        "         count(DISTINCT s.player_id) FILTER (WHERE s.lifecycle_day = 1) AS d1_users,\n"
        "         count(DISTINCT s.player_id) FILTER (WHERE s.lifecycle_day = 7) AS d7_users,\n"
        "         count(DISTINCT s.player_id) FILTER (WHERE s.lifecycle_day = 14) AS d14_users,\n"
        "         count(DISTINCT s.player_id) FILTER (WHERE s.lifecycle_day = 30) AS d30_users\n"
        "  FROM cohort c\n"
        "  LEFT JOIN fact_sessions s ON s.player_id = c.player_id\n"
        "  GROUP BY c.install_date\n"
        ")\n"
        "SELECT r.install_date,\n"
        "       r.new_users,\n"
        "       CASE WHEN r.install_date <= obs.max_date - 1\n"
        "            THEN round(r.d1_users::numeric / nullif(r.new_users, 0) * 100, 2) END AS d1_retention_pct,\n"
        "       CASE WHEN r.install_date <= obs.max_date - 7\n"
        "            THEN round(r.d7_users::numeric / nullif(r.new_users, 0) * 100, 2) END AS d7_retention_pct,\n"
        "       CASE WHEN r.install_date <= obs.max_date - 14\n"
        "            THEN round(r.d14_users::numeric / nullif(r.new_users, 0) * 100, 2) END AS d14_retention_pct,\n"
        "       CASE WHEN r.install_date <= obs.max_date - 30\n"
        "            THEN round(r.d30_users::numeric / nullif(r.new_users, 0) * 100, 2) END AS d30_retention_pct\n"
        "FROM retained r CROSS JOIN obs\n"
        "ORDER BY r.install_date;\n"
        "```",
    ),
    (
        "最近30天总流水、ARPU、ARPPU和付费率",
        "收入用成功订单净收入 net_revenue_usd；活跃用户用 fact_sessions 去重；"
        "付费用户必须过滤 payment_status='success' 且 net_revenue_usd>0。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(session_start::date) AS max_date FROM fact_sessions),\n"
        "win AS (SELECT (max_date - 29) AS start_date, max_date FROM obs),\n"
        "active AS (\n"
        "  SELECT count(DISTINCT s.player_id) AS active_users\n"
        "  FROM fact_sessions s CROSS JOIN win\n"
        "  WHERE s.session_start::date BETWEEN win.start_date AND win.max_date\n"
        "),\n"
        "pay AS (\n"
        "  SELECT count(DISTINCT p.player_id) AS payers,\n"
        "         coalesce(sum(p.net_revenue_usd), 0) AS revenue\n"
        "  FROM fact_payments p CROSS JOIN win\n"
        "  WHERE p.event_date BETWEEN win.start_date AND win.max_date\n"
        "    AND p.payment_status = 'success'\n"
        "    AND p.net_revenue_usd > 0\n"
        ")\n"
        "SELECT a.active_users, p.payers, round(p.revenue, 2) AS revenue,\n"
        "       round(p.revenue / nullif(a.active_users,0), 4) AS arpu,\n"
        "       round(p.revenue / nullif(p.payers,0), 4) AS arppu,\n"
        "       round(p.payers::numeric / nullif(a.active_users,0) * 100, 2) AS payer_rate_pct\n"
        "FROM active a CROSS JOIN pay p;\n"
        "```",
    ),
    (
        "最近30天各渠道的付费率、ARPPU和收入对比",
        "按 dim_player.channel 分组，活跃来自 fact_sessions，付费来自 fact_payments 成功净收入订单。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(event_date) AS max_date FROM fact_events),\n"
        "win AS (SELECT (max_date - 29) AS start_date, max_date FROM obs),\n"
        "act AS (\n"
        "  SELECT p.channel, count(DISTINCT s.player_id) AS active_users\n"
        "  FROM fact_sessions s\n"
        "  JOIN dim_player p ON p.player_id = s.player_id\n"
        "  CROSS JOIN win\n"
        "  WHERE s.session_start::date BETWEEN win.start_date AND win.max_date\n"
        "  GROUP BY p.channel\n"
        "),\n"
        "pay AS (\n"
        "  SELECT p.channel,\n"
        "         count(DISTINCT pay.player_id) AS payers,\n"
        "         coalesce(sum(pay.net_revenue_usd), 0) AS revenue\n"
        "  FROM fact_payments pay\n"
        "  JOIN dim_player p ON p.player_id = pay.player_id\n"
        "  CROSS JOIN win\n"
        "  WHERE pay.event_date BETWEEN win.start_date AND win.max_date\n"
        "    AND pay.payment_status = 'success'\n"
        "    AND pay.net_revenue_usd > 0\n"
        "  GROUP BY p.channel\n"
        ")\n"
        "SELECT a.channel, a.active_users,\n"
        "       coalesce(pay.payers, 0) AS payers,\n"
        "       round(coalesce(pay.revenue, 0), 2) AS revenue,\n"
        "       round(coalesce(pay.revenue, 0) / nullif(pay.payers, 0), 4) AS arppu,\n"
        "       round(coalesce(pay.payers, 0)::numeric / nullif(a.active_users, 0) * 100, 2) AS payer_rate_pct\n"
        "FROM act a LEFT JOIN pay ON pay.channel = a.channel\n"
        "ORDER BY revenue DESC;\n"
        "```",
    ),
    (
        "最近一周新增用户的付费留存 用折线图",
        "本问题按“生命周期日付费率”理解：同一新增 cohort 在 lifecycle_day=n 当天发生成功支付的玩家数 / cohort 新增用户数。"
        "这不是累计付费转化，也不是连续留存；曲线可波动，允许 D1=0 但 D2>0。"
        "最近一周以数据最大日期为截止日回推 7 天；成熟但无人付费为 0，未成熟 lifecycle_day 返回 NULL。"
        "折线图标题建议写“最近一周新增用户生命周期日付费率”，y 轴名称用“生命周期日付费率”，"
        "配置建议：x=day_index 或 lifecycle_day，y=daily_payer_rate_pct，series=install_date。\n"
        "```sql\n"
        "WITH obs AS (\n"
        "  SELECT max(event_date) AS max_date FROM fact_events\n"
        "),\n"
        "days(n) AS (VALUES (0),(1),(2),(3),(4),(5),(6)),\n"
        "cohort AS (\n"
        "  SELECT p.player_id, p.install_date\n"
        "  FROM dim_player p CROSS JOIN obs\n"
        "  WHERE p.install_date BETWEEN obs.max_date - 6 AND obs.max_date\n"
        "),\n"
        "cohort_size AS (\n"
        "  SELECT install_date, count(*) AS new_users\n"
        "  FROM cohort\n"
        "  GROUP BY install_date\n"
        "),\n"
        "paid AS (\n"
        "  SELECT c.install_date,\n"
        "         pay.lifecycle_day,\n"
        "         count(DISTINCT c.player_id) AS paying_users\n"
        "  FROM cohort c\n"
        "  JOIN fact_payments pay ON pay.player_id = c.player_id\n"
        "   AND pay.payment_status = 'success'\n"
        "   AND pay.net_revenue_usd > 0\n"
        "  GROUP BY c.install_date, pay.lifecycle_day\n"
        "),\n"
        "grid AS (\n"
        "  SELECT cs.install_date, d.n AS day_index, 'D' || d.n AS lifecycle_day, cs.new_users\n"
        "  FROM cohort_size cs CROSS JOIN days d\n"
        ")\n"
        "SELECT g.install_date,\n"
        "       g.day_index,\n"
        "       g.lifecycle_day,\n"
        "       g.new_users,\n"
       "       CASE WHEN g.install_date <= obs.max_date - g.day_index\n"
       "            THEN coalesce(p.paying_users, 0) END AS paying_users,\n"
       "       CASE WHEN g.install_date <= obs.max_date - g.day_index\n"
       "            THEN round(coalesce(p.paying_users, 0)::numeric / nullif(g.new_users, 0) * 100, 2) END AS daily_payer_rate_pct\n"
        "FROM grid g\n"
        "CROSS JOIN obs\n"
        "LEFT JOIN paid p ON p.install_date = g.install_date AND p.lifecycle_day = g.day_index\n"
        "ORDER BY g.install_date, g.day_index;\n"
        "```",
    ),
    (
        "最近一周新增用户的累计付费转化 用折线图",
        "如果用户希望曲线随生命周期不下降，应使用累计付费转化：截至 lifecycle_day<=n 曾成功付费的玩家数 / cohort 新增用户数。"
        "同一 install_date cohort 分母固定；未成熟 lifecycle_day 返回 NULL。"
        "折线图标题建议写“最近一周新增用户累计付费转化率”，y 轴名称用“累计付费转化率”，"
        "配置建议：x=day_index 或 lifecycle_day，y=cumulative_payer_rate_pct，series=install_date。\n"
        "```sql\n"
        "WITH obs AS (\n"
        "  SELECT max(event_date) AS max_date FROM fact_events\n"
        "),\n"
        "days(n) AS (VALUES (0),(1),(2),(3),(4),(5),(6)),\n"
        "cohort AS (\n"
        "  SELECT p.player_id, p.install_date\n"
        "  FROM dim_player p CROSS JOIN obs\n"
        "  WHERE p.install_date BETWEEN obs.max_date - 6 AND obs.max_date\n"
        "),\n"
        "cohort_size AS (\n"
        "  SELECT install_date, count(*) AS new_users\n"
        "  FROM cohort\n"
        "  GROUP BY install_date\n"
        "),\n"
        "payer_day AS (\n"
        "  SELECT c.install_date,\n"
        "         pay.player_id,\n"
        "         min(pay.lifecycle_day) AS first_paid_day\n"
        "  FROM cohort c\n"
        "  JOIN fact_payments pay ON pay.player_id = c.player_id\n"
        "   AND pay.payment_status = 'success'\n"
        "   AND pay.net_revenue_usd > 0\n"
        "  GROUP BY c.install_date, pay.player_id\n"
        "),\n"
        "grid AS (\n"
        "  SELECT cs.install_date, d.n AS day_index, 'D' || d.n AS lifecycle_day, cs.new_users\n"
        "  FROM cohort_size cs CROSS JOIN days d\n"
        ")\n"
        "SELECT g.install_date,\n"
        "       g.day_index,\n"
        "       g.lifecycle_day,\n"
        "       g.new_users,\n"
        "       CASE WHEN g.install_date <= obs.max_date - g.day_index\n"
        "            THEN count(DISTINCT pd.player_id) END AS cumulative_payers,\n"
        "       CASE WHEN g.install_date <= obs.max_date - g.day_index\n"
        "            THEN round(count(DISTINCT pd.player_id)::numeric / nullif(g.new_users, 0) * 100, 2) END AS cumulative_payer_rate_pct\n"
        "FROM grid g\n"
        "CROSS JOIN obs\n"
        "LEFT JOIN payer_day pd ON pd.install_date = g.install_date AND pd.first_paid_day <= g.day_index\n"
        "GROUP BY g.install_date, g.day_index, g.lifecycle_day, g.new_users, obs.max_date\n"
        "ORDER BY g.install_date, g.day_index;\n"
        "```",
    ),
    (
        "最近一周新增用户生命周期付费表现",
        "这是混合指标分析，主图不要把总收入、平均付费、付费率全部放进同一个同轴图。"
        "推荐主图：x=day_index/lifecycle_day，柱=total_revenue，右轴折线=daily_payer_rate_pct；"
        "avg_revenue_per_payer 作为表格字段或文字结论解释，不加入 multi-quota。"
        "累计 LTV 应单独按 install_date cohort 生成生命周期曲线，不要混在这个总收入/付费率组合图里。"
        "生命周期数据要补齐 D0-D7 网格；分母使用已成熟到该 lifecycle_day 的 observed_users，成熟但无付费返回 0，未成熟 lifecycle_day 返回 NULL。"
        "收入必须使用 payment_status='success' 且 net_revenue_usd > 0 的净收入。\n"
        "```sql\n"
        "WITH obs AS (\n"
        "  SELECT max(event_date) AS max_date FROM fact_events\n"
        "),\n"
        "days(n) AS (VALUES (0),(1),(2),(3),(4),(5),(6),(7)),\n"
        "cohort AS (\n"
        "  SELECT p.player_id, p.install_date\n"
        "  FROM dim_player p CROSS JOIN obs\n"
        "  WHERE p.install_date BETWEEN obs.max_date - 6 AND obs.max_date\n"
        "),\n"
        "cohort_size AS (\n"
        "  SELECT count(*) AS new_users FROM cohort\n"
        "),\n"
        "day_base AS (\n"
        "  SELECT d.n AS day_index,\n"
        "         count(DISTINCT c.player_id) AS observed_users\n"
        "  FROM days d\n"
        "  CROSS JOIN obs\n"
        "  LEFT JOIN cohort c ON c.install_date <= obs.max_date - d.n\n"
        "  GROUP BY d.n\n"
        "),\n"
        "daily_pay AS (\n"
        "  SELECT d.n AS day_index,\n"
        "         count(DISTINCT pay.player_id) AS paying_users,\n"
        "         sum(pay.net_revenue_usd) AS total_revenue,\n"
        "         sum(pay.net_revenue_usd) / nullif(count(DISTINCT pay.player_id), 0) AS avg_revenue_per_payer\n"
        "  FROM days d\n"
        "  CROSS JOIN obs\n"
        "  JOIN cohort c ON c.install_date <= obs.max_date - d.n\n"
        "  LEFT JOIN fact_payments pay ON pay.player_id = c.player_id\n"
        "   AND pay.lifecycle_day = d.n\n"
        "   AND pay.payment_status = 'success'\n"
        "   AND pay.net_revenue_usd > 0\n"
        "  GROUP BY d.n\n"
        ")\n"
        "SELECT d.n AS day_index,\n"
        "       'D' || d.n AS lifecycle_day,\n"
        "       cs.new_users,\n"
        "       db.observed_users,\n"
        "       CASE WHEN db.observed_users > 0 THEN coalesce(dp.paying_users, 0) END AS paying_users,\n"
        "       CASE WHEN db.observed_users > 0 THEN round(coalesce(dp.total_revenue, 0), 2) END AS total_revenue,\n"
        "       CASE WHEN db.observed_users > 0 THEN round(coalesce(dp.paying_users, 0)::numeric / nullif(db.observed_users, 0) * 100, 2) END AS daily_payer_rate_pct,\n"
        "       CASE WHEN db.observed_users > 0 THEN round(dp.avg_revenue_per_payer, 2) END AS avg_revenue_per_payer\n"
        "FROM days d\n"
        "CROSS JOIN cohort_size cs\n"
        "LEFT JOIN day_base db ON db.day_index = d.n\n"
        "LEFT JOIN daily_pay dp ON dp.day_index = d.n\n"
        "ORDER BY d.n;\n"
        "```",
    ),
    (
        "最近一周D0付费用户复购留存 用折线图",
        "如果用户明确问 D0 付费用户后续是否继续付费，使用复购留存：分母固定为 lifecycle_day=0 成功付费用户，D0=100%。"
        "Dn 表示这些 D0 付费用户在 lifecycle_day=n 再次成功付费的比例；它不是新增用户整体付费率。"
        "折线图标题建议写“最近一周 D0 付费用户复购留存”，y 轴名称用“复购留存率”，"
        "配置建议：x=day_index 或 lifecycle_day，y=repeat_payer_retention_pct，series=install_date。\n"
        "```sql\n"
        "WITH obs AS (\n"
        "  SELECT max(event_date) AS max_date FROM fact_events\n"
        "),\n"
        "days(n) AS (VALUES (0),(1),(2),(3),(4),(5),(6)),\n"
        "cohort AS (\n"
        "  SELECT p.player_id, p.install_date\n"
        "  FROM dim_player p CROSS JOIN obs\n"
        "  WHERE p.install_date BETWEEN obs.max_date - 6 AND obs.max_date\n"
        "),\n"
        "d0_payers AS (\n"
        "  SELECT DISTINCT c.install_date, c.player_id\n"
        "  FROM cohort c\n"
        "  JOIN fact_payments pay ON pay.player_id = c.player_id\n"
        "   AND pay.lifecycle_day = 0\n"
        "   AND pay.payment_status = 'success'\n"
        "   AND pay.net_revenue_usd > 0\n"
        "),\n"
        "base AS (\n"
        "  SELECT install_date, count(DISTINCT player_id) AS d0_payers\n"
        "  FROM d0_payers\n"
        "  GROUP BY install_date\n"
        "),\n"
        "repeat_paid AS (\n"
        "  SELECT d0.install_date,\n"
        "         pay.lifecycle_day,\n"
        "         count(DISTINCT d0.player_id) AS repeat_payers\n"
        "  FROM d0_payers d0\n"
        "  JOIN fact_payments pay ON pay.player_id = d0.player_id\n"
        "   AND pay.payment_status = 'success'\n"
        "   AND pay.net_revenue_usd > 0\n"
        "  GROUP BY d0.install_date, pay.lifecycle_day\n"
        "),\n"
        "grid AS (\n"
        "  SELECT b.install_date, d.n AS day_index, 'D' || d.n AS lifecycle_day, b.d0_payers\n"
        "  FROM base b CROSS JOIN days d\n"
        ")\n"
        "SELECT g.install_date,\n"
        "       g.day_index,\n"
        "       g.lifecycle_day,\n"
        "       g.d0_payers,\n"
        "       CASE WHEN g.install_date <= obs.max_date - g.day_index\n"
        "            THEN coalesce(r.repeat_payers, 0) END AS repeat_payers,\n"
        "       CASE WHEN g.install_date <= obs.max_date - g.day_index\n"
        "            THEN round(coalesce(r.repeat_payers, 0)::numeric / nullif(g.d0_payers, 0) * 100, 2) END AS repeat_payer_retention_pct\n"
        "FROM grid g\n"
        "CROSS JOIN obs\n"
        "LEFT JOIN repeat_paid r ON r.install_date = g.install_date AND r.lifecycle_day = g.day_index\n"
        "ORDER BY g.install_date, g.day_index;\n"
        "```",
    ),
    (
        "最近30天新增用户的LTV生命周期曲线",
        "目标 cohort = 最近30天新增；LTV(n) = cohort 截至 lifecycle_day<=n 的累计净收入 / cohort 人数，累计单调不减。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(event_date) AS max_date FROM fact_events),\n"
        "cohort AS (\n"
        "  SELECT p.player_id\n"
        "  FROM dim_player p CROSS JOIN obs\n"
        "  WHERE p.install_date BETWEEN obs.max_date - 29 AND obs.max_date\n"
        "),\n"
        "days(n) AS (VALUES (0),(1),(3),(7),(14),(30)),\n"
        "rev AS (\n"
        "  SELECT d.n,\n"
        "         (SELECT count(*) FROM cohort) AS cohort_size,\n"
        "         coalesce(sum(pay.net_revenue_usd), 0) AS cumulative_revenue\n"
        "  FROM days d\n"
        "  LEFT JOIN fact_payments pay\n"
        "    ON pay.player_id IN (SELECT player_id FROM cohort)\n"
        "   AND pay.lifecycle_day <= d.n\n"
        "   AND pay.payment_status = 'success'\n"
        "   AND pay.net_revenue_usd > 0\n"
        "  GROUP BY d.n\n"
        ")\n"
        "SELECT 'D' || n AS lifecycle_day, n AS day_index, cohort_size,\n"
        "       round(cumulative_revenue, 2) AS cumulative_revenue,\n"
        "       round(cumulative_revenue::numeric / nullif(cohort_size, 0), 4) AS cumulative_ltv\n"
        "FROM rev ORDER BY n;\n"
        "```",
    ),
    (
        "预测最近7天新增用户的LTV",
        "目标 cohort = 最近7天已经发生的新增用户，不是未来新增用户。"
        "先计算目标 cohort 已成熟生命周期天数的实际累计 LTV，再用历史成熟 cohort 的累计 LTV 曲线做基准外推未成熟天数。"
        "actual_ltv 表示已观测值，benchmark_ltv 表示历史成熟基准，predicted_ltv 表示预测值。\n"
        "```sql\n"
        "WITH obs AS (\n"
        "  SELECT max(event_date) AS max_date FROM fact_events\n"
        "),\n"
        "days(n) AS (VALUES (0),(1),(3),(7),(14),(30)),\n"
        "target_cohort AS (\n"
        "  SELECT p.player_id, p.install_date\n"
        "  FROM dim_player p CROSS JOIN obs\n"
        "  WHERE p.install_date BETWEEN obs.max_date - 6 AND obs.max_date\n"
        "),\n"
        "target_size AS (\n"
        "  SELECT count(*)::int AS target_users FROM target_cohort\n"
        "),\n"
        "target_actual AS (\n"
        "  SELECT d.n AS lifecycle_day,\n"
        "         count(DISTINCT tc.player_id) FILTER (WHERE tc.install_date <= obs.max_date - d.n) AS observed_users,\n"
        "         coalesce(sum(pay.net_revenue_usd) FILTER (\n"
        "           WHERE tc.install_date <= obs.max_date - d.n\n"
        "             AND pay.lifecycle_day <= d.n\n"
        "         ), 0) AS cumulative_revenue\n"
        "  FROM days d\n"
        "  CROSS JOIN obs\n"
        "  CROSS JOIN target_cohort tc\n"
        "  LEFT JOIN fact_payments pay\n"
        "    ON pay.player_id = tc.player_id\n"
        "   AND pay.payment_status = 'success'\n"
        "   AND pay.net_revenue_usd > 0\n"
        "  GROUP BY d.n\n"
        "),\n"
        "benchmark_cohort AS (\n"
        "  SELECT p.player_id\n"
        "  FROM dim_player p CROSS JOIN obs\n"
        "  WHERE p.install_date BETWEEN obs.max_date - 59 AND obs.max_date - 30\n"
        "),\n"
        "benchmark_ltv AS (\n"
        "  SELECT d.n AS lifecycle_day,\n"
        "         count(DISTINCT bc.player_id) AS benchmark_users,\n"
        "         round(coalesce(sum(pay.net_revenue_usd), 0)::numeric / nullif(count(DISTINCT bc.player_id), 0), 4) AS benchmark_ltv\n"
        "  FROM days d\n"
        "  CROSS JOIN benchmark_cohort bc\n"
        "  LEFT JOIN fact_payments pay\n"
        "    ON pay.player_id = bc.player_id\n"
        "   AND pay.payment_status = 'success'\n"
        "   AND pay.net_revenue_usd > 0\n"
        "   AND pay.lifecycle_day <= d.n\n"
        "  GROUP BY d.n\n"
        "),\n"
        "curve AS (\n"
        "  SELECT ta.lifecycle_day,\n"
        "         ts.target_users,\n"
        "         ta.observed_users,\n"
        "         round(ta.cumulative_revenue::numeric / nullif(ta.observed_users, 0), 4) AS actual_ltv,\n"
        "         bl.benchmark_users,\n"
        "         bl.benchmark_ltv\n"
        "  FROM target_actual ta\n"
        "  CROSS JOIN target_size ts\n"
        "  LEFT JOIN benchmark_ltv bl ON bl.lifecycle_day = ta.lifecycle_day\n"
        "),\n"
        "anchor AS (\n"
        "  SELECT lifecycle_day AS anchor_day,\n"
        "         actual_ltv AS anchor_actual_ltv,\n"
        "         benchmark_ltv AS anchor_benchmark_ltv\n"
        "  FROM curve\n"
        "  WHERE actual_ltv IS NOT NULL\n"
        "    AND benchmark_ltv > 0\n"
        "    AND observed_users >= greatest(10, ceil(target_users * 0.2)::int)\n"
        "  ORDER BY lifecycle_day DESC\n"
        "  LIMIT 1\n"
        ")\n"
        "SELECT 'D' || c.lifecycle_day AS lifecycle_day,\n"
        "       c.lifecycle_day AS day_index,\n"
        "       c.target_users AS sample_size,\n"
        "       c.observed_users,\n"
        "       c.actual_ltv,\n"
        "       c.benchmark_ltv,\n"
        "       CASE\n"
        "         WHEN c.actual_ltv IS NOT NULL THEN c.actual_ltv\n"
        "         WHEN a.anchor_benchmark_ltv > 0 THEN round(a.anchor_actual_ltv * c.benchmark_ltv / a.anchor_benchmark_ltv, 4)\n"
        "       END AS predicted_ltv,\n"
        "       CASE\n"
        "         WHEN c.actual_ltv IS NOT NULL THEN 'actual_observed'\n"
        "         WHEN a.anchor_day IS NOT NULL THEN 'anchored_to_D' || a.anchor_day || '_history_curve'\n"
        "         ELSE 'insufficient_anchor'\n"
        "       END AS forecast_basis,\n"
        "       CASE\n"
        "         WHEN c.actual_ltv IS NOT NULL AND c.observed_users >= c.target_users * 0.8 THEN 'high'\n"
        "         WHEN a.anchor_day IS NOT NULL AND c.benchmark_users >= 100 THEN 'medium'\n"
        "         ELSE 'low'\n"
        "       END AS confidence\n"
        "FROM curve c\n"
        "LEFT JOIN anchor a ON TRUE\n"
        "ORDER BY c.lifecycle_day;\n"
        "```",
    ),
    (
        "用漏斗图从多个维度展示用户流失情况",
        "漏斗主图只展示单一路径；多维度流失拆解另用维度表格/柱图展示。"
        "下面示例以最近30天新增用户为 cohort，使用登录后的新手教程和首付成功路径，避免把安装/注册/登录这种天然 100% 的埋点当作真实流失。\n"
        "```sql\n"
        "WITH obs AS (\n"
        "  SELECT max(event_date) AS max_date FROM fact_events\n"
        "),\n"
        "cohort AS (\n"
        "  SELECT p.player_id, p.channel, p.device_tier, p.register_server_id\n"
        "  FROM dim_player p CROSS JOIN obs\n"
        "  WHERE p.install_date BETWEEN obs.max_date - 29 AND obs.max_date\n"
        "),\n"
        "player_level AS (\n"
        "  SELECT c.player_id,\n"
        "         bool_or(e.event_name = 'login') AS did_login,\n"
        "         bool_or(e.event_name = 'tutorial_step' AND (e.attributes->>'step')::int >= 3) AS did_tutorial_3,\n"
        "         bool_or(e.event_name = 'tutorial_step' AND (e.attributes->>'step')::int >= 7) AS did_tutorial_7,\n"
        "         bool_or(e.event_name = 'tutorial_step' AND (e.attributes->>'step')::int >= 12) AS did_tutorial_12,\n"
        "         bool_or(pay.player_id IS NOT NULL) AS did_first_pay\n"
        "  FROM cohort c\n"
        "  LEFT JOIN fact_events e ON e.player_id = c.player_id\n"
        "  LEFT JOIN fact_payments pay\n"
        "    ON pay.player_id = c.player_id\n"
        "   AND pay.payment_status = 'success'\n"
        "   AND pay.net_revenue_usd > 0\n"
        "   AND (pay.is_first_pay = true OR pay.pay_sequence = 1)\n"
        "  GROUP BY c.player_id\n"
        "),\n"
        "steps AS (\n"
        "  SELECT 1 AS step_order, '登录' AS step_name, count(*) FILTER (WHERE did_login) AS users FROM player_level\n"
        "  UNION ALL SELECT 2, '完成教程第3步', count(*) FILTER (WHERE did_login AND did_tutorial_3) FROM player_level\n"
        "  UNION ALL SELECT 3, '完成教程第7步', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7) FROM player_level\n"
        "  UNION ALL SELECT 4, '完成教程第12步', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12) FROM player_level\n"
        "  UNION ALL SELECT 5, '首次成功付费', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12 AND did_first_pay) FROM player_level\n"
        "),\n"
        "base AS (\n"
        "  SELECT step_order, step_name, users,\n"
        "         first_value(users) OVER (ORDER BY step_order) AS start_users,\n"
        "         lag(users) OVER (ORDER BY step_order) AS prev_users\n"
        "  FROM steps\n"
        ")\n"
        "SELECT step_order, step_name, users,\n"
        "       round(users::numeric / nullif(start_users, 0) * 100, 2) AS conversion_from_start_pct,\n"
        "       round(users::numeric / nullif(prev_users, 0) * 100, 2) AS conversion_from_prev_pct\n"
        "FROM base\n"
        "ORDER BY step_order;\n"
        "```\n"
        "```sql\n"
        "WITH obs AS (\n"
        "  SELECT max(event_date) AS max_date FROM fact_events\n"
        "),\n"
        "cohort AS (\n"
        "  SELECT p.player_id, p.channel, p.device_tier, p.register_server_id\n"
        "  FROM dim_player p CROSS JOIN obs\n"
        "  WHERE p.install_date BETWEEN obs.max_date - 29 AND obs.max_date\n"
        "),\n"
        "player_level AS (\n"
        "  SELECT c.player_id, c.channel, c.device_tier, c.register_server_id,\n"
        "         bool_or(e.event_name = 'login') AS did_login,\n"
        "         bool_or(e.event_name = 'tutorial_step' AND (e.attributes->>'step')::int >= 3) AS did_tutorial_3,\n"
        "         bool_or(e.event_name = 'tutorial_step' AND (e.attributes->>'step')::int >= 7) AS did_tutorial_7,\n"
        "         bool_or(e.event_name = 'tutorial_step' AND (e.attributes->>'step')::int >= 12) AS did_tutorial_12,\n"
        "         bool_or(pay.player_id IS NOT NULL) AS did_first_pay\n"
        "  FROM cohort c\n"
        "  LEFT JOIN fact_events e ON e.player_id = c.player_id\n"
        "  LEFT JOIN fact_payments pay\n"
        "    ON pay.player_id = c.player_id\n"
        "   AND pay.payment_status = 'success'\n"
        "   AND (pay.is_first_pay = true OR pay.pay_sequence = 1)\n"
        "  GROUP BY c.player_id, c.channel, c.device_tier, c.register_server_id\n"
        ")\n"
        "SELECT channel,\n"
        "       count(*) AS total_users,\n"
        "       count(*) FILTER (WHERE did_login) AS login_users,\n"
        "       count(*) FILTER (WHERE did_login AND did_tutorial_3) AS tutorial_3_users,\n"
        "       count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7) AS tutorial_7_users,\n"
        "       count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12) AS tutorial_12_users,\n"
        "       count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12 AND did_first_pay) AS first_pay_users,\n"
        "       round(count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12 AND did_first_pay)::numeric / nullif(count(*), 0) * 100, 2) AS first_pay_conversion_pct\n"
        "FROM player_level\n"
        "GROUP BY channel\n"
        "ORDER BY first_pay_conversion_pct DESC NULLS LAST;\n"
        "```",
    ),
    (
        "分析用户再引导任务每个节点的流失情况",
        "任务节点漏斗必须按玩家去重统计，不要统计事件条数。"
        "先构造 player_level，一行一个 player_id，标记是否登录、是否完成关键教程步骤、是否完成战斗/建筑/科技/首付；"
        "再按“完成当前步骤且完成所有前序步骤”的条件 count(*)。"
        "如果某一步人数大于前一步、完成率超过 100% 或流失率为负数，说明 SQL 错了，要重写。\n"
        "```sql\n"
        "WITH obs AS (\n"
        "  SELECT max(event_date) AS max_date FROM fact_events\n"
        "),\n"
        "cohort AS (\n"
        "  SELECT p.player_id, p.channel, p.device_tier, p.register_server_id\n"
        "  FROM dim_player p CROSS JOIN obs\n"
        "  WHERE p.install_date BETWEEN obs.max_date - 29 AND obs.max_date\n"
        "),\n"
        "event_flags AS (\n"
        "  SELECT c.player_id,\n"
        "         bool_or(e.event_name = 'login') AS did_login,\n"
        "         bool_or(e.event_name = 'tutorial_step' AND (e.attributes->>'step')::int >= 3) AS did_tutorial_3,\n"
        "         bool_or(e.event_name = 'tutorial_step' AND (e.attributes->>'step')::int >= 7) AS did_tutorial_7,\n"
        "         bool_or(e.event_name = 'tutorial_step' AND (e.attributes->>'step')::int >= 12) AS did_tutorial_12\n"
        "  FROM cohort c\n"
        "  LEFT JOIN fact_events e ON e.player_id = c.player_id\n"
        "  GROUP BY c.player_id\n"
        "),\n"
        "battle_flags AS (\n"
        "  SELECT DISTINCT c.player_id, true AS did_first_battle\n"
        "  FROM cohort c JOIN fact_battles b ON b.player_id = c.player_id\n"
        "),\n"
        "building_flags AS (\n"
        "  SELECT DISTINCT c.player_id, true AS did_building_upgrade\n"
        "  FROM cohort c JOIN fact_building_upgrades bu ON bu.player_id = c.player_id\n"
        "),\n"
        "research_flags AS (\n"
        "  SELECT DISTINCT c.player_id, true AS did_research\n"
        "  FROM cohort c JOIN fact_research r ON r.player_id = c.player_id\n"
        "),\n"
        "pay_flags AS (\n"
        "  SELECT DISTINCT c.player_id, true AS did_first_pay\n"
        "  FROM cohort c\n"
        "  JOIN fact_payments pay ON pay.player_id = c.player_id\n"
        "  WHERE pay.payment_status = 'success'\n"
        "    AND pay.net_revenue_usd > 0\n"
        "    AND (pay.is_first_pay = true OR pay.pay_sequence = 1)\n"
        "),\n"
        "player_level AS (\n"
        "  SELECT c.player_id,\n"
        "         coalesce(ef.did_login, false) AS did_login,\n"
        "         coalesce(ef.did_tutorial_3, false) AS did_tutorial_3,\n"
        "         coalesce(ef.did_tutorial_7, false) AS did_tutorial_7,\n"
        "         coalesce(ef.did_tutorial_12, false) AS did_tutorial_12,\n"
        "         coalesce(bf.did_first_battle, false) AS did_first_battle,\n"
        "         coalesce(buf.did_building_upgrade, false) AS did_building_upgrade,\n"
        "         coalesce(rf.did_research, false) AS did_research,\n"
        "         coalesce(pf.did_first_pay, false) AS did_first_pay\n"
        "  FROM cohort c\n"
        "  LEFT JOIN event_flags ef ON ef.player_id = c.player_id\n"
        "  LEFT JOIN battle_flags bf ON bf.player_id = c.player_id\n"
        "  LEFT JOIN building_flags buf ON buf.player_id = c.player_id\n"
        "  LEFT JOIN research_flags rf ON rf.player_id = c.player_id\n"
        "  LEFT JOIN pay_flags pf ON pf.player_id = c.player_id\n"
        "),\n"
        "steps AS (\n"
        "  SELECT 1 AS step_order, '登录' AS step_name, count(*) FILTER (WHERE did_login) AS users FROM player_level\n"
        "  UNION ALL SELECT 2, '完成教程第3步', count(*) FILTER (WHERE did_login AND did_tutorial_3) FROM player_level\n"
        "  UNION ALL SELECT 3, '完成教程第7步', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7) FROM player_level\n"
        "  UNION ALL SELECT 4, '完成教程第12步', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12) FROM player_level\n"
        "  UNION ALL SELECT 5, '首次战斗', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12 AND did_first_battle) FROM player_level\n"
        "  UNION ALL SELECT 6, '首次建筑升级', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12 AND did_first_battle AND did_building_upgrade) FROM player_level\n"
        "  UNION ALL SELECT 7, '首次科技研究', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12 AND did_first_battle AND did_building_upgrade AND did_research) FROM player_level\n"
        "  UNION ALL SELECT 8, '首次成功付费', count(*) FILTER (WHERE did_login AND did_tutorial_3 AND did_tutorial_7 AND did_tutorial_12 AND did_first_battle AND did_building_upgrade AND did_research AND did_first_pay) FROM player_level\n"
        "),\n"
        "base AS (\n"
        "  SELECT step_order, step_name, users,\n"
        "         first_value(users) OVER (ORDER BY step_order) AS start_users,\n"
        "         lag(users) OVER (ORDER BY step_order) AS prev_users\n"
        "  FROM steps\n"
        ")\n"
        "SELECT step_order,\n"
        "       step_name,\n"
        "       users,\n"
        "       round(users::numeric / nullif(start_users, 0) * 100, 2) AS conversion_from_start_pct,\n"
        "       round(users::numeric / nullif(prev_users, 0) * 100, 2) AS conversion_from_prev_pct,\n"
        "       CASE WHEN prev_users IS NULL THEN NULL ELSE prev_users - users END AS drop_off_users,\n"
        "       CASE WHEN prev_users IS NULL THEN NULL ELSE round((prev_users - users)::numeric / nullif(prev_users, 0) * 100, 2) END AS drop_off_from_prev_pct\n"
        "FROM base\n"
        "ORDER BY step_order;\n"
        "```",
    ),
    (
        "最近30天按付费档位的收入构成",
        "使用 fact_payments.revenue_tier 分组，收入用 net_revenue_usd，只统计成功支付净收入订单。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(event_date) AS max_date FROM fact_events),\n"
        "win AS (SELECT (max_date - 29) AS start_date, max_date FROM obs)\n"
        "SELECT p.revenue_tier,\n"
        "       count(*) AS orders,\n"
        "       count(DISTINCT p.player_id) AS payers,\n"
        "       round(sum(p.net_revenue_usd), 2) AS revenue\n"
        "FROM fact_payments p CROSS JOIN win\n"
        "WHERE p.event_date BETWEEN win.start_date AND win.max_date\n"
        "  AND p.payment_status = 'success'\n"
        "  AND p.net_revenue_usd > 0\n"
        "GROUP BY p.revenue_tier\n"
        "ORDER BY revenue DESC;\n"
        "```",
    ),
    (
        "礼包和商品付费结构分析",
        "商品付费结构默认看成功支付净收入，不要用 amount_usd。"
        "主图可按 product_type 展示 revenue 占比；完整分析应同时返回 orders、payers、revenue、arppu、revenue_share_pct。"
        "饼图只适合展示收入占比，购买人数/ARPPU/复购率建议用表格或柱图。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(event_date) AS max_date FROM fact_events),\n"
        "win AS (SELECT (max_date - 29) AS start_date, max_date FROM obs),\n"
        "pay AS (\n"
        "  SELECT pay.player_id,\n"
        "         pay.order_id,\n"
        "         pay.net_revenue_usd,\n"
        "         dp.product_type,\n"
        "         dp.product_name\n"
        "  FROM fact_payments pay\n"
        "  JOIN dim_product dp ON dp.product_id = pay.product_id\n"
        "  CROSS JOIN win\n"
        "  WHERE pay.event_date BETWEEN win.start_date AND win.max_date\n"
        "    AND pay.payment_status = 'success'\n"
        "    AND pay.net_revenue_usd > 0\n"
        "),\n"
        "by_type AS (\n"
        "  SELECT product_type,\n"
        "         count(*) AS orders,\n"
        "         count(DISTINCT player_id) AS payers,\n"
        "         round(sum(net_revenue_usd), 2) AS revenue,\n"
        "         round(sum(net_revenue_usd) / nullif(count(DISTINCT player_id), 0), 2) AS arppu\n"
        "  FROM pay\n"
        "  GROUP BY product_type\n"
        "),\n"
        "total AS (\n"
        "  SELECT sum(revenue) AS total_revenue FROM by_type\n"
        ")\n"
        "SELECT b.product_type,\n"
        "       b.orders,\n"
        "       b.payers,\n"
        "       b.revenue,\n"
        "       b.arppu,\n"
        "       round(b.revenue / nullif(t.total_revenue, 0) * 100, 2) AS revenue_share_pct\n"
        "FROM by_type b CROSS JOIN total t\n"
        "ORDER BY b.revenue DESC;\n"
        "```",
    ),
    (
        "最近30天各类事件的触发次数和触发人数",
        "事件分析使用 fact_events；事件次数 count(*)，事件人数 count(DISTINCT player_id)。"
        "事件中文名和说明从 dim_event_name 关联，避免只输出英文 event_name。"
        "这不是 DAU，不能替代 fact_sessions 的活跃口径。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(event_date) AS max_date FROM fact_events),\n"
        "win AS (SELECT (max_date - 29) AS start_date, max_date FROM obs)\n"
        "SELECT e.event_category,\n"
        "       e.event_name,\n"
        "       den.event_cn_name,\n"
        "       count(*) AS event_count,\n"
        "       count(DISTINCT e.player_id) AS event_users\n"
        "FROM fact_events e\n"
        "LEFT JOIN dim_event_name den ON den.event_name = e.event_name\n"
        "CROSS JOIN win\n"
        "WHERE e.event_date BETWEEN win.start_date AND win.max_date\n"
        "GROUP BY e.event_category, e.event_name, den.event_cn_name\n"
        "ORDER BY event_count DESC;\n"
        "```",
    ),
    (
        "最近30天按战斗类型分析战斗人数、次数、胜率和兵损",
        "战斗分析使用 fact_battles，一行一场战斗结算。"
        "战斗次数 count(*)，战斗人数 count(DISTINCT player_id)，胜率用 result='win' 的战斗次数 / 总战斗次数；"
        "兵损、伤兵、资源掠夺和体力消耗来自 fact_battles 的结算字段。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(event_date) AS max_date FROM fact_battles),\n"
        "win AS (SELECT (max_date - 29) AS start_date, max_date FROM obs)\n"
        "SELECT b.battle_type,\n"
        "       b.target_type,\n"
        "       count(*) AS battles,\n"
        "       count(DISTINCT b.player_id) AS battle_users,\n"
        "       round(count(*) FILTER (WHERE b.result = 'win')::numeric / nullif(count(*), 0) * 100, 2) AS win_rate_pct,\n"
        "       sum(b.troops_sent) AS troops_sent,\n"
        "       sum(b.troops_lost) AS troops_lost,\n"
        "       sum(b.wounded) AS wounded,\n"
        "       sum(b.resource_looted) AS resource_looted,\n"
        "       sum(b.stamina_spent) AS stamina_spent\n"
        "FROM fact_battles b CROSS JOIN win\n"
        "WHERE b.event_date BETWEEN win.start_date AND win.max_date\n"
        "GROUP BY b.battle_type, b.target_type\n"
        "ORDER BY battles DESC;\n"
        "```",
    ),
    (
        "最近30天资源产出和消耗结构",
        "资源流水使用 fact_resource_transactions。产出和消耗要分开看："
        "gain_amount 统计正向资源，sink_amount 统计消耗绝对值，net_change_amount 才是净变化。"
        "不要只看正负相加后的净值，否则会掩盖产出和消耗规模。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(event_date) AS max_date FROM fact_resource_transactions),\n"
        "win AS (SELECT (max_date - 29) AS start_date, max_date FROM obs),\n"
        "base AS (\n"
        "  SELECT r.resource_type,\n"
        "         r.reason,\n"
        "         coalesce(sum(r.change_amount) FILTER (WHERE r.change_amount > 0), 0) AS gain_amount,\n"
        "         coalesce(abs(sum(r.change_amount) FILTER (WHERE r.change_amount < 0)), 0) AS sink_amount,\n"
        "         sum(r.change_amount) AS net_change_amount,\n"
        "         count(*) AS transactions,\n"
        "         count(DISTINCT r.player_id) AS users\n"
        "  FROM fact_resource_transactions r CROSS JOIN win\n"
        "  WHERE r.event_date BETWEEN win.start_date AND win.max_date\n"
        "  GROUP BY r.resource_type, r.reason\n"
        ")\n"
        "SELECT resource_type, reason, gain_amount, sink_amount, net_change_amount, transactions, users\n"
        "FROM base\n"
        "ORDER BY resource_type, gain_amount + sink_amount DESC;\n"
        "```",
    ),
    (
        "最近30天建筑、科技和练兵的成长消耗对比",
        "建筑、科技、练兵分别来自 fact_building_upgrades、fact_research、fact_army_training。"
        "三张表一行都是一个完成任务，可以 UNION 到统一任务粒度后比较任务数、用户数、战力增长、原始耗时和加速秒数；"
        "不要用 fact_events 的 start/finish 事件数替代任务完成明细。\n"
        "```sql\n"
        "WITH obs AS (\n"
        "  SELECT max(day) AS max_date\n"
        "  FROM (\n"
        "    SELECT max(finish_time::date) AS day FROM fact_building_upgrades\n"
        "    UNION ALL SELECT max(finish_time::date) FROM fact_research\n"
        "    UNION ALL SELECT max(finish_time::date) FROM fact_army_training\n"
        "  ) d\n"
        "),\n"
        "win AS (SELECT (max_date - 29) AS start_date, max_date FROM obs),\n"
        "tasks AS (\n"
        "  SELECT 'building' AS task_type, building_type AS item_type, player_id,\n"
        "         finish_time::date AS finish_date, duration_seconds, speedup_seconds, power_gain\n"
        "  FROM fact_building_upgrades\n"
        "  UNION ALL\n"
        "  SELECT 'research', research_type, player_id,\n"
        "         finish_time::date, duration_seconds, speedup_seconds, power_gain\n"
        "  FROM fact_research\n"
        "  UNION ALL\n"
        "  SELECT 'army_training', troop_type, player_id,\n"
        "         finish_time::date, duration_seconds, speedup_seconds, power_gain\n"
        "  FROM fact_army_training\n"
        ")\n"
        "SELECT t.task_type,\n"
        "       t.item_type,\n"
        "       count(*) AS completed_tasks,\n"
        "       count(DISTINCT t.player_id) AS users,\n"
        "       sum(t.power_gain) AS total_power_gain,\n"
        "       round(avg(t.duration_seconds) / 3600.0, 2) AS avg_duration_hours,\n"
        "       round(avg(t.speedup_seconds) / 3600.0, 2) AS avg_speedup_hours\n"
        "FROM tasks t CROSS JOIN win\n"
        "WHERE t.finish_date BETWEEN win.start_date AND win.max_date\n"
        "GROUP BY t.task_type, t.item_type\n"
        "ORDER BY t.task_type, completed_tasks DESC;\n"
        "```",
    ),
    (
        "最近30天客户端质量问题按设备和版本分布",
        "质量问题来自 fact_events 中 event_category='quality' 或 event_name in ('crash','client_error','network_error')。"
        "问题次数用 count(*)，受影响用户数用 count(DISTINCT player_id)，可按平台、设备、系统版本、网络类型和 app_build 拆分。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(event_date) AS max_date FROM fact_events),\n"
        "win AS (SELECT (max_date - 29) AS start_date, max_date FROM obs)\n"
        "SELECT e.platform,\n"
        "       e.device_tier,\n"
        "       e.device_model,\n"
        "       e.os_version,\n"
        "       e.network_type,\n"
        "       e.app_build,\n"
        "       e.event_name,\n"
        "       count(*) AS issue_events,\n"
        "       count(DISTINCT e.player_id) AS affected_users\n"
        "FROM fact_events e CROSS JOIN win\n"
        "WHERE e.event_date BETWEEN win.start_date AND win.max_date\n"
        "  AND (e.event_category = 'quality' OR e.event_name IN ('crash', 'client_error', 'network_error'))\n"
        "GROUP BY e.platform, e.device_tier, e.device_model, e.os_version, e.network_type, e.app_build, e.event_name\n"
        "ORDER BY issue_events DESC;\n"
        "```",
    ),
]


DATA_SKILLS: list[dict[str, str]] = [
    {
        "slug": "workspace-onboarding-funnel",
        "visibility_scope": "ADMIN_PUBLIC",
        "owner_account": "",
        "name": "SLG Skill：新手引导与早期激活漏斗",
        "description": "用于新手教程、首次战斗、首次建筑/科技、首付等早期激活链路，不把事件次数误当用户漏斗。",
        "prompt": """
<!-- data-skill-source:slg-bi-mock:workspace:onboarding-funnel -->
# SLG Skill：新手引导与早期激活漏斗

适用问题：
- 新用户从安装、登录、新手教程、首次战斗、首次建筑升级、首次科技研究到首次付费的转化。
- 新手教程第 3/7/12 步掉点、早期关键节点流失、不同渠道或设备的新手链路对比。

必须使用的明细表：
- cohort 用 `dim_player.install_date` 锁定新增玩家。
- 教程步骤用 `fact_events` 中 `event_name='tutorial_step'`，步骤号取 `attributes->>'step'`。
- 首战用 `fact_battles`，建筑/科技用 `fact_building_upgrades`、`fact_research`，首付用 `fact_payments`。

SQL 口径：
- 先构造玩家级 `player_level`，一行一个 `player_id`，用 `bool_or` / `exists` 标记每个节点是否完成。
- 漏斗人数必须带前序条件，例如完成第 7 步人数必须同时完成登录、第 3 步和第 7 步。
- 禁止每个步骤独立 `count(distinct player_id)` 后直接 `UNION`，那会导致后序步骤人数大于前序步骤。
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
- 付费用户为成功净收入订单的 `count(distinct player_id)`。
- 首付用户优先用 `is_first_pay=true`，或用玩家最早成功支付日推导。
- ARPU = 净收入 / 指定用户分母；ARPPU = 净收入 / 付费用户数。跨维度汇总时回到收入和人数重新计算，不要平均各组 ARPU。

推荐输出：
- 指标卡：`revenue`, `payers`, `payer_rate_pct`, `arpu`, `arppu`。
- 商品结构：`product_type`, `product_name`, `orders`, `payers`, `revenue`, `revenue_share_pct`, `arppu`。
- 图表：收入趋势用柱/线，付费率用折线或双轴；商品收入占比可用饼图，但人数、订单数、ARPPU 用表格或柱图。

参考 SQL：
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

        term_added = term_updated = 0
        touched_term_parent_ids: set[int] = set()
        for word, synonyms, description in TERMS:
            cur.execute(
                """
                SELECT id FROM terminology
                WHERE pid IS NULL AND word = %s
                  AND tenant_id = %s
                  AND scope = 'TENANT'
                  AND specific_ds = TRUE
                  AND datasource_ids @> jsonb_build_array(%s)
                ORDER BY id LIMIT 1
                """,
                (word, tenant_id, ds_id),
            )
            existing = cur.fetchone()
            if existing:
                parent_id = existing[0]
                cur.execute(
                    """
                    UPDATE terminology
                    SET tenant_id = %s,
                        scope = 'TENANT',
                        description = %s,
                        specific_ds = TRUE,
                        datasource_ids = %s,
                        enabled = TRUE,
                        embedding = NULL
                    WHERE id = %s
                    """,
                    (tenant_id, description, Jsonb([ds_id]), parent_id),
                )
                term_updated += 1
            else:
                cur.execute(
                    """
                    INSERT INTO terminology (tenant_id, scope, pid, create_time, word, description, specific_ds, datasource_ids, enabled, embedding)
                    VALUES (%s, 'TENANT', NULL, %s, %s, %s, TRUE, %s, TRUE, NULL)
                    RETURNING id
                    """,
                    (tenant_id, now, word, description, Jsonb([ds_id])),
                )
                parent_id = cur.fetchone()[0]
                term_added += 1
            touched_term_parent_ids.add(int(parent_id))

            for syn in synonyms:
                syn = syn.strip()
                if not syn:
                    continue
                cur.execute(
                    """
                    SELECT id FROM terminology
                    WHERE pid = %s AND word = %s
                    ORDER BY id LIMIT 1
                    """,
                    (parent_id, syn),
                )
                syn_row = cur.fetchone()
                if syn_row:
                    cur.execute(
                        """
                        UPDATE terminology
                        SET tenant_id = %s,
                            scope = 'TENANT',
                            specific_ds = TRUE,
                            datasource_ids = %s,
                            enabled = TRUE,
                            embedding = NULL
                        WHERE id = %s
                        """,
                        (tenant_id, Jsonb([ds_id]), syn_row[0]),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO terminology (tenant_id, scope, pid, create_time, word, description, specific_ds, datasource_ids, enabled, embedding)
                        VALUES (%s, 'TENANT', %s, %s, %s, NULL, TRUE, %s, TRUE, NULL)
                        """,
                        (tenant_id, parent_id, now, syn, Jsonb([ds_id])),
                    )

        ex_added = ex_updated = 0
        touched_training_ids: set[int] = set()
        for question, answer in EXAMPLES:
            cur.execute(
                "SELECT id FROM data_training WHERE question = %s AND tenant_id = %s AND scope = 'TENANT' AND datasource = %s ORDER BY id LIMIT 1",
                (question, tenant_id, ds_id),
            )
            existing = cur.fetchone()
            if existing:
                training_id = existing[0]
                cur.execute(
                    """
                    UPDATE data_training
                    SET tenant_id = %s, scope = 'TENANT', description = %s, enabled = TRUE, embedding = NULL
                    WHERE id = %s
                    """,
                    (tenant_id, answer, training_id),
                )
                ex_updated += 1
            else:
                cur.execute(
                    """
                    INSERT INTO data_training (tenant_id, scope, datasource, create_time, question, description, enabled, embedding)
                    VALUES (%s, 'TENANT', %s, %s, %s, %s, TRUE, NULL)
                    RETURNING id
                    """,
                    (tenant_id, ds_id, now, question, answer),
                )
                training_id = cur.fetchone()[0]
                ex_added += 1
            touched_training_ids.add(int(training_id))

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
        print(f"术语: 新增 {term_added} 组（含同义词子记录），更新 {term_updated} 组")
        print(f"数据训练: 新增 {ex_added} 条，更新 {ex_updated} 条")
        print(f"数据 Skills: 新增 {skill_added} 条，更新 {skill_updated} 条")
        print(f"本次触达父术语: {len(touched_term_parent_ids)} 组")
        print(f"本次触达数据训练: {len(touched_training_ids)} 条")
        print(f"xiaonan 用户: id={xiaonan_user_id}")
        cur.execute(
            """
            SELECT count(*) FROM terminology
            WHERE specific_ds = TRUE AND datasource_ids @> jsonb_build_array(%s)
            """,
            (ds_id,),
        )
        print("terminology 总记录数:", cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM data_training WHERE datasource = %s", (ds_id,))
        print("data_training 总记录数:", cur.fetchone()[0])
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
