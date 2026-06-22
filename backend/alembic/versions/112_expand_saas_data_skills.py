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
    return f"""{marker}
# {skill_name}

本 Skill 从旧版平台级术语和 SQL 示例抽象整理而来，作为 SaaS 全局通用的数据问答能力边界。它不绑定具体数据源、表名或业务域；生成 SQL 时必须以当前已选数据源、字段元数据、权限和数据源级语义配置为准。

## 来源摘要
{_source_summary(source_terms, source_sql_rows)}

## 使用方式
{rules}
- 如果本 Skill 与当前数据库 Schema、数据权限、SQL 安全规则或用户已选数据源冲突，以当前 SaaS 权限、Schema 和已选数据源为准。
- 如果当前数据源没有配置本 Skill 所需的业务字段、指标公式或维度映射，应说明缺少配置，不能把旧示例中的表名、字段名或业务域当作隐藏规则。
"""


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
