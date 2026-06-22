"""112_expand_saas_data_skills

Revision ID: d4f6a7b8c9e0
Revises: c9d12e7f4a6b
Create Date: 2026-06-22 00:00:00.000000

"""
from __future__ import annotations

from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d4f6a7b8c9e0"
down_revision = "c9d12e7f4a6b"
branch_labels = None
depends_on = None


OLD_SAAS_THEME_MARKER = "<!-- data-skill-source:semantic-theme:saas:"
SAAS_20_MARKER_PREFIX = "<!-- data-skill-source:semantic-theme20:saas:"


SAAS_SKILLS: tuple[dict[str, Any], ...] = (
    {
        "slug": "datasource-context-semantic-priority",
        "title": "数据源上下文与语义优先",
        "description": "约束跨数据源、权限、Schema 与语义配置优先级，防止用用户措辞越权或跨源推断。",
        "term_words": (),
        "sql_keywords": ("数据源", "权限", "跨源", "当前数据源", "已选择"),
        "rules": (
            "生成 SQL 前先确认当前已选数据源、用户权限、可见 Schema、字段元数据和已选择的数据 Skill。",
            "用户提到的数据项目或业务对象如果不在当前授权上下文内，应说明权限或上下文不匹配，要求切换数据源或补充授权。",
            "不要因为旧示例、推荐问题或用户措辞里出现某个业务名，就跨数据源读取 Schema、复用 SQL 或引用其他数据源口径。",
            "如果语义配置没有覆盖业务指标、分母、时间字段或过滤条件，只能生成不依赖该缺失口径的基础探索查询，或请求补充配置。",
        ),
    },
    {
        "slug": "business-date-window",
        "title": "业务日期与观察窗口",
        "description": "统一最近 N 天、自然日、观察截止日、成熟窗口和业务日期字段的选择原则。",
        "term_words": ("预测分析",),
        "sql_keywords": ("最近", "近", "观察", "窗口", "预测"),
        "rules": (
            "“最近 N 天”“近一个月”“截至目前”默认使用当前分析表的最大业务日期作为截止日，而不是系统当前日期。",
            "最近 N 天通常按闭区间 [max_date - N + 1, max_date] 处理；如果用户明确指定自然月、自然周或固定日期，以用户日期为准。",
            "不同事实表可能有不同业务时间字段，必须优先使用字段元数据或数据 Skill 指定的日期字段；缺少配置时先说明不确定性。",
            "涉及留存、生命周期、LTV 或预测时，要区分已成熟窗口、未成熟窗口和未来预测窗口，未成熟结果不要按 0 处理。",
        ),
    },
    {
        "slug": "grain-dedup-preaggregation",
        "title": "明细粒度、去重与预聚合",
        "description": "约束事实表粒度、人数/次数/金额统计、去重粒度和多事实表关联前预聚合。",
        "term_words": ("漏斗分析", "商品付费结构"),
        "sql_keywords": ("人数", "次数", "订单", "触发", "漏斗", "商品"),
        "rules": (
            "先识别每张表的一行代表什么：事件、会话、订单、任务、账户、组织或快照；不要把次数表直接当人数表。",
            "人数、客户数、账号数等主体规模指标优先使用 count(distinct subject_id)；事件数、订单数、任务数才使用 count(*)。",
            "多张事实表关联前，先按主体、日期、订单或业务键预聚合，避免多对多 join 放大收入、次数或用户数。",
            "SQL 输出字段名要体现粒度，例如 users、sessions、orders、events、accounts、revenue，避免只写 count 或 value。",
        ),
    },
    {
        "slug": "rate-percent-metrics",
        "title": "比例指标与百分比输出",
        "description": "覆盖留存率、转化率、付费率、流失率、占比等非累加比例指标的输出和图表规则。",
        "term_words": ("百分比指标", "付费率", "留存率"),
        "sql_keywords": ("率", "占比", "留存", "转化", "付费率"),
        "rules": (
            "比例指标必须先明确分子、分母和统计窗口；同一图表中的分母口径应保持一致。",
            "用于图表 y 轴时返回 0-100 的数值型字段，例如 retention_pct 或 conversion_pct，不要拼接百分号文本。",
            "比例指标不可直接累加；整体比例应使用 sum(numerator) / sum(denominator)，不要对明细百分比做简单平均。",
            "趋势使用折线，维度对比使用柱状或条形；除非只展示构成占比，不要把比例指标放入饼图。",
        ),
    },
    {
        "slug": "new-user-cohort",
        "title": "新增用户与 Cohort 基数",
        "description": "抽象新增用户、注册/安装 cohort、首日基数和 cohort 固定分母的通用规则。",
        "term_words": ("新增用户",),
        "sql_keywords": ("新增用户", "新增", "注册", "cohort"),
        "rules": (
            "新增用户、注册用户、安装用户、开户客户等 cohort 必须以语义配置指定的首次发生日期或主体创建日期为准。",
            "最近 N 天新增表示已发生历史窗口内的 cohort，不是未来新增预测；预测类问题应另走预测 Skill。",
            "按生命周期、留存、转化或 LTV 分析同一 cohort 时，分母固定为该 cohort 的主体数，不能按每个生命周期日重新计算。",
            "如果用户指定某一天或某批新增，SQL 应先锁定 cohort 明细，再派生后续行为、付费或留存指标。",
        ),
    },
    {
        "slug": "active-session-health",
        "title": "活跃、访问与会话健康",
        "description": "覆盖 DAU/WAU/MAU、活跃用户、访问次数、会话时长和人均活跃行为的通用口径。",
        "term_words": ("DAU", "活跃用户分层"),
        "sql_keywords": ("DAU", "日活", "活跃", "会话", "访问"),
        "rules": (
            "DAU/WAU/MAU 本质是窗口内发生有效活跃行为的去重主体数，具体活跃行为以数据源语义配置为准。",
            "不要用任意事件触发人数替代活跃用户；除非 Skill 明确某事件就是活跃事件。",
            "会话次数、访问次数、启动次数、停留时长和活跃人数是不同指标，应分别命名和计算。",
            "人均会话次数、人均时长等均值使用总次数或总时长除以活跃主体数，不要在用户级均值上再简单平均。",
        ),
    },
    {
        "slug": "exact-retention-mature-window",
        "title": "精确日留存与成熟窗口",
        "description": "覆盖 D1/Dn 留存、固定分母、成熟 cohort、未成熟窗口 NULL 处理和留存趋势表达。",
        "term_words": ("次日留存", "留存率"),
        "sql_keywords": ("留存", "次日", "D1", "D7", "6月1号"),
        "rules": (
            "Dn 留存默认是精确日留存：同一 cohort 在 lifecycle_day = n 或第 n 个观察日是否活跃。",
            "分母固定为已成熟 cohort 的主体数；分子是该 cohort 在目标生命周期日发生有效活跃的去重主体数。",
            "未成熟生命周期日返回 NULL 或标注未成熟，不要当作 0；D0 可作为 cohort 基准，不等同于 D1 之后的行为留存。",
            "按生命周期日分组时，不要把当天有行为的人数重新当作分母，否则会得到错误的 100% 留存。",
        ),
    },
    {
        "slug": "churn-return-rolling-retention",
        "title": "流失、回流与滚动留存",
        "description": "区分精确日留存、连续留存、滚动留存、沉默流失和回流用户，防止概念互相替代。",
        "term_words": ("回流用户",),
        "sql_keywords": ("回流", "流失", "沉默", "滚动留存", "连续留存"),
        "rules": (
            "流失或沉默必须先定义连续不活跃阈值，例如连续 N 天无有效活跃；缺少阈值时应请求确认。",
            "回流用户是曾满足沉默或流失阈值后再次活跃的主体，与新增用户、普通留存活跃不同。",
            "未付费用户、未转化用户或某日没有行为的用户不能直接称为流失用户；除非 SQL 已按连续不活跃阈值计算 churned_subjects。",
            "连续留存要求 D1 到 Dn 每天都活跃，通常单调不增；滚动留存要求第 n 天及以后任意一天活跃，也不同于精确日留存。",
            "精确日留存曲线回升不能自动解释为回流，除非 SQL 已逐主体验证沉默阈值后再次活跃。",
        ),
    },
    {
        "slug": "revenue-recognition-net-amount",
        "title": "收入确认、净额与订单状态",
        "description": "覆盖收入/流水、净收入、毛收入、退款、成功订单和金额字段选择的通用规则。",
        "term_words": ("流水", "付费用户", "首付成功"),
        "sql_keywords": ("流水", "收入", "订单", "退款", "成功支付"),
        "rules": (
            "收入类指标必须使用语义配置指定的成功交易状态和有效收入字段；不要把订单标价或失败订单金额当正式收入。",
            "需要区分净收入、毛收入、退款金额、折扣金额和税费；字段未配置时不能自行选择看起来像金额的列作为口径。",
            "收入统计窗口通常按交易成功或业务确认日期归属，而不是订单创建日期；如需改变归属日期必须明确说明。",
            "SQL 字段名应区分 revenue、gross_revenue、refund_amount、net_revenue，避免把不同金额口径混在一起。",
        ),
    },
    {
        "slug": "payer-conversion-rate",
        "title": "付费用户、付费率与转化",
        "description": "覆盖付费用户、首付、付费率、累计付费转化和分母选择的通用规则。",
        "term_words": ("付费用户", "付费率", "首付成功", "累计付费转化"),
        "sql_keywords": ("付费率", "付费用户", "首付", "累计付费", "转化"),
        "rules": (
            "付费用户是统计窗口内发生成功有效付费的去重主体；首付用户必须使用首次成功付费标记或最早成功付费日。",
            "付费率 = 付费用户数 / 指定分母，分母可能是同周期活跃用户、新增 cohort、试用用户或曝光用户，必须先确认。",
            "累计付费转化统计截至生命周期日 n 曾成功付费的主体数 / cohort 人数，应随生命周期日单调不下降。",
            "不要把生命周期日当日付费率、累计付费转化和首日付费用户复购留存混为同一个指标。",
            "不要把按商品、渠道或日期分组后的 paying_subjects 相加当作整体付费用户数；整体付费用户必须在 cohort 或窗口范围内重新 count(distinct subject_id)。",
        ),
    },
    {
        "slug": "arpu-arppu-averages",
        "title": "ARPU、ARPPU 与人均值",
        "description": "覆盖用户人均收入、付费用户人均收入、平均客单价和均值类指标图表表达。",
        "term_words": ("ARPU", "ARPPU"),
        "sql_keywords": ("ARPU", "ARPPU", "人均", "平均"),
        "rules": (
            "ARPU 使用指定收入 / 指定用户分母；默认分母应由数据 Skill 明确，例如活跃用户、注册用户或新增 cohort。",
            "ARPPU 使用指定收入 / 付费用户数，只能在成功有效付费用户分母上计算。",
            "均值类指标不可累加；跨维度汇总时应回到收入总额和人数重新计算，不要对各组均值直接平均。",
            "ARPU、ARPPU、客单价等均值适合柱状对比、趋势折线或表格，不适合饼图，也不要与大额总量共用同轴。",
        ),
    },
    {
        "slug": "ltv-cohort-value",
        "title": "LTV 与 Cohort 价值曲线",
        "description": "覆盖生命周期价值、累计收入、人均价值、单调性校验和 cohort 分母一致性。",
        "term_words": ("LTV",),
        "sql_keywords": ("LTV", "生命周期价值", "长期价值"),
        "rules": (
            "LTV(n) = 同一 cohort 截至生命周期日 n 的累计有效收入 / cohort 人数，必须保持同一 cohort 和同一分母。",
            "累计 LTV 应随生命周期日单调不下降；若结果下降，优先检查分母变化、收入字段或生命周期窗口。",
            "如果展示总收入，应命名为 cumulative_revenue 或 total_revenue，不要把总收入列命名为 LTV。",
            "未成熟生命周期日应返回 NULL、标注未成熟或使用预测 Skill 外推，不能用 0 当作真实成熟 LTV。",
            "回答总营收或总体 LTV 时必须使用 cumulative_revenue 或 total_revenue 字段；不要从分日 rows 手动漏加或跨维度重复加总。",
            "如果 SQL 只返回 daily_revenue 或 daily_paying_subjects，结论只能描述每日节奏，不能描述累计收入、累计 LTV 或总体价值；必须补 cumulative_revenue/ltv 查询。",
        ),
    },
    {
        "slug": "lifecycle-monetization-curves",
        "title": "生命周期付费曲线",
        "description": "区分生命周期日付费率、当日收入、人均收入和累计转化，适用于 cohort 付费表现分析。",
        "term_words": ("生命周期日付费率", "付费留存", "累计付费转化"),
        "sql_keywords": ("生命周期付费", "每日付费", "付费留存", "累计付费"),
        "rules": (
            "生命周期日付费率统计 lifecycle_day = n 当天成功付费主体数 / cohort 人数，曲线可以波动。",
            "生命周期日收入、人均收入、付费率和累计付费转化是不同字段，必须分别输出，不要共用一个指标名。",
            "“后续付费情况”默认至少输出 daily_paying_subjects、daily_revenue、cumulative_paying_subjects、cumulative_revenue、daily_pay_rate_pct、cumulative_pay_conversion_pct 和 ltv。",
            "生命周期趋势 SQL 不能只返回有付费的 lifecycle_day；应补齐观察窗口内的日期序列，让无付费日期以 0 展示，并让累计字段保持不下降。",
            "同一 cohort 的分母固定；成熟但无付费可为 0，未成熟生命周期日应返回 NULL。",
            "图表标题和 y 轴应明确写“生命周期日付费率”“当日收入”或“累计付费转化率”，避免误读为留存。",
        ),
    },
    {
        "slug": "first-pay-repeat-purchase",
        "title": "首付、复购与付费留存",
        "description": "覆盖首次成功付费、D0 付费用户基准、复购留存和重复购买行为。",
        "term_words": ("首付成功", "首日付费用户复购留存", "付费留存"),
        "sql_keywords": ("D0付费", "复购", "首付", "首次付费", "付费留存"),
        "rules": (
            "首付或首购必须基于首次成功有效交易，不应计入失败、取消、退款或测试订单。",
            "D0 付费用户复购留存以首日成功付费用户为固定分母，Dn 表示这些用户在第 n 天再次成功付费的比例。",
            "复购留存不同于新增用户生命周期日付费率，也不同于累计付费转化；用户问题含糊时应先说明选择的口径。",
            "复购次数、复购人数、复购率、复购收入和客单价应拆成独立字段，避免一个 revenue 或 rate 字段承载多义。",
        ),
    },
    {
        "slug": "product-plan-revenue-mix",
        "title": "商品、套餐与方案收入结构",
        "description": "覆盖商品/套餐/订阅方案收入构成、购买人数、订单数、ARPPU 和结构图表选择。",
        "term_words": ("商品付费结构",),
        "sql_keywords": ("商品", "礼包", "套餐", "产品", "收入构成"),
        "rules": (
            "商品、套餐、订阅方案或价格计划分析必须关联语义配置指定的商品/计划维表或枚举字段。",
            "收入结构默认使用成功有效净收入；同时输出订单数、购买人数、收入、ARPPU 和收入占比时要分别命名。",
            "商品/计划维度的购买人数是组内去重，不能跨商品相加得到总体付费用户；如果需要总体付费用户，必须另算 overall_paying_subjects。",
            "饼图只适合展示单一构成指标，例如 revenue_share_pct；若同时比较收入、人数、订单数和均值，优先使用表格或柱图。",
            "如果用户要求商品明细排行，按收入或购买人数排序并限制 Top N，其余可归为 Other，避免图表过载。",
        ),
    },
    {
        "slug": "dimension-breakdown-segmentation",
        "title": "维度拆解与人群分层",
        "description": "覆盖渠道、地区、设备、活动、人群分层、付费分层和维度对比的通用规则。",
        "term_words": ("活跃用户分层",),
        "sql_keywords": ("渠道", "分层", "维度", "对比", "付费档位"),
        "rules": (
            "维度拆解优先使用数据源已有字段元数据和语义分层，不要临时发明阈值或业务分组。",
            "同一问题中要区分主体当前属性、事件发生时属性和订单归属属性；历史行为分析优先使用事实发生时的维度。",
            "按维度比较总量、均值和比例时，应分别计算分子分母，再输出清晰字段名和排序指标。",
            "维度过多时限制 Top N，并说明排序依据；高基数字段适合表格或条形图，不适合饼图。",
        ),
    },
    {
        "slug": "event-behavior-uv-pv",
        "title": "事件行为、触发次数与触发人数",
        "description": "覆盖事件明细、PV/UV、行为人数、事件属性、行为路径和事件类指标边界。",
        "term_words": ("新手教程步骤", "漏斗分析"),
        "sql_keywords": ("事件", "触发", "教程", "行为", "PV", "UV"),
        "rules": (
            "事件次数表示满足条件的事件行数，触发人数表示触发事件的去重主体数，二者不能混用。",
            "事件属性筛选必须基于字段元数据、JSON 属性说明或数据 Skill；未配置属性含义时不要猜枚举值。",
            "行为路径或步骤完成率应先转成主体级状态，再统计每个步骤的人数；不要直接用事件条数计算用户转化。",
            "事件类问题不能自动替代活跃、会话、收入或留存口径，除非语义配置明确事件与指标的映射关系。",
        ),
    },
    {
        "slug": "funnel-path-conversion",
        "title": "漏斗转化与路径流失",
        "description": "覆盖步骤漏斗、前序约束、单调性校验、节点流失率和多维漏斗拆解。",
        "term_words": ("漏斗分析", "新手教程步骤"),
        "sql_keywords": ("漏斗", "流失", "节点", "路径", "转化"),
        "rules": (
            "漏斗必须先确定同一目标 cohort、同一时间窗口和步骤顺序，再构造主体级 player_level/account_level 状态表。",
            "每一步 users 必须是完成当前步骤且完成所有前序步骤的去重主体数，主漏斗人数应单调不增。",
            "输出建议包含 step_order、step_name、users、conversion_from_start_pct、conversion_from_prev_pct 和 dropoff_users。",
            "多维漏斗拆解应在同一主体级状态表上按单个维度分组，不要把多个维度混入一个漏斗图。",
        ),
    },
    {
        "slug": "chart-result-schema",
        "title": "图表选择与结果字段结构",
        "description": "约束趋势、对比、构成、漏斗、指标卡和表格输出字段，提升图表自动映射稳定性。",
        "term_words": ("百分比指标", "混合指标图表"),
        "sql_keywords": ("折线图", "漏斗图", "柱", "图表", "趋势"),
        "rules": (
            "趋势图输出日期或生命周期日作为 x 字段，数值指标作为 y 字段，必要时提供 series 字段。",
            "维度对比输出 dimension、metric_value 和排序字段；构成图输出 category、value、share_pct。",
            "漏斗图输出 step_order、step_name、users；指标卡输出单行清晰命名的核心指标。",
            "SQL 不要把数值格式化为带单位的文本；展示单位、百分号和千分位由图表层处理。",
            "不要把总量、均值和百分比三个量级差异很大的指标全部放在同一个同轴图。",
            "推荐一个总量指标用柱，一个比例指标用右轴折线；均值、人均值和 LTV 可放摘要、表格或第二张图。",
            "若 SQL 同时返回多个量级指标，字段名要能让图表层识别 metric 类型，例如 revenue、payer_rate_pct、arpu。",
            "当用户要求一个问题看多指标时，可以返回同一查询结果并建议拆图，而不是强行把所有字段放入 multi-quota。",
        ),
    },
    {
        "slug": "forecast-benchmark-confidence",
        "title": "预测、成熟基准与置信度",
        "description": "覆盖预测目标、已观测窗口、成熟历史基准、外推结果、样本量和置信度表达。",
        "term_words": ("预测分析", "LTV"),
        "sql_keywords": ("预测", "预估", "LTV"),
        "rules": (
            "预测前必须明确目标指标、预测对象、已观测窗口、预测周期和可用历史成熟样本。",
            "预测输出应区分 actual_value、benchmark_value、predicted_value、sample_size、forecast_basis 和 confidence。",
            "生命周期预测可用目标 cohort 已成熟观测点作为锚点，结合历史成熟 cohort 曲线外推；样本越少或已观测天数越短，置信度越低。",
            "缺少历史成熟基准、样本量或明确预测口径时，不要编造预测值，应说明数据或配置不足。",
        ),
    },
)


SAAS_SQL_EXAMPLES: dict[str, tuple[str, ...]] = {
    "datasource-context-semantic-priority": (
        """
-- 仅在允许探查当前数据源 schema 时使用；不要跨数据源复用其他库的表字段。
SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
ORDER BY table_schema, table_name, ordinal_position;
""",
    ),
    "business-date-window": (
        """
-- 将 fact_events、event_date、subject_id 替换为当前数据源的事实表、业务日期和主体字段。
WITH bounds AS (
    SELECT MAX(event_date)::date AS max_business_date
    FROM fact_events
),
windowed_events AS (
    SELECT e.*
    FROM fact_events AS e
    CROSS JOIN bounds AS b
    WHERE e.event_date::date BETWEEN b.max_business_date - INTERVAL '29 days'
                                 AND b.max_business_date
)
SELECT
    event_date::date AS business_date,
    COUNT(DISTINCT subject_id) AS active_subjects,
    COUNT(*) AS event_count
FROM windowed_events
GROUP BY 1
ORDER BY 1;
""",
    ),
    "grain-dedup-preaggregation": (
        """
-- 多事实表关联前先按共同粒度预聚合，避免订单、事件、会话互相放大。
WITH orders_by_subject_day AS (
    SELECT
        subject_id,
        paid_at::date AS business_date,
        COUNT(DISTINCT order_id) AS orders,
        SUM(net_amount) AS revenue
    FROM fact_orders
    WHERE order_status = 'success'
    GROUP BY 1, 2
),
events_by_subject_day AS (
    SELECT
        subject_id,
        event_time::date AS business_date,
        COUNT(*) AS events
    FROM fact_events
    GROUP BY 1, 2
)
SELECT
    COALESCE(o.business_date, e.business_date) AS business_date,
    COUNT(DISTINCT COALESCE(o.subject_id, e.subject_id)) AS subjects,
    SUM(COALESCE(o.orders, 0)) AS orders,
    SUM(COALESCE(o.revenue, 0)) AS revenue,
    SUM(COALESCE(e.events, 0)) AS events
FROM orders_by_subject_day AS o
FULL OUTER JOIN events_by_subject_day AS e
    ON e.subject_id = o.subject_id
   AND e.business_date = o.business_date
GROUP BY 1
ORDER BY 1;
""",
    ),
    "rate-percent-metrics": (
        """
-- 比例指标输出 0-100 数值，不拼接百分号；整体比例用分子分母重新计算。
WITH daily AS (
    SELECT
        event_date::date AS business_date,
        COUNT(DISTINCT subject_id) AS denominator_subjects,
        COUNT(DISTINCT CASE WHEN is_converted THEN subject_id END) AS numerator_subjects
    FROM fact_events
    GROUP BY 1
)
SELECT
    business_date,
    numerator_subjects,
    denominator_subjects,
    ROUND(numerator_subjects * 100.0 / NULLIF(denominator_subjects, 0), 2) AS conversion_pct
FROM daily
ORDER BY business_date;
""",
    ),
    "new-user-cohort": (
        """
-- cohort_date 应替换为语义配置指定的首次注册、首次安装、开户或首次出现日期。
WITH cohort AS (
    SELECT
        subject_id,
        MIN(created_at)::date AS cohort_date
    FROM dim_subjects
    GROUP BY 1
),
bounds AS (
    SELECT MAX(cohort_date) AS max_cohort_date
    FROM cohort
)
SELECT
    cohort_date,
    COUNT(*) AS new_subjects
FROM cohort
CROSS JOIN bounds
WHERE cohort_date BETWEEN max_cohort_date - INTERVAL '29 days'
                      AND max_cohort_date
GROUP BY 1
ORDER BY 1;
""",
    ),
    "active-session-health": (
        """
-- 将 session_id、duration_seconds、started_at 替换为当前会话/访问事实表字段。
SELECT
    started_at::date AS business_date,
    COUNT(DISTINCT subject_id) AS active_subjects,
    COUNT(DISTINCT session_id) AS sessions,
    ROUND(SUM(duration_seconds) / NULLIF(COUNT(DISTINCT subject_id), 0), 2) AS avg_duration_seconds_per_subject,
    ROUND(COUNT(DISTINCT session_id) * 1.0 / NULLIF(COUNT(DISTINCT subject_id), 0), 2) AS sessions_per_subject
FROM fact_sessions
WHERE is_valid_session = TRUE
GROUP BY 1
ORDER BY 1;
""",
    ),
    "exact-retention-mature-window": (
        """
-- Dn 精确日留存：固定 cohort 分母；未成熟 cohort 不进入计算。
WITH cohort AS (
    SELECT subject_id, MIN(created_at)::date AS cohort_date
    FROM dim_subjects
    GROUP BY 1
),
activity AS (
    SELECT DISTINCT subject_id, event_time::date AS active_date
    FROM fact_events
    WHERE is_active_event = TRUE
),
bounds AS (
    SELECT MAX(active_date) AS max_active_date
    FROM activity
)
SELECT
    c.cohort_date,
    1 AS lifecycle_day,
    COUNT(DISTINCT c.subject_id) AS cohort_subjects,
    COUNT(DISTINCT a.subject_id) AS retained_subjects,
    ROUND(COUNT(DISTINCT a.subject_id) * 100.0 / NULLIF(COUNT(DISTINCT c.subject_id), 0), 2) AS retention_pct
FROM cohort AS c
CROSS JOIN bounds AS b
LEFT JOIN activity AS a
    ON a.subject_id = c.subject_id
   AND a.active_date = c.cohort_date + 1
WHERE c.cohort_date <= b.max_active_date - 1
GROUP BY 1, 2
ORDER BY 1;
""",
    ),
    "churn-return-rolling-retention": (
        """
-- 回流模板：连续 inactive_days_threshold 天无活跃后再次活跃；阈值需由用户或 Skill 明确。
WITH active_days AS (
    SELECT DISTINCT subject_id, event_time::date AS active_date
    FROM fact_events
    WHERE is_active_event = TRUE
),
sequenced AS (
    SELECT
        subject_id,
        active_date,
        LAG(active_date) OVER (PARTITION BY subject_id ORDER BY active_date) AS previous_active_date
    FROM active_days
),
returns AS (
    SELECT
        subject_id,
        active_date AS return_date,
        previous_active_date
    FROM sequenced
    WHERE previous_active_date IS NOT NULL
      AND active_date > previous_active_date + 7
)
SELECT
    return_date,
    COUNT(DISTINCT subject_id) AS return_subjects
FROM returns
GROUP BY 1
ORDER BY 1;
""",
    ),
    "revenue-recognition-net-amount": (
        """
-- 收入以成功或业务确认状态为准；金额字段需替换为语义配置指定的净收入/毛收入字段。
SELECT
    paid_at::date AS business_date,
    COUNT(DISTINCT order_id) AS successful_orders,
    COUNT(DISTINCT subject_id) AS paying_subjects,
    SUM(net_amount) AS net_revenue,
    SUM(gross_amount) AS gross_revenue,
    SUM(refund_amount) AS refund_amount
FROM fact_orders
WHERE order_status = 'success'
GROUP BY 1
ORDER BY 1;
""",
    ),
    "payer-conversion-rate": (
        """
-- 付费率分母可为活跃、新增、曝光或试用主体；这里以同日活跃主体为例。
WITH active AS (
    SELECT event_time::date AS business_date, subject_id
    FROM fact_events
    WHERE is_active_event = TRUE
    GROUP BY 1, 2
),
payers AS (
    SELECT paid_at::date AS business_date, subject_id
    FROM fact_orders
    WHERE order_status = 'success'
    GROUP BY 1, 2
)
SELECT
    a.business_date,
    COUNT(DISTINCT a.subject_id) AS active_subjects,
    COUNT(DISTINCT p.subject_id) AS paying_subjects,
    ROUND(COUNT(DISTINCT p.subject_id) * 100.0 / NULLIF(COUNT(DISTINCT a.subject_id), 0), 2) AS payer_rate_pct
FROM active AS a
LEFT JOIN payers AS p
    ON p.business_date = a.business_date
   AND p.subject_id = a.subject_id
GROUP BY 1
ORDER BY 1;
""",
    ),
    "arpu-arppu-averages": (
        """
-- ARPU/ARPPU 均从总收入和分母重算，不对已聚合均值再平均。
WITH active AS (
    SELECT event_time::date AS business_date, subject_id
    FROM fact_events
    WHERE is_active_event = TRUE
    GROUP BY 1, 2
),
revenue AS (
    SELECT
        paid_at::date AS business_date,
        subject_id,
        SUM(net_amount) AS revenue
    FROM fact_orders
    WHERE order_status = 'success'
    GROUP BY 1, 2
),
daily AS (
    SELECT
        a.business_date,
        COUNT(DISTINCT a.subject_id) AS active_subjects,
        COUNT(DISTINCT r.subject_id) AS paying_subjects,
        SUM(COALESCE(r.revenue, 0)) AS revenue
    FROM active AS a
    LEFT JOIN revenue AS r
        ON r.business_date = a.business_date
       AND r.subject_id = a.subject_id
    GROUP BY 1
)
SELECT
    business_date,
    revenue,
    active_subjects,
    paying_subjects,
    ROUND(revenue / NULLIF(active_subjects, 0), 4) AS arpu,
    ROUND(revenue / NULLIF(paying_subjects, 0), 4) AS arppu
FROM daily
ORDER BY business_date;
""",
    ),
    "ltv-cohort-value": (
        """
-- LTV(n) = 同一 cohort 截至生命周期日 n 的累计收入 / 固定 cohort 人数。
WITH cohort AS (
    SELECT subject_id, MIN(created_at)::date AS cohort_date
    FROM dim_subjects
    GROUP BY 1
),
cohort_size AS (
    SELECT cohort_date, COUNT(DISTINCT subject_id) AS cohort_subjects
    FROM cohort
    GROUP BY 1
),
revenue_by_day AS (
    SELECT
        c.cohort_date,
        (o.paid_at::date - c.cohort_date)::int AS lifecycle_day,
        SUM(o.net_amount) AS revenue
    FROM cohort AS c
    JOIN fact_orders AS o
        ON o.subject_id = c.subject_id
       AND o.order_status = 'success'
       AND o.paid_at::date >= c.cohort_date
    GROUP BY 1, 2
),
cumulative AS (
    SELECT
        cohort_date,
        lifecycle_day,
        SUM(revenue) OVER (
            PARTITION BY cohort_date
            ORDER BY lifecycle_day
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_revenue
    FROM revenue_by_day
)
SELECT
    c.cohort_date,
    c.lifecycle_day,
    s.cohort_subjects,
    c.cumulative_revenue,
    ROUND(c.cumulative_revenue / NULLIF(s.cohort_subjects, 0), 4) AS ltv
FROM cumulative AS c
JOIN cohort_size AS s USING (cohort_date)
ORDER BY c.cohort_date, c.lifecycle_day;
""",
    ),
    "lifecycle-monetization-curves": (
        """
-- 生命周期日付费率、当日收入、累计付费转化要分字段输出。
WITH cohort AS (
    SELECT subject_id, MIN(created_at)::date AS cohort_date
    FROM dim_subjects
    GROUP BY 1
),
cohort_size AS (
    SELECT cohort_date, COUNT(DISTINCT subject_id) AS cohort_subjects
    FROM cohort
    GROUP BY 1
),
days AS (
    SELECT generate_series(0, 30) AS lifecycle_day
),
cohort_days AS (
    SELECT s.cohort_date, d.lifecycle_day
    FROM cohort_size AS s
    CROSS JOIN days AS d
),
payment_days AS (
    SELECT
        c.cohort_date,
        o.subject_id,
        (o.paid_at::date - c.cohort_date)::int AS lifecycle_day,
        SUM(o.net_amount) AS revenue
    FROM cohort AS c
    JOIN fact_orders AS o
        ON o.subject_id = c.subject_id
       AND o.order_status = 'success'
       AND o.paid_at::date >= c.cohort_date
    GROUP BY 1, 2, 3
),
daily AS (
    SELECT
        cohort_date,
        lifecycle_day,
        COUNT(DISTINCT subject_id) AS paying_subjects,
        SUM(revenue) AS revenue
    FROM payment_days
    GROUP BY 1, 2
),
cumulative AS (
    SELECT
        cd.cohort_date,
        cd.lifecycle_day,
        COUNT(DISTINCT pd.subject_id) AS cumulative_paying_subjects,
        COALESCE(SUM(pd.revenue), 0) AS cumulative_revenue
    FROM cohort_days AS cd
    LEFT JOIN payment_days AS pd
        ON pd.cohort_date = cd.cohort_date
       AND pd.lifecycle_day <= cd.lifecycle_day
    GROUP BY 1, 2
)
SELECT
    c.cohort_date,
    c.lifecycle_day,
    s.cohort_subjects,
    COALESCE(d.paying_subjects, 0) AS daily_paying_subjects,
    COALESCE(d.revenue, 0) AS daily_revenue,
    ROUND(COALESCE(d.paying_subjects, 0) * 100.0 / NULLIF(s.cohort_subjects, 0), 2) AS daily_pay_rate_pct,
    c.cumulative_paying_subjects,
    ROUND(c.cumulative_revenue, 2) AS cumulative_revenue,
    ROUND(c.cumulative_paying_subjects * 100.0 / NULLIF(s.cohort_subjects, 0), 2) AS cumulative_pay_conversion_pct,
    ROUND(c.cumulative_revenue / NULLIF(s.cohort_subjects, 0), 4) AS ltv
FROM cumulative AS c
JOIN cohort_size AS s USING (cohort_date)
LEFT JOIN daily AS d
    ON d.cohort_date = c.cohort_date
   AND d.lifecycle_day = c.lifecycle_day
ORDER BY c.cohort_date, c.lifecycle_day;
""",
    ),
    "first-pay-repeat-purchase": (
        """
-- 首付 cohort 的复购留存：分母固定为首次成功付费主体。
WITH first_pay AS (
    SELECT
        subject_id,
        MIN(paid_at)::date AS first_pay_date
    FROM fact_orders
    WHERE order_status = 'success'
    GROUP BY 1
),
repeat_pay AS (
    SELECT
        f.subject_id,
        f.first_pay_date,
        (o.paid_at::date - f.first_pay_date)::int AS lifecycle_day
    FROM first_pay AS f
    JOIN fact_orders AS o
        ON o.subject_id = f.subject_id
       AND o.order_status = 'success'
       AND o.paid_at::date > f.first_pay_date
),
cohort_size AS (
    SELECT first_pay_date, COUNT(DISTINCT subject_id) AS first_payers
    FROM first_pay
    GROUP BY 1
)
SELECT
    r.first_pay_date,
    r.lifecycle_day,
    s.first_payers,
    COUNT(DISTINCT r.subject_id) AS repeat_payers,
    ROUND(COUNT(DISTINCT r.subject_id) * 100.0 / NULLIF(s.first_payers, 0), 2) AS repeat_purchase_pct
FROM repeat_pay AS r
JOIN cohort_size AS s USING (first_pay_date)
GROUP BY 1, 2, 3
ORDER BY 1, 2;
""",
    ),
    "product-plan-revenue-mix": (
        """
-- 商品/套餐/计划结构：收入、订单、购买人数和占比分开输出。
WITH plan_revenue AS (
    SELECT
        COALESCE(p.plan_name, o.plan_id::text) AS plan_name,
        COUNT(DISTINCT o.order_id) AS orders,
        COUNT(DISTINCT o.subject_id) AS paying_subjects,
        SUM(o.net_amount) AS revenue
    FROM fact_orders AS o
    LEFT JOIN dim_product_plan AS p
        ON p.plan_id = o.plan_id
    WHERE o.order_status = 'success'
    GROUP BY 1
)
SELECT
    plan_name,
    orders,
    paying_subjects,
    revenue,
    ROUND(revenue * 100.0 / NULLIF(SUM(revenue) OVER (), 0), 2) AS revenue_share_pct,
    ROUND(revenue / NULLIF(paying_subjects, 0), 4) AS arppu
FROM plan_revenue
ORDER BY revenue DESC
LIMIT 20;
""",
    ),
    "dimension-breakdown-segmentation": (
        """
-- 维度拆解需使用当前数据源已有维度字段；不要临时发明分层阈值。
-- 将 :start_date 和 :end_date 替换为用户指定日期窗口；若用户未指定，按当前数据源业务日期窗口确定。
WITH subject_metric AS (
    SELECT
        e.subject_id,
        COUNT(*) AS events,
        COUNT(DISTINCT e.event_time::date) AS active_days
    FROM fact_events AS e
    WHERE e.event_time::date BETWEEN :start_date AND :end_date
    GROUP BY 1
),
subject_revenue AS (
    SELECT subject_id, SUM(net_amount) AS revenue
    FROM fact_orders
    WHERE order_status = 'success'
    GROUP BY 1
)
SELECT
    COALESCE(d.segment_name, 'unknown') AS segment_name,
    COUNT(DISTINCT m.subject_id) AS subjects,
    SUM(m.events) AS events,
    SUM(m.active_days) AS active_days,
    SUM(COALESCE(r.revenue, 0)) AS revenue,
    ROUND(SUM(COALESCE(r.revenue, 0)) / NULLIF(COUNT(DISTINCT m.subject_id), 0), 4) AS revenue_per_subject
FROM subject_metric AS m
LEFT JOIN subject_revenue AS r USING (subject_id)
LEFT JOIN dim_subjects AS d USING (subject_id)
GROUP BY 1
ORDER BY revenue DESC
LIMIT 20;
""",
    ),
    "event-behavior-uv-pv": (
        """
-- PV/次数用事件行数；UV/触发人数用主体去重数。
SELECT
    event_time::date AS business_date,
    event_name,
    COUNT(*) AS event_count,
    COUNT(DISTINCT subject_id) AS event_subjects
FROM fact_events
WHERE event_name IN ('target_event_a', 'target_event_b')
GROUP BY 1, 2
ORDER BY 1, 2;
""",
    ),
    "funnel-path-conversion": (
        """
-- 漏斗先转主体级步骤状态；后续步骤必须满足前序步骤已完成。
WITH step_flags AS (
    SELECT
        subject_id,
        MIN(CASE WHEN event_name = 'step_1' THEN event_time END) AS step_1_time,
        MIN(CASE WHEN event_name = 'step_2' THEN event_time END) AS step_2_time,
        MIN(CASE WHEN event_name = 'step_3' THEN event_time END) AS step_3_time
    FROM fact_events
    WHERE event_name IN ('step_1', 'step_2', 'step_3')
    GROUP BY 1
),
funnel AS (
    SELECT 1 AS step_order, 'step_1' AS step_name, COUNT(DISTINCT subject_id) AS users
    FROM step_flags
    WHERE step_1_time IS NOT NULL
    UNION ALL
    SELECT 2, 'step_2', COUNT(DISTINCT subject_id)
    FROM step_flags
    WHERE step_1_time IS NOT NULL
      AND step_2_time IS NOT NULL
      AND step_2_time >= step_1_time
    UNION ALL
    SELECT 3, 'step_3', COUNT(DISTINCT subject_id)
    FROM step_flags
    WHERE step_1_time IS NOT NULL
      AND step_2_time IS NOT NULL
      AND step_3_time IS NOT NULL
      AND step_2_time >= step_1_time
      AND step_3_time >= step_2_time
)
SELECT
    step_order,
    step_name,
    users,
    ROUND(users * 100.0 / NULLIF(MAX(CASE WHEN step_order = 1 THEN users END) OVER (), 0), 2) AS conversion_from_start_pct,
    ROUND(users * 100.0 / NULLIF(LAG(users) OVER (ORDER BY step_order), 0), 2) AS conversion_from_prev_pct,
    LAG(users) OVER (ORDER BY step_order) - users AS dropoff_users
FROM funnel
ORDER BY step_order;
""",
    ),
    "chart-result-schema": (
        """
-- 趋势图：日期/生命周期日 + 数值指标 + 可选 series。
SELECT business_date AS x_date, metric_name AS series, metric_value
FROM report_ready_metric_series
ORDER BY x_date, series;

-- 构成图：分类 + 数值 + 占比。
SELECT category_name AS category, metric_value AS value, share_pct
FROM report_ready_category_mix
ORDER BY value DESC;

-- 指标卡：单行、清晰字段名、数值类型。
SELECT
    SUM(revenue) AS revenue,
    COUNT(DISTINCT subject_id) AS active_subjects,
    ROUND(SUM(revenue) / NULLIF(COUNT(DISTINCT subject_id), 0), 4) AS arpu
FROM report_ready_subject_metric;
""",
    ),
    "forecast-benchmark-confidence": (
        """
-- 预测输出要区分实际值、成熟历史基准、预测值、样本量和置信度。
WITH actual AS (
    SELECT
        business_date,
        SUM(metric_value) AS actual_value,
        COUNT(DISTINCT subject_id) AS sample_size
    FROM fact_metric_observations
    GROUP BY 1
),
benchmark AS (
    SELECT
        lifecycle_day,
        AVG(metric_value) AS benchmark_value
    FROM mature_history_metric
    GROUP BY 1
),
forecast AS (
    SELECT
        business_date,
        lifecycle_day,
        predicted_value,
        confidence
    FROM external_forecast_results
)
SELECT
    f.business_date,
    a.actual_value,
    b.benchmark_value,
    f.predicted_value,
    COALESCE(a.sample_size, 0) AS sample_size,
    f.confidence
FROM forecast AS f
LEFT JOIN actual AS a USING (business_date)
LEFT JOIN benchmark AS b USING (lifecycle_day)
ORDER BY f.business_date;
""",
    ),
}


def _bind():
    return op.get_bind()


def _inspector():
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_columns(table_name: str, column_names: tuple[str, ...]) -> bool:
    return all(_has_column(table_name, column_name) for column_name in column_names)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _fetch_platform_terms() -> list[dict[str, Any]]:
    if not _has_columns("terminology", ("id", "scope", "pid", "word", "enabled")):
        return []
    rows = _bind().execute(
        sa.text(
            """
            SELECT
                t.id,
                btrim(t.word) AS word,
                COALESCE(
                    string_agg(btrim(child.word), ', ' ORDER BY child.word)
                        FILTER (
                            WHERE child.id IS NOT NULL
                              AND NULLIF(btrim(child.word), '') IS NOT NULL
                        ),
                    ''
                ) AS synonyms
            FROM terminology AS t
            LEFT JOIN terminology AS child
                ON child.pid = t.id
               AND COALESCE(child.enabled, TRUE) = TRUE
            WHERE t.pid IS NULL
              AND COALESCE(t.enabled, TRUE) = TRUE
              AND COALESCE(t.scope, 'TENANT') = 'PLATFORM'
              AND NULLIF(btrim(t.word), '') IS NOT NULL
            GROUP BY t.id
            ORDER BY t.id
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _fetch_platform_sql_rows() -> list[dict[str, Any]]:
    if not _has_columns("data_training", ("id", "scope", "question", "description", "enabled")):
        return []
    rows = _bind().execute(
        sa.text(
            """
            SELECT id, btrim(question) AS question, btrim(COALESCE(description, '')) AS description
            FROM data_training
            WHERE COALESCE(enabled, TRUE) = TRUE
              AND COALESCE(scope, 'TENANT') = 'PLATFORM'
              AND NULLIF(btrim(question), '') IS NOT NULL
            ORDER BY id
            """
        )
    ).mappings().all()
    result = []
    seen_questions: set[str] = set()
    for row in rows:
        question = str(row["question"] or "").strip()
        source_text = f"{question}\n{row.get('description') or ''}"
        if not question or question in seen_questions:
            continue
        if _contains_any(source_text, ("SLG BI Mock 2", "Season War", "crystal")):
            continue
        seen_questions.add(question)
        result.append(dict(row))
    return result


def _source_terms(theme: dict[str, Any], terms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wanted = set(str(item) for item in theme.get("term_words", ()))
    return [term for term in terms if str(term.get("word") or "") in wanted]


def _source_sql_rows(theme: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keywords = tuple(str(item) for item in theme.get("sql_keywords", ()))
    if not keywords:
        return []
    return [
        row
        for row in rows
        if _contains_any(f"{row.get('question') or ''}\n{row.get('description') or ''}", keywords)
    ][:8]


def _source_summary(source_terms: list[dict[str, Any]], source_sql_rows: list[dict[str, Any]]) -> str:
    term_names = "、".join(str(term.get("word") or "") for term in source_terms if term.get("word"))
    sql_questions = "；".join(str(row.get("question") or "") for row in source_sql_rows if row.get("question"))
    lines = []
    if term_names:
        lines.append(f"- 参考旧术语：{term_names}")
    if sql_questions:
        lines.append(f"- 参考旧 SQL 问法：{sql_questions}")
    if not lines:
        lines.append("- 由旧版平台语义资产抽象补足，用于通用 SaaS 数据问答边界。")
    return "\n".join(lines)


def _render_prompt(
        marker: str,
        skill_name: str,
        theme: dict[str, Any],
        source_terms: list[dict[str, Any]],
        source_sql_rows: list[dict[str, Any]],
) -> str:
    rules = "\n".join(f"- {item}" for item in theme["rules"])
    sql_examples = tuple(SAAS_SQL_EXAMPLES.get(str(theme["slug"]), ()))
    sql_section = ""
    if sql_examples:
        rendered_examples = "\n\n".join(
            f"```sql\n{example.strip()}\n```"
            for example in sql_examples
            if example.strip()
        )
        sql_section = f"""

## 参考 SQL 模板
以下 SQL 只表达通用查询结构，表名、字段名、状态值、日期字段和布尔条件都是占位示例。生成真实 SQL 时必须替换为当前已选数据源中已授权、已配置的实际 Schema 与语义字段；如果当前数据源缺少对应配置，应说明缺口而不是照抄模板。

{rendered_examples}
"""
    return f"""{marker}
# {skill_name}

本 Skill 从旧版平台级术语和 SQL 示例抽象整理而来，作为 SaaS 全局通用的数据问答能力边界。它不绑定具体数据源、表名或业务域；生成 SQL 时必须以当前已选数据源、字段元数据、权限和数据源级语义配置为准。

## 来源摘要
{_source_summary(source_terms, source_sql_rows)}

## 使用方式
{rules}
- 如果本 Skill 与当前数据库 Schema、数据权限、SQL 安全规则或用户已选数据源冲突，以当前 SaaS 权限、Schema 和已选数据源为准。
- 如果当前数据源没有配置本 Skill 所需的业务字段、指标公式或维度映射，应说明缺少配置，不能把旧示例中的表名、字段名或业务域当作隐藏规则。
{sql_section}"""


def _upsert_skill(
        marker: str,
        name: str,
        description: str,
        prompt: str,
) -> None:
    bind = _bind()
    update_stmt = sa.text(
        """
        UPDATE custom_prompt
        SET tenant_id = 1,
            name = :name,
            description = :description,
            target_scope = 'ALL',
            active = TRUE,
            ai_model_id = NULL,
            create_by = NULL,
            visibility_scope = 'PLATFORM_PUBLIC',
            prompt = :prompt,
            specific_ds = FALSE,
            datasource_ids = :datasource_ids
        WHERE type = 'DATA_SKILL'
          AND position(:marker in COALESCE(prompt, '')) > 0
        """
    ).bindparams(sa.bindparam("datasource_ids", type_=postgresql.JSONB))
    result = bind.execute(
        update_stmt,
        {
            "marker": marker,
            "name": name[:255],
            "description": description,
            "prompt": prompt.strip(),
            "datasource_ids": [],
        },
    )
    if result.rowcount:
        return

    insert_stmt = sa.text(
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
        VALUES (
            1,
            'DATA_SKILL',
            NOW(),
            :name,
            :description,
            'ALL',
            TRUE,
            NULL,
            NULL,
            'PLATFORM_PUBLIC',
            :prompt,
            FALSE,
            :datasource_ids
        )
        """
    ).bindparams(sa.bindparam("datasource_ids", type_=postgresql.JSONB))
    bind.execute(
        insert_stmt,
        {
            "name": name[:255],
            "description": description,
            "prompt": prompt.strip(),
            "datasource_ids": [],
        },
    )


def _disable_old_saas_theme_skills() -> None:
    if not _has_columns("custom_prompt", ("type", "visibility_scope", "prompt", "active")):
        return
    _bind().execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET active = FALSE
            WHERE type = 'DATA_SKILL'
              AND visibility_scope = 'PLATFORM_PUBLIC'
              AND position(:old_marker in COALESCE(prompt, '')) > 0
            """
        ),
        {"old_marker": OLD_SAAS_THEME_MARKER},
    )


def _create_saas_20_skills() -> None:
    if not _has_columns(
        "custom_prompt",
        (
            "tenant_id",
            "type",
            "create_time",
            "name",
            "description",
            "target_scope",
            "active",
            "ai_model_id",
            "create_by",
            "visibility_scope",
            "prompt",
            "specific_ds",
            "datasource_ids",
        ),
    ):
        return

    terms = _fetch_platform_terms()
    sql_rows = _fetch_platform_sql_rows()
    for theme in SAAS_SKILLS:
        marker = f"{SAAS_20_MARKER_PREFIX}{theme['slug']} -->"
        name = f"SaaS 数据 Skill：{theme['title']}"
        prompt = _render_prompt(
            marker=marker,
            skill_name=name,
            theme=theme,
            source_terms=_source_terms(theme, terms),
            source_sql_rows=_source_sql_rows(theme, sql_rows),
        )
        _upsert_skill(
            marker=marker,
            name=name,
            description=str(theme["description"]),
            prompt=prompt,
        )


def upgrade() -> None:
    _disable_old_saas_theme_skills()
    _create_saas_20_skills()


def downgrade() -> None:
    if not _has_columns("custom_prompt", ("type", "visibility_scope", "prompt", "active")):
        return
    bind = _bind()
    bind.execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET active = FALSE
            WHERE type = 'DATA_SKILL'
              AND visibility_scope = 'PLATFORM_PUBLIC'
              AND position(:new_marker in COALESCE(prompt, '')) > 0
            """
        ),
        {"new_marker": SAAS_20_MARKER_PREFIX},
    )
    bind.execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET active = TRUE
            WHERE type = 'DATA_SKILL'
              AND visibility_scope = 'PLATFORM_PUBLIC'
              AND position(:old_marker in COALESCE(prompt, '')) > 0
            """
        ),
        {"old_marker": OLD_SAAS_THEME_MARKER},
    )
