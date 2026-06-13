import json
import re
import traceback
from datetime import datetime
from typing import Any, Literal

import orjson
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlmodel import select

from apps.ai_model.model_factory import LLMFactory, get_default_config
from apps.data_training.curd.data_training import get_training_template
from apps.datasource.crud.datasource import get_datasource_list, get_table_schema, get_tables_sample_data
from apps.datasource.crud.permission import get_row_permission_filters, is_normal_user
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import exec_sql, get_sqlglot_dialect
from apps.template.filter.generator import get_permissions_template
from apps.terminology.curd.terminology import get_terminology_template
from apps.system.schemas.permission import SqlbotPermission, require_permissions
from common.core.deps import CurrentUser, SessionDep
from common.utils.utils import extract_nested_json
import sqlglot
from sqlglot import exp

router = APIRouter(tags=["analysis_assistant"], prefix="/analysis-assistant")


class AnalysisAssistantMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(default="")


class AnalysisAssistantRequest(BaseModel):
    messages: list[AnalysisAssistantMessage] = Field(default_factory=list)
    context: str | None = None
    datasource_id: int | None = None


SYSTEM_PROMPT = """你是 SQLBot 内置的综合分析助手，一个独立于“智能问数”的业务分析 Agent。

你的职责：
1. 将用户的自然语言问题转成业务分析框架。
2. 判断需要召回哪些数据，并生成只读 SQL。
3. 基于召回数据做图表解释、异常归因、结论提炼和改进建议。
4. 你可以复用系统的数据源能力，但不要复用“智能问数”的对话状态和提示词。

回答要求：
- 默认使用简体中文。
- 先说明你如何理解用户的问题，再拆解分析路径。
- 所有数字结论必须来自查询结果；没有数据支撑时明确说明不确定。
- 每个图表/数据块都要给一句业务总结。
- 最终答案要包含结论和可执行建议。"""

INITIAL_OUTLINE_PROMPT = """请先基于用户问题，输出“用户意图理解 + 分析框架”。

要求：
- 这是给业务用户看的第一段回复，必须自然、可信、像分析师在解释接下来要怎么做。
- 不要提 SQL、schema、表结构、技术实现、数据库执行等技术细节。
- 不要编造具体数据结果。
- 如果用户说“最近/近 N 天新增用户”，目标对象是已经发生的最近 N 天新增 cohort，不要改写成“未来 N 天新注册用户”；只有用户明确说“未来 N 天新增”时才按未来新增用户理解。
- 先用一段话说明你理解用户想分析什么，以及你会从哪些业务角度分析。
- 然后用 4 到 6 条编号步骤说明后续分析路径。
- 默认使用简体中文。
"""

CHART_TYPES = {
    "table",
    "bar",
    "column",
    "line",
    "pie",
    "metric",
    "funnel",
    "heatmap",
    "scatter",
    "sankey",
    "treemap",
}
MAX_ANALYSIS_QUERIES = 4
MAX_SQL_ROWS = 200
MAX_FORECAST_QUERIES = 4


PLAN_PROMPT = """请基于用户问题、页面上下文和数据库 schema，生成综合分析计划。

你必须只输出一个合法 JSON 对象，不要输出 Markdown，不要输出额外解释。

JSON 格式：
{
  "intro": "用第一人称说明你如何理解用户问题。例如：用户问的问题是新增用户流水，我锁定最近一个月新增用户收入，这是一个综合问题，需要从多个角度分析。",
  "steps": ["分析步骤1", "分析步骤2"],
  "queries": [
    {
      "id": "q1",
      "title": "图表标题",
      "purpose": "为什么要查这组数据",
      "sql": "只读 SQL，必须是 PostgreSQL 语法，最多返回 200 行",
      "chart_type": "line|column|bar|pie|metric|funnel|heatmap|scatter|sankey|treemap|table",
      "x": "结果集中作为维度或时间轴的字段别名",
      "y": "结果集中作为指标的字段别名",
      "series": "可选，结果集中作为分组系列的字段别名"
    }
  ]
}

约束：
- queries 数量 2 到 4 个，除非问题确实只需要 1 个查询。
- SQL 只能 SELECT 或 WITH，不允许 INSERT/UPDATE/DELETE/DDL。
- 不要查询不存在于 schema 的表或字段。
- 所有输出字段必须使用英文小写别名，便于图表绑定。
- ORDER BY、GROUP BY、HAVING 中引用的字段必须来自当前查询可见字段；ORDER BY 使用的别名必须在最终 SELECT 列表中真实输出。
- 用户问“收入/流水/金额/付费收入/revenue”时，图表 y 指标必须优先使用 revenue、amount、gmv、pay_amount 等收入金额字段，不要用新增用户数或活跃用户数替代。
- 如果用户提到“最近一个月/近期”，优先以相关事实表里的最大日期为基准，而不是系统当前日期。
- 如果用户明确给出“最近 7 天/近 7 日/最近 N 天”等时间范围，SQL、标题和分析口径必须严格使用这个范围，不要擅自扩大成 30 天或最近一个月。
- 如果问题是归因类，至少覆盖趋势、结构拆解、关键分组/渠道/产品/服务器等角度中的两个。
- 图表类型应尽量可视化：核心单值指标用 metric，趋势用 line，结构/分布/占比用 bar/pie/treemap，转化路径用 funnel，留存 cohort 或二维分布用 heatmap，二维关系用 scatter，流向/路径/资源转移用 sankey；只有无法确定维度和指标时才使用 table。
- 如果用户要求“漏斗/转化路径/流失分析”，必须使用同一目标 cohort、同一时间窗口、按用户递进完成口径计算：每一步人数必须是完成当前步骤且已完成所有前序步骤的 distinct player_id，不能用 count(*) 事件次数，不能把 quest_complete、login 等可重复事件独立计数后直接拼成漏斗。
- 漏斗图只展示单一路径，字段必须包含 step_order、step_name、users，可附带 conversion_from_start_pct、conversion_from_prev_pct；多维度流失请另起 bar/column/table 查询展示各渠道、设备、服务器在关键步骤的转化率/流失率，不要把多个维度混在同一个 funnel 图里。
- 多维度漏斗拆解必须先按 player_id 生成一行一人的步骤完成状态，再按 channel/device_tier/server 等维度汇总；禁止 count(distinct step)、count(distinct 状态)、count(distinct 1) 或把步骤字段当作用户数。如果各维度 total_users 全部为 1 且转化率全 100%，这一定是统计口径错误。
- `tutorial_step` 是新手步骤明细事件，不能把“发生过任意 tutorial_step”解释为“完成新手教程”。分析新手步骤/教程完成/教程流失时，必须读取 attributes->>'step'，用关键里程碑（如 Step 3/7/12）或实际最大 step 判断完成情况。
- 首付/首充/付费成功转化必须只统计成功支付：使用 fact_payments 时必须过滤 payment_status='success'，再结合 is_first_pay=true 或 pay_sequence=1；不能把 failed/cancelled/refunded 的 is_first_pay 订单算作成功首付。
- 当前 mock 数据中 dim_player/fact_events 只包含已进入游戏的玩家，install/register/login 在 D0 基本天然 100%；如果用户要求安装到登录流失，必须说明这是数据覆盖限制，并改用登录后的新手步骤、教程、首付等应用内漏斗分析。
- 付费转化率、ARPU、ARPPU、平均值、比例、渗透率等非累加指标不能使用 pie，应使用 bar 或 column 做维度对比。
- 分析留存、生命周期、LTV 生命周期阶段时，必须使用成熟 cohort 口径：以 fact_events 或 fact_sessions 的最大日期作为观察截止日，计算 Dn 留存时只纳入 install_date <= 最大日期 - n 天的玩家；分母是这些成熟安装 cohort，分子是在 lifecycle_day = n 有 login/session 行为的玩家。不能把未满观察窗口的 cohort 缺失值解释为 0% 留存。
- 留存 D0 可以是 100% 的注册/安装基准，但 D1/D2/D3 不应默认等于 100%；必须从 session/login 行为中计算。若某个 Dn 样本未成熟或没有足够观察期，要输出“样本未成熟/暂不判断”，不要输出 0% 或“全量流失”。
- 如果用户问“预测/预估/预计/forecast”，必须输出面向目标 cohort 的预测结果，而不只是历史分析。预测新增用户生命周期时，要以最近 N 天或指定日期新增用户为目标 cohort；先使用该 cohort 已经真实成熟的 Dn 留存作为锚点，再用成熟老用户 cohort 的留存衰减曲线外推未成熟周期。已观测天数越多，预测可信度越高；不能只用历史均值硬套。
"""


FORECAST_PLAN_PROMPT = """请基于用户问题、页面上下文、数据库 schema 和样例数据，生成“通用预测分析计划”。

你必须只输出一个合法 JSON 对象，不要输出 Markdown，不要输出额外解释。

JSON 格式：
{
  "intro": "用业务语言说明用户想预测什么指标、目标对象是什么、你会如何使用已观测数据和历史规律进行预测。",
  "forecast_metric": "预测指标，例如 retention、ltv、lifecycle_revenue、revenue、payer_rate、arpu、orders、other",
  "forecast_target": "预测对象，例如某日新增用户 cohort、最近 7 天新增用户、未来 7 天流水等",
  "forecast_method": "简要说明预测方法，必须说明已观测数据、历史基准、成熟样本、置信度如何使用",
  "steps": ["预测步骤1", "预测步骤2"],
  "queries": [
    {
      "id": "q1",
      "title": "图表标题",
      "purpose": "为什么要查这组数据",
      "sql": "只读 SQL，必须是 PostgreSQL 语法，最多返回 200 行",
      "chart_type": "line|column|bar|pie|metric|funnel|heatmap|scatter|sankey|treemap|table",
      "x": "结果集中作为时间、生命周期天数或维度的字段别名",
      "y": "结果集中作为预测值或核心指标的字段别名",
      "series": "可选，结果集中作为分组系列的字段别名"
    }
  ]
}

通用预测原则：
- 你不是固定的留存预测器；必须根据用户问题识别指标，可能是留存、LTV、生命周期收入、流水、付费率、ARPU、ARPPU、订单数或其它业务指标。
- 如果用户说“最近/近 N 天新增用户”，预测目标是已经发生的最近 N 天新增 cohort 的未来生命周期表现，不要改写成“未来 N 天新注册用户”；只有用户明确说“未来 N 天新增”时才预测未来新增人群。
- SQL 只能 SELECT 或 WITH，不允许 INSERT/UPDATE/DELETE/DDL，不要创建表、视图或持久化聚合。
- 不要查询不存在于 schema 的表或字段，所有输出字段使用英文小写别名。
- 预测必须尽量基于明细事实表在查询时计算，不要假设存在 agg/kpi/snapshot 表。
- 用户问收入、LTV、生命周期收入时，优先从支付明细事实表计算，例如净收入/金额字段；LTV 必须按 cohort 累计收入 / cohort 用户数计算成人均生命周期价值，不能把分组总收入直接命名为 LTV；如果需要展示总收入，字段名必须明确使用 total_revenue、cumulative_revenue 等。
- LTV 主预测图必须优先输出生命周期曲线：字段应包含 lifecycle_day/day_index、actual_ltv、benchmark_ltv、predicted_ltv 中的至少两个。目标 cohort 当前观测图如果按日期或渠道展示，y 轴必须是 actual_ltv/actual_arpu 这类人均值，总收入只能作为辅助字段。
- 历史成熟 LTV 曲线必须使用同一批 mature cohort 和同一个分母计算各生命周期天数的累计收入；累计 LTV 必须随 lifecycle_day 单调不下降。若出现 D30 < D7、D30 < D6 或增长倍率 < 1（在锚点收入大于 0 时），说明 SQL 口径错误，必须重写查询，不能解释成真实业务现象。
- D30/D7、D30/Dn 这类增长倍率应该基于累计 LTV 计算，而不是总收入，也不能混用不同 cohort 的分母。
- 用户问留存时，使用 session/login 活跃事实计算 Dn 留存，不要把未满观察窗口的缺失当成 0%。
- 如果是 cohort 预测：先确定目标 cohort（指定日期、最近 N 天新增用户或用户指定的人群），再计算该 cohort 已经成熟的真实观测点；未成熟周期用历史成熟 cohort 的曲线、倍率或分组基准外推。
- 如果目标 cohort 已观测到 D3、D7、D15 等锚点，必须用最近且已成熟的锚点校准未来预测；已观测天数越多，预测可信度越高。
- 小样本分组预测不能被极端值直接带偏，应在 SQL 或总结中体现向历史基准收缩/低置信度提示。
- 使用倍率外推时，如果某个渠道/设备/产品分组的历史倍率为空或分母为 0，必须回退到整体成熟 cohort 的倍率或同类上级分组基准；不要把预测值静默等同于当前实测值，除非明确输出“无法外推”并给出原因。
- 对收入、LTV、ARPU 等金额预测，如果目标 cohort 的早期收入为 0 或样本很小，应使用平滑锚点，例如“目标早期收入 + 历史基准先验”后再外推；不能因为早期暂未付费就预测未来长期收入一定为 0。
- 查询结果中如果包含 confidence/confidence_level，取值必须与样本量、已观测天数和历史基准可用性一致；不要出现字段为 High 但总结又说 Low 的矛盾。
- 如果是未来自然日趋势预测：用事实表最大日期作为观察截止日，基于近期趋势、同周期历史和结构变化外推，输出预测窗口和置信度。
- 查询结果中尽量包含 sample_size、actual_value、predicted_value、benchmark_value、forecast_basis、confidence 等字段；如果字段命名和业务不匹配，可用同义字段，但必须让图表和总结能区分实测与预测。
- 折线图必须至少有两个时间点或生命周期天数；单个倍率、单个基准值、单行结果不要使用 line，应使用 table、metric 或 bar。
- 趋势/生命周期曲线用 line；核心单值指标用 metric；分组对比用 bar/column；占比结构且指标可累加时可用 pie，层级/贡献结构可用 treemap；转化路径用 funnel；留存 cohort 或二维分布用 heatmap；二维关系用 scatter；流向/路径/资源转移用 sankey。
- 付费转化率、ARPU、ARPPU、平均值、比例、渗透率等非累加指标不能使用 pie。
- queries 数量 2 到 4 个：至少包含一个主预测曲线/预测表；如果用户需要归因或结构拆解，再包含渠道、设备、服务器、产品等维度。
"""


SQL_REPAIR_PROMPT = """你是 PostgreSQL 查询修正器。请根据执行错误、原始 SQL 和 schema 修正 SQL。

你必须只输出一个合法 JSON 对象，不要输出 Markdown，不要输出额外解释。

JSON 格式：
{
  "sql": "修正后的只读 SQL"
}

修正规则：
- SQL 只能 SELECT 或 WITH，不允许 INSERT/UPDATE/DELETE/DDL。
- 不要查询不存在于 schema 的表或字段。
- 保持原分析目的和时间范围，不要扩大或缩小口径。
- ORDER BY 使用的字段或别名必须在最终 SELECT 中存在；如果排序字段是计算值，要在 SELECT 中输出同名别名，或改用实际存在的输出别名。
- 输出字段使用英文小写别名，便于图表绑定。
- 修正漏斗/转化路径 SQL 时，必须使用同一目标 cohort、同一时间窗口、按步骤递进完成口径计算：每一步人数是完成当前步骤且完成所有前序步骤的 distinct player_id。不能用 count(*) 事件次数，不能把可重复事件独立计数后拼漏斗。
- 漏斗结果必须包含 step_order、step_name、users，并按 step_order 排序；users 必须单调不增。如果多维度拆解，请输出维度 + 各关键步骤人数/转化率/流失率，用 bar/table，不要混成一个多系列 funnel。
- 修正多维漏斗拆解时，先构建 player_level CTE：每个 player_id 一行，包含 channel/device_tier/server 和各关键步骤最早完成时间或布尔状态；最终按维度 count(*) / count(*) filter(...) 汇总。禁止 count(distinct step)、count(distinct status)、count(distinct 1)。
- 修正新手教程/新手步骤 SQL 时，`tutorial_step` 必须结合 attributes->>'step' 判断具体步骤；不能把任意 tutorial_step 事件当作教程完成。教程完成应使用实际最大步骤或关键里程碑步骤。
- 修正首付/首充/付费成功 SQL 时，如果使用 fact_payments，必须过滤 payment_status='success'，再统计 is_first_pay=true 或 pay_sequence=1 的玩家；不能把 failed/cancelled/refunded 订单计入成功首付。
- 如果 install/register/login 都是 100%，需要判断是否因为数据源只记录已激活玩家；这种情况下应改用登录后的新手步骤漏斗，而不是声称底层数据必须整体修复后才能分析。
- 修正 LTV/生命周期收入 SQL 时，LTV 必须是累计收入 / cohort 用户数；同一条累计 LTV 曲线必须使用同一批 cohort 和同一个分母，且累计值必须随 lifecycle_day/day_index 单调不下降。
- 如果出现 D30 < D7、D30 < D6、增长倍率小于 1 或累计收入倒退，必须重写为同 cohort 的累计口径，不能把单日收入误命名为 LTV。
- 修正留存/生命周期 SQL 时，必须使用成熟 cohort：计算 Dn 时分母只包含 install_date <= 最大观察日期 - n 天的玩家，分子是 lifecycle_day = n 的 login/session 活跃玩家；未满观察窗口不能算作 0%。
"""


SUMMARY_PROMPT = """你是业务数据分析师。请根据用户问题和查询结果，总结这个数据块。

要求：
- 简体中文。
- 2 到 4 句话。
- 必须引用查询结果里能支撑的现象。
- 不要编造查询结果之外的数字。
- 如果是留存/生命周期分析，必须区分“真实 0%”和“样本未满观察期导致没有数据”；不要把未成熟 cohort 的缺失解释为用户全部流失。
- 如果是预测分析，必须说明预测指标、目标对象、已观测数据/历史基准、预测值和置信度；如果查询结果包含 forecast_basis、confidence、benchmark_value 等字段，要用业务语言解释这些字段代表的依据。
- 如果是 LTV 或生命周期收入，累计 LTV/累计收入不应随生命周期天数下降；如果查询结果出现 D30 小于 D7/D6、增长倍率小于 1 等异常，必须说明这是口径或数据计算异常，不能把它解释为真实的累计收入下降。
- 如果是漏斗分析，必须说明目标 cohort、漏斗步骤、最大流失环节和各关键步骤转化率；如果 install/register/login 为 100%，应说明数据源可能只覆盖已激活玩家，并继续分析登录后的新手/付费漏斗。
"""


FINAL_PROMPT = """你是业务数据分析师。请基于多个数据块的总结和它们附带的真实查询数据 rows，回答用户最初的问题。

输出结构：
1. 先给最终判断。
2. 再给关键依据。
3. 最后给 3 条以内改进建议。

要求简洁、可执行，不要编造没有数据支撑的信息。
所有具体数字（金额、人数、比率、预测值等）必须直接来自数据块的 rows 字段；如果 rows 里没有某个数字，就不要给出该数字，而要说明数据未覆盖。
如果回答留存/生命周期问题，必须说明观察窗口和 mature cohort 口径；当数据不足以支持 D7/D14/D30 判断时，明确说样本未成熟，而不是说留存为 0%。
如果用户问预测/预估，最终判断必须先给预测结果，再解释已观测锚点、历史成熟曲线依据和预测可信度；不能只输出历史复盘。
"""


def _to_langchain_messages(request: AnalysisAssistantRequest) -> list[BaseMessage]:
    messages: list[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
    if request.context:
        messages.append(HumanMessage(content=f"当前页面上下文：\n{request.context}"))

    for item in request.messages[-12:]:
        content = item.content.strip()
        if not content:
            continue
        if item.role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages


def _chunk_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or content)
    return str(content)


async def _create_llm():
    config = await get_default_config()
    additional_params = dict(config.additional_params or {})
    extra_body = dict(additional_params.get("extra_body") or {})
    extra_body["enable_thinking"] = False
    additional_params["extra_body"] = extra_body
    # 综合分析助手需要稳定可复现的输出：强制低温度采样，避免同一问题每次召回口径漂移。
    additional_params["temperature"] = 0
    additional_params["top_p"] = 1
    config = config.model_copy(update={"additional_params": additional_params})
    return LLMFactory.create_llm(config).llm


def _sse(payload: dict[str, Any]) -> str:
    return "data:" + orjson.dumps(payload).decode() + "\n\n"


def _trace(content: str, block_id: str | None = None) -> str:
    payload: dict[str, Any] = {"type": "trace", "content": content}
    if block_id:
        payload["block_id"] = block_id
    return _sse(payload)


def _llm_text(llm, messages: list[BaseMessage]) -> str:
    response = llm.invoke(messages)
    return _chunk_text(getattr(response, "content", response)).strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    json_str = extract_nested_json(text)
    if not json_str:
        raise ValueError("模型没有返回合法 JSON")
    data = orjson.loads(json_str)
    if not isinstance(data, dict):
        raise ValueError("模型返回的 JSON 不是对象")
    return data


def _normalise_sql(sql: str) -> str:
    sql = (sql or "").strip()
    sql = re.sub(r"^```(?:sql)?", "", sql, flags=re.IGNORECASE).strip()
    sql = re.sub(r"```$", "", sql).strip()
    while sql.endswith(";"):
        sql = sql[:-1].strip()
    if not re.match(r"^(select|with)\b", sql, flags=re.IGNORECASE):
        raise ValueError("综合分析助手只允许执行 SELECT/WITH 查询")
    if not re.search(r"\blimit\s+\d+\b", sql, flags=re.IGNORECASE):
        sql = f"select * from ({sql}) as analysis_query_limit limit {MAX_SQL_ROWS}"
    return sql


def _get_datasource(
    session: SessionDep, current_user: CurrentUser, datasource_id: int | None
) -> CoreDatasource:
    if datasource_id:
        oid = current_user.oid if current_user.oid is not None else 1
        datasource = session.exec(
            select(CoreDatasource).where(CoreDatasource.oid == oid, CoreDatasource.id == datasource_id)
        ).first()
        if not datasource:
            raise RuntimeError("当前用户无权访问该数据源，或数据源不存在")
        return datasource

    datasource_list = get_datasource_list(session=session, user=current_user)
    if not datasource_list:
        raise RuntimeError("当前工作空间没有可用数据源")
    if len(datasource_list) > 1:
        raise RuntimeError("当前工作空间有多个数据源，请先选择本次综合分析要使用的数据源")
    datasource = datasource_list[0]
    return datasource


def _extract_tables_from_sql(sql: str, ds_type: str | None = None) -> set[str]:
    tables: set[str] = set()
    dialect = get_sqlglot_dialect(ds_type)
    try:
        statements = sqlglot.parse(sql, dialect=dialect)
        for stmt in statements:
            if not stmt:
                continue
            cte_names = {cte.alias_or_name for cte in stmt.find_all(exp.CTE) if cte.alias_or_name}
            for table in stmt.find_all(exp.Table):
                if table.name and table.name not in cte_names:
                    tables.add(table.name)
    except Exception:
        pass
    return tables


def _validate_sql_tables(sql: str, datasource: CoreDatasource, allowed_tables: list[str]) -> list[str]:
    actual_tables = _extract_tables_from_sql(sql, datasource.type)
    if not actual_tables:
        raise ValueError("SQL 解析失败，无法确认查询表范围")
    unauthorized_tables = actual_tables - set(allowed_tables)
    if unauthorized_tables:
        raise ValueError(f"SQL 包含无权限表：{', '.join(sorted(unauthorized_tables))}")
    return sorted(actual_tables)


def _apply_row_permissions(
    llm,
    session: SessionDep,
    current_user: CurrentUser,
    datasource: CoreDatasource,
    sql: str,
    tables: list[str],
) -> str:
    if not is_normal_user(current_user):
        return sql
    filters = get_row_permission_filters(
        session=session,
        current_user=current_user,
        ds=datasource,
        tables=tables,
    )
    if not filters:
        return sql

    template = get_permissions_template()
    engine = datasource.type_name or datasource.type
    messages = [
        SystemMessage(
            content=template["system"].format(
                lang="zh-CN",
                engine=engine,
                sqlbot_name="SQLBot",
            )
        ),
        HumanMessage(
            content=template["user"].format(
                sql=sql,
                filter=json.dumps(filters, ensure_ascii=False),
            )
        ),
    ]
    text = _llm_text(llm, messages)
    try:
        data = _extract_json_object(text)
    except Exception:
        data = {"success": True, "sql": text}
    if data.get("success") is False:
        raise ValueError(str(data.get("message") or "行权限过滤条件应用失败"))
    return _normalise_sql(str(data.get("sql") or sql))


def _prepare_sql_for_execution(
    llm,
    session: SessionDep,
    current_user: CurrentUser,
    datasource: CoreDatasource,
    raw_sql: str,
    allowed_tables: list[str],
) -> str:
    sql = _normalise_sql(raw_sql)
    tables = _validate_sql_tables(sql, datasource, allowed_tables)
    sql = _apply_row_permissions(llm, session, current_user, datasource, sql, tables)
    _validate_sql_tables(sql, datasource, allowed_tables)
    return sql


def _collect_metric_knowledge(
    session: SessionDep, oid: int, datasource_id: int | None, question: str
) -> str:
    """Reuse the project's existing semantic layer (术语 terminology + 数据训练 SQL 示例)
    so the assistant shares the SAME metric definitions as 智能问数, instead of letting
    the LLM re-invent 口径 every time."""
    parts: list[str] = []
    try:
        terminology_template, _terms = get_terminology_template(session, question, oid, datasource_id)
        if terminology_template and terminology_template.strip():
            parts.append(terminology_template.strip())
    except Exception:
        traceback.print_exc()
    try:
        training_template, _examples = get_training_template(session, question, oid, datasource_id)
        if training_template and training_template.strip():
            parts.append(training_template.strip())
    except Exception:
        traceback.print_exc()
    return "\n\n".join(parts)


def _knowledge_block(knowledge: str) -> str:
    if not knowledge or not knowledge.strip():
        return ""
    return (
        "统一业务口径（以下是本工作空间已配置的术语定义/同义词与标准 SQL 示例，"
        "是权威口径。生成 SQL 时必须优先遵循其中的指标定义、字段选择和计算算法；"
        "当它与你的默认理解冲突时，一律以此为准）：\n"
        f"{knowledge[:12000]}\n\n"
    )


def _profile_result_as_text(title: str, result: dict[str, Any], limit: int = 80) -> str:
    rows = result.get("data") or []
    if not rows:
        return ""
    return f"{title}：{orjson.dumps(rows[:limit]).decode()}"


def _collect_date_bounds(datasource: CoreDatasource, schema: str) -> str:
    """Read the real MIN/MAX of every date/time column so the model grounds
    "最近 N 天 / 观察截止日" on actual data instead of the system clock."""
    table_blocks = re.findall(r"# Table:\s*([^\n,]+)[^\n]*\n\[\n(.*?)\n\]", schema, flags=re.DOTALL)
    lines: list[str] = []
    table_count = 0
    for raw_table, body in table_blocks:
        if table_count >= 8:
            break
        table_name = raw_table.strip().split(".")[-1].strip()
        if not table_name:
            continue
        date_fields: list[str] = []
        for fname, ftype in re.findall(r"\(([^:()]+):([^,()]+)", body):
            if any(keyword in ftype.strip().lower() for keyword in ("date", "time", "timestamp")):
                date_fields.append(fname.strip())
        date_fields = date_fields[:4]
        if not date_fields:
            continue
        select_parts: list[str] = []
        for index, field in enumerate(date_fields):
            select_parts.append(f'MAX("{field}")::text AS f{index}_max')
            select_parts.append(f'MIN("{field}")::text AS f{index}_min')
        sql = f'SELECT {", ".join(select_parts)} FROM {table_name}'
        try:
            result = exec_sql(datasource, sql, origin_column=False)
            data = result.get("data") or []
            if not data:
                continue
            row = data[0]
            for index, field in enumerate(date_fields):
                max_value = row.get(f"f{index}_max")
                min_value = row.get(f"f{index}_min")
                if max_value is None and min_value is None:
                    continue
                lines.append(f"- {table_name}.{field}: 最早 {min_value}, 最新 {max_value}")
            table_count += 1
        except Exception:
            traceback.print_exc()
    if not lines:
        return ""
    header = (
        "数据时间边界（以下是各表真实存在的日期范围。判断“最近 N 天 / 最近一个月 / 观察截止日”时，"
        "必须以相关事实表的“最新”日期为基准来推算，不要使用系统当前日期）："
    )
    return header + "\n" + "\n".join(lines)


def _get_data_profile(datasource: CoreDatasource, schema: str) -> str:
    lowered = schema.lower()
    parts: list[str] = []
    if "fact_events" in lowered and "event_name" in lowered:
        try:
            result = exec_sql(
                datasource,
                """
                select event_name, count(*) as events, count(distinct player_id) as users
                from fact_events
                group by event_name
                order by events desc
                limit 80
                """,
                origin_column=False,
            )
            text = _profile_result_as_text("fact_events 实际 event_name 枚举", result)
            if text:
                parts.append(text)
        except Exception:
            traceback.print_exc()
        if "attributes" in lowered:
            try:
                result = exec_sql(
                    datasource,
                    """
                    select
                      min((attributes->>'step')::int) as min_step,
                      max((attributes->>'step')::int) as max_step,
                      count(distinct player_id) as users
                    from fact_events
                    where event_name = 'tutorial_step'
                      and attributes ? 'step'
                    """,
                    origin_column=False,
                )
                text = _profile_result_as_text("tutorial_step 的实际 step 范围", result)
                if text:
                    parts.append(text)
            except Exception:
                traceback.print_exc()
            try:
                result = exec_sql(
                    datasource,
                    """
                    select attributes->>'quest_type' as quest_type, count(*) as events, count(distinct player_id) as users
                    from fact_events
                    where event_name = 'quest_complete'
                    group by attributes->>'quest_type'
                    order by events desc
                    """,
                    origin_column=False,
                )
                text = _profile_result_as_text("quest_complete 的实际 quest_type 枚举", result)
                if text:
                    parts.append(text)
            except Exception:
                traceback.print_exc()
    if "fact_payments" in lowered and "payment_status" in lowered:
        try:
            result = exec_sql(
                datasource,
                """
                select payment_status, count(*) as orders, count(distinct player_id) as users
                from fact_payments
                group by payment_status
                order by orders desc
                """,
                origin_column=False,
            )
            text = _profile_result_as_text("fact_payments 实际 payment_status 枚举", result)
            if text:
                parts.append(text)
        except Exception:
            traceback.print_exc()
    date_bounds = _collect_date_bounds(datasource, schema)
    combined = "\n\n".join(part for part in (date_bounds, "\n".join(parts)) if part.strip())
    return combined[:12000]


def _is_forecast_question(question: str) -> bool:
    lowered = question.lower()
    forecast_keywords = (
        "预测",
        "预估",
        "预计",
        "推算",
        "预判",
        "forecast",
        "predict",
        "estimate",
    )
    return any(keyword in lowered for keyword in forecast_keywords)


def _field_label(field: str) -> str:
    return field.replace("_", " ")


def _is_number(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    try:
        float(str(value).replace(",", ""))
        return True
    except Exception:
        return False


def _numeric_fields(fields: list[str], rows: list[dict[str, Any]]) -> list[str]:
    numeric = []
    for field in fields:
        values = [row.get(field) for row in rows if row.get(field) is not None]
        if values and sum(1 for value in values if _is_number(value)) >= max(1, int(len(values) * 0.6)):
            numeric.append(field)
    return numeric


def _match_field(value: str | None, fields: list[str]) -> str | None:
    if not value:
        return None
    lower_map = {field.lower(): field for field in fields}
    return lower_map.get(value.lower())


def _field_matches(field: str | None, keywords: tuple[str, ...]) -> bool:
    if not field:
        return False
    lowered = field.lower()
    return any(keyword in lowered for keyword in keywords)


def _query_metric_text(query: dict[str, Any]) -> str:
    return " ".join(
        str(query.get(key) or "").lower()
        for key in ("title", "purpose", "y", "_user_question")
    )


def _funnel_order_field(fields: list[str]) -> str | None:
    return next(
        (
            field
            for field in fields
            if field.lower() in {"step_order", "step_index", "stage_order", "funnel_order", "order_index"}
        ),
        None,
    )


def _funnel_step_field(query: dict[str, Any], fields: list[str]) -> str | None:
    requested = _match_field(query.get("x"), fields)
    step_names = {
        "step_name",
        "stage_name",
        "funnel_step",
        "funnel_stage",
        "step",
        "stage",
    }
    if requested and (requested.lower() in step_names or _field_matches(requested, ("step", "stage", "funnel"))):
        return requested
    return next(
        (
            field
            for field in fields
            if field.lower() in step_names or _field_matches(field, ("step_name", "stage_name", "funnel_step"))
        ),
        None,
    )


def _requested_metric_field(query: dict[str, Any], numeric: list[str], x_field: str | None) -> str | None:
    text = _query_metric_text(query)
    available = [field for field in numeric if field != x_field]
    metric_groups: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
        (("ltv", "生命周期价值", "生命周期收入", "长期价值"), ("ltv", "arpu", "predicted_value", "actual_value", "benchmark_value")),
        (("流水", "收入", "金额", "付费收入", "支付金额", "revenue", "amount", "gmv"), ("revenue", "amount", "income", "gmv", "pay_amount", "paid_amount")),
        (("转化", "渗透", "付费率", "rate", "conversion"), ("rate", "ratio", "conversion")),
        (("arppu",), ("arppu",)),
        (("arpu",), ("arpu",)),
        (("用户数", "人数", "新增", "注册", "user", "payer"), ("users", "user_count", "payers", "payer_count", "new_users")),
        (("订单", "次数", "count"), ("orders", "order_count", "cnt", "count")),
    ]
    for text_keywords, field_keywords in metric_groups:
        if any(keyword in text for keyword in text_keywords):
            matched = next((field for field in available if _field_matches(field, field_keywords)), None)
            if matched:
                return matched
    return None


def _choose_metric_field(query: dict[str, Any], numeric: list[str], x_field: str | None) -> str | None:
    if not numeric:
        return None

    available = [field for field in numeric if field != x_field]
    requested = _requested_metric_field(query, numeric, x_field)
    if requested:
        return requested
    preferred_revenue = next(
        (
            field
            for field in available
            if _field_matches(field, ("revenue", "amount", "income", "gmv", "pay_amount", "paid_amount"))
        ),
        None,
    )
    if preferred_revenue:
        return preferred_revenue
    return available[0] if available else numeric[0]


def _looks_like_time_field(field: str | None) -> bool:
    return _field_matches(field, ("date", "day", "week", "month", "time", "dt"))


def _looks_like_metric_card(query: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    text = " ".join(str(query.get(key) or "") for key in ("title", "purpose", "chart_type")).lower()
    return len(rows) <= 3 and any(
        keyword in text
        for keyword in (
            "指标卡",
            "核心指标",
            "总览",
            "概览",
            "汇总",
            "kpi",
            "metric",
            "summary",
            "overview",
        )
    )


def _choose_visual_chart_type(
    chart_type: str,
    query: dict[str, Any],
    rows: list[dict[str, Any]],
    x_field: str | None,
) -> str:
    if chart_type != "table":
        return chart_type
    if not rows or not x_field:
        return chart_type

    text = " ".join(str(query.get(key) or "") for key in ("title", "purpose", "chart_type")).lower()
    if _looks_like_metric_card(query, rows):
        return "metric"
    if any(keyword in text for keyword in ("漏斗", "转化路径", "转化漏斗", "funnel")):
        return "funnel"
    if any(keyword in text for keyword in ("热力", "热力图", "cohort", "留存矩阵", "二维分布", "heatmap")):
        return "heatmap"
    if any(keyword in text for keyword in ("散点", "相关性", "关系分布", "scatter")):
        return "scatter"
    if any(keyword in text for keyword in ("流向", "路径流转", "资源流", "桑基", "sankey")):
        return "sankey"
    if any(keyword in text for keyword in ("矩形树", "树图", "层级贡献", "treemap")):
        return "treemap"

    if _looks_like_time_field(x_field) or any(keyword in text for keyword in ("趋势", "变化", "按天", "每日", "time trend")):
        return "line"

    structure_keywords = ("结构", "分布", "占比", "构成", "来源", "渠道", "商品", "类型", "档位", "偏好")
    if any(keyword in text for keyword in structure_keywords):
        return "pie" if len(rows) <= 12 else "bar"
    return "bar"


def _prefers_pie_chart(query: dict[str, Any], rows: list[dict[str, Any]], x_field: str | None) -> bool:
    if not rows or len(rows) > 12 or _looks_like_time_field(x_field):
        return False
    text = " ".join(str(query.get(key) or "") for key in ("title", "purpose", "chart_type")).lower()
    return any(
        keyword in text
        for keyword in ("饼图", "占比", "结构", "构成", "贡献", "分布", "share", "proportion", "composition", "contribution")
    )


def _is_pie_metric_suitable(query: dict[str, Any], y_field: str | None) -> bool:
    text = _query_metric_text(query)
    if any(
        keyword in text
        for keyword in ("倍率", "倍数", "增长率", "预测", "预估", "ltv", "arpu", "arppu", "predicted", "forecast")
    ):
        return False
    return not _field_matches(
        y_field or str(query.get("y") or ""),
        (
            "rate",
            "ratio",
            "conversion",
            "avg",
            "average",
            "arpu",
            "arppu",
            "per_",
            "percent",
            "pct",
        ),
    )


def _build_chart_config(query: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    fields = [str(field) for field in result.get("fields") or []]
    rows = result.get("data") or []
    columns = [{"name": _field_label(field), "value": field} for field in fields]

    chart_type = str(query.get("chart_type") or "table").lower()
    if chart_type not in CHART_TYPES:
        chart_type = "table"
    if not rows or (chart_type != "metric" and len(fields) < 2) or (chart_type == "metric" and not fields):
        chart_type = "table"

    numeric = _numeric_fields(fields, rows)
    x_field = _match_field(query.get("x"), fields)
    y_field = _match_field(query.get("y"), fields)
    series_field = _match_field(query.get("series"), fields)

    if not x_field:
        x_field = next((field for field in fields if field not in numeric), fields[0] if fields else None)
    requested_y_field = _requested_metric_field(query, numeric, x_field)
    if requested_y_field:
        y_field = requested_y_field
    elif not y_field:
        y_field = _choose_metric_field(query, numeric, x_field)

    if rows and len(fields) >= 2 and x_field and y_field:
        chart_type = _choose_visual_chart_type(chart_type, query, rows, x_field)

    if (
        chart_type in {"table", "bar", "column"}
        and _prefers_pie_chart(query, rows, x_field)
        and _is_pie_metric_suitable(query, y_field)
    ):
        chart_type = "pie"

    if chart_type == "pie" and (len(rows) > 12 or not _is_pie_metric_suitable(query, y_field)):
        chart_type = "bar"

    if chart_type == "line" and len(rows) < 2:
        chart_type = "metric" if _looks_like_metric_card(query, rows) else "table"

    if chart_type == "metric" and not y_field:
        chart_type = "table"
    elif chart_type in {"heatmap", "sankey"} and (not x_field or not y_field or not series_field):
        chart_type = "table"
    elif chart_type != "table" and chart_type != "metric" and (not x_field or not y_field):
        chart_type = "table"

    chart: dict[str, Any] = {
        "type": chart_type,
        "title": str(query.get("title") or "分析结果"),
        "columns": columns,
        "axis": {},
    }
    if series_field in numeric and chart_type not in {"heatmap", "sankey"}:
        series_field = None

    if chart_type == "funnel":
        order_field = _funnel_order_field(fields)
        step_field = _funnel_step_field(query, fields)
        preferred_y_field = next(
            (
                field
                for field in fields
                if _field_matches(field, ("users", "user_count", "players", "player_count", "converted_users", "count"))
                and field in numeric
            ),
            None,
        )
        if preferred_y_field:
            y_field = preferred_y_field
        if step_field:
            x_field = step_field
        elif order_field:
            x_field = order_field

        if not order_field and not step_field:
            chart_type = "bar"
        elif x_field:
            x_values = [row.get(x_field) for row in rows]
            has_repeated_steps = len(set(x_values)) < len(x_values)
            categorical_fields = [field for field in fields if field not in numeric and field != x_field]
            if not series_field and has_repeated_steps and categorical_fields:
                series_field = categorical_fields[0]
            if series_field:
                chart_type = "bar"
    chart["type"] = chart_type

    if chart_type == "metric" and y_field:
        metric_fields = [field for field in numeric if field != x_field] or [y_field]
        chart["axis"]["y"] = [{"name": _field_label(field), "value": field} for field in metric_fields]
    elif chart_type != "table" and x_field and y_field:
        chart["axis"]["x"] = {"name": _field_label(x_field), "value": x_field}
        chart["axis"]["y"] = {"name": _field_label(y_field), "value": y_field}
        if chart_type == "pie":
            pie_series_field = series_field if series_field and series_field not in numeric else x_field
            chart["axis"]["series"] = {"name": _field_label(pie_series_field), "value": pie_series_field}
        elif chart_type in {"heatmap", "sankey"} and series_field:
            chart["axis"]["series"] = {"name": _field_label(series_field), "value": series_field}
        elif series_field and series_field not in {x_field, y_field}:
            chart["axis"]["series"] = {"name": _field_label(series_field), "value": series_field}
    return chart


def _compact_rows(rows: list[dict[str, Any]], limit: int = 30) -> str:
    return orjson.dumps(rows[:limit]).decode()


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _coerce_day_number(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def _value_range_error(fields: list[str], rows: list[dict[str, Any]]) -> str | None:
    """Metric-agnostic guardrails: catch impossible values regardless of what
    the user asked to analyse or predict."""
    rate_keywords = (
        "retention",
        "留存",
        "conversion",
        "转化率",
        "payer_rate",
        "付费率",
        "渗透",
        "复购率",
        "流失率",
    )
    pct_keywords = ("_pct", "percent", "百分")
    count_keywords = (
        "users",
        "user_count",
        "players",
        "player_count",
        "payers",
        "payer_count",
        "orders",
        "order_count",
        "cnt",
        "人数",
        "人次",
        "订单数",
        "会话数",
    )
    multiplier_exclude = ("mult", "倍", "growth", "增长", "index", "_x", "delta", "diff", "change")
    for field in fields:
        lower = field.lower()
        is_rate = any(keyword in lower for keyword in rate_keywords) or any(
            keyword in lower for keyword in pct_keywords
        )
        is_count = any(keyword in lower for keyword in count_keywords)
        if is_rate and any(keyword in lower for keyword in multiplier_exclude):
            is_rate = False
        if not is_rate and not is_count:
            continue
        for row in rows:
            value = _coerce_float(row.get(field))
            if value is None:
                continue
            if is_rate and (value < -1e-6 or value > 100 + 1e-6):
                return (
                    f"字段 {field} 出现超出合理区间的比率值 {value:.6g}；"
                    "留存率/转化率/付费率等比率字段应落在 0~100%（或 0~1）之间，"
                    "请检查是否分母错误、口径混用，或把累计值/计数当成了比率。"
                )
            if is_count and value < -1e-6:
                return (
                    f"字段 {field} 出现负的计数值 {value:.6g}；用户数/订单数/会话数等计数不可能为负，"
                    "请检查 join 或聚合逻辑是否错误。"
                )
    return None


def _wide_funnel_validation_error(
    query: dict[str, Any],
    fields: list[str],
    rows: list[dict[str, Any]],
    numeric: list[str],
) -> str | None:
    text = _query_metric_text(query)
    if not any(keyword in text for keyword in ("漏斗", "转化", "流失", "funnel", "conversion")):
        return None

    count_fields = [
        field
        for field in numeric
        if _field_matches(field, ("total_users", "new_users", "users", "user_count", "players", "player_count"))
        and not _field_matches(field, ("pct", "rate", "ratio", "percent"))
    ]
    rate_fields = [
        field
        for field in numeric
        if _field_matches(field, ("pct", "rate", "ratio", "conversion", "转化率", "流失率"))
    ]
    if not count_fields or len(rate_fields) < 2 or len(rows) < 3:
        return None

    count_values = [
        _coerce_float(row.get(count_fields[0]))
        for row in rows
        if _coerce_float(row.get(count_fields[0])) is not None
    ]
    rate_values = [
        _coerce_float(row.get(field))
        for row in rows
        for field in rate_fields
        if _coerce_float(row.get(field)) is not None
    ]
    if count_values and rate_values and max(count_values) <= 1 and min(rate_values) >= 99.99:
        return (
            "分维度漏斗结果异常：各分组样本量几乎都为 1，且关键转化率全部为 100%。"
            "这通常表示 SQL 聚合时 count(distinct) 的对象写成了步骤、布尔值或常量，"
            "而不是同一 cohort 内的 distinct player_id。请先按玩家粒度生成每个用户的步骤完成状态，"
            "再按渠道/设备/服务器等维度汇总人数和转化率。"
        )
    return None


def _tutorial_step_sql_error(query: dict[str, Any]) -> str | None:
    text = _query_metric_text(query)
    sql = str(query.get("sql") or "").lower()
    if "tutorial_step" not in sql:
        return None
    if "attributes" in sql and "step" in sql:
        return None
    if not any(keyword in text for keyword in ("新手", "教程", "tutorial", "漏斗", "转化", "流失")):
        return None
    return (
        "新手教程口径过宽：SQL 只判断了是否发生过 tutorial_step，却没有读取 attributes->>'step' "
        "来区分具体步骤。任意 tutorial_step 只能表示进入过新手流程，不能表示完成教程；"
        "请按玩家粒度提取关键步骤或实际最大步骤后再计算完成率/流失率。"
    )


def _payment_success_sql_error(query: dict[str, Any]) -> str | None:
    text = _query_metric_text(query)
    sql = str(query.get("sql") or "").lower()
    if not any(keyword in text for keyword in ("首付", "首充", "付费", "支付", "first_pay", "first pay", "payer")):
        return None
    if "fact_payments" in sql and ("is_first_pay" in sql or "pay_sequence" in sql) and "payment_status" not in sql:
        return (
            "首付/首充成功口径不完整：SQL 使用了 fact_payments 的 is_first_pay/pay_sequence，"
            "但没有过滤 payment_status='success'。failed/cancelled/refunded 订单不能计入成功首付，"
            "请只统计成功支付的首次付费玩家。"
        )
    if "purchase_start" in sql and "purchase_success" not in sql and "fact_payments" not in sql:
        return (
            "首付/首充成功口径不完整：SQL 只统计了 purchase_start，"
            "这表示发起支付或购买意向，不等于支付成功。请补充 purchase_success 或 fact_payments "
            "中 payment_status='success' 的首次付费口径。"
        )
    return None


def _semantic_validation_error(query: dict[str, Any], result: dict[str, Any]) -> str | None:
    rows = result.get("data") or []
    fields = [str(field) for field in result.get("fields") or []]

    range_error = _value_range_error(fields, rows)
    if range_error:
        return range_error

    if len(rows) < 2:
        return None

    text = _query_metric_text(query)
    if str(query.get("chart_type") or "").lower() == "funnel" or any(
        keyword in text for keyword in ("漏斗", "转化路径", "转化漏斗", "funnel")
    ):
        numeric = _numeric_fields(fields, rows)
        wide_error = _wide_funnel_validation_error(query, fields, rows, numeric)
        if wide_error:
            return wide_error
        tutorial_error = _tutorial_step_sql_error(query)
        if tutorial_error:
            return tutorial_error
        payment_error = _payment_success_sql_error(query)
        if payment_error:
            return payment_error

        y_field = _match_field(query.get("y"), fields)
        preferred = ("users", "user_count", "players", "player_count", "converted_users", "count")
        preferred_y_field = next((field for field in fields if _field_matches(field, preferred) and field in numeric), None)
        if preferred_y_field:
            y_field = preferred_y_field
        elif not y_field or y_field not in numeric:
            y_field = None
        if not y_field:
            return None

        series_field = _match_field(query.get("series"), fields)
        order_field = _funnel_order_field(fields)
        step_field = _funnel_step_field(query, fields)
        if series_field and series_field in numeric:
            series_field = None
        if series_field and series_field == step_field:
            series_field = None

        step_key_field = step_field or order_field
        if not step_key_field:
            return None

        step_values = [row.get(step_key_field) for row in rows]
        has_repeated_steps = len(set(step_values)) < len(step_values)
        categorical_fields = [
            field
            for field in fields
            if field not in numeric and field not in {step_field, order_field}
        ]
        if not series_field and has_repeated_steps and categorical_fields:
            series_field = next(
                (
                    field
                    for field in categorical_fields
                    if len({row.get(field) for row in rows if row.get(field) is not None}) > 1
                ),
                categorical_fields[0],
            )

        groups: dict[Any, list[dict[str, Any]]] = {}
        for row in rows:
            key = row.get(series_field) if series_field else "__single_funnel__"
            groups.setdefault(key, []).append(row)

        zero_tail_groups: list[Any] = []
        valid_group_count = 0
        for key, group_rows in groups.items():
            if order_field:
                ordered_rows = sorted(
                    group_rows,
                    key=lambda row: _coerce_float(row.get(order_field)) if _coerce_float(row.get(order_field)) is not None else 10**9,
                )
            else:
                ordered_rows = group_rows
            values: list[float] = []
            previous_value: float | None = None
            previous_label: Any = None
            for index, row in enumerate(ordered_rows, start=1):
                value = _coerce_float(row.get(y_field))
                if value is None:
                    continue
                values.append(value)
                label = (
                    row.get(step_field)
                    if step_field
                    else row.get("step_name") or row.get("stage") or row.get("step") or row.get("name") or row.get(order_field) or index
                )
                if previous_value is not None and value > previous_value + 1e-6:
                    group_text = "" if key == "__single_funnel__" else f"（分组 {key}）"
                    return (
                        f"漏斗人数{group_text}在步骤 {previous_label}={previous_value:.6g} 到 "
                        f"{label}={value:.6g} 出现倒挂；漏斗必须按同 cohort 的递进 distinct player_id 计算，"
                        "后续步骤人数不能大于前序步骤。"
                    )
                previous_value = value
                previous_label = label
            if len(values) >= 3 and values[0] > 0 and all(value == 0 for value in values[1:]):
                zero_tail_groups.append(key)
            if len(values) >= 2:
                valid_group_count += 1
        if zero_tail_groups and (not series_field or len(zero_tail_groups) == valid_group_count):
            group_text = "" if zero_tail_groups == ["__single_funnel__"] else f"（分组 {zero_tail_groups[0]} 等）"
            return (
                f"漏斗人数{group_text}从第二步开始全部为 0；这通常表示使用了不存在的事件名、过窄的事件条件或错误 join。"
                "请核对实际 event_name/attributes 枚举，并改用真实存在的递进步骤。"
            )
        return None

    if not any(keyword in text for keyword in ("ltv", "生命周期收入", "生命周期价值", "长期价值")):
        return None

    day_field = next(
        (
            field
            for field in fields
            if field.lower() in {"lifecycle_day", "lifecycle_day_number", "day_index", "day", "life_day"}
        ),
        None,
    )
    if not day_field:
        return None

    cumulative_fields = [
        field
        for field in fields
        if any(keyword in field.lower() for keyword in ("ltv", "cumulative", "cum_"))
        and not any(keyword in field.lower() for keyword in ("single", "daily", "day_revenue"))
    ]
    if not cumulative_fields:
        return None

    ordered_rows = sorted(
        (
            (_coerce_day_number(row.get(day_field)), row)
            for row in rows
        ),
        key=lambda item: item[0] if item[0] is not None else 10**9,
    )
    ordered_rows = [(day, row) for day, row in ordered_rows if day is not None]
    if len(ordered_rows) < 2:
        return None

    tolerance = 1e-6
    for field in cumulative_fields:
        previous_day: int | None = None
        previous_value: float | None = None
        for day, row in ordered_rows:
            value = _coerce_float(row.get(field))
            if value is None:
                continue
            if previous_value is not None and value + tolerance < previous_value:
                return (
                    f"LTV 累计字段 {field} 在 D{previous_day}={previous_value:.6g} 到 "
                    f"D{day}={value:.6g} 出现下降；累计 LTV/累计收入必须同 cohort 同分母且单调不下降。"
                )
            previous_day = day
            previous_value = value
    return None


def _repair_sql(
    llm,
    question: str,
    raw_query: dict[str, Any],
    failed_sql: str,
    error: Exception,
    schema: str,
    sample_data: str,
    data_profile: str = "",
    knowledge: str = "",
) -> str:
    prompt = (
        f"用户问题：{question}\n"
        f"数据块标题：{raw_query.get('title')}\n"
        f"分析目的：{raw_query.get('purpose')}\n"
        f"原始 SQL：\n{failed_sql}\n\n"
        f"执行错误：\n{str(error)[:3000]}\n\n"
        f"{_knowledge_block(knowledge)}"
        f"数据库 schema：\n{schema[:18000]}\n\n"
        f"样例数据：\n{sample_data[:6000]}\n\n"
        f"实际数据画像（必须优先使用这些真实枚举值，不要编造 event_name/status/属性值）：\n{data_profile[:12000]}"
    )
    text = _llm_text(llm, [SystemMessage(content=SQL_REPAIR_PROMPT), HumanMessage(content=prompt)])
    try:
        data = _extract_json_object(text)
        repaired_sql = str(data.get("sql") or "")
    except Exception:
        repaired_sql = text
    return _normalise_sql(repaired_sql)


def _summarise_block(llm, question: str, block: dict[str, Any]) -> str:
    rows = block.get("data") or []
    if not rows:
        return "这组查询没有返回数据，暂时不能从该角度形成确定判断。"
    prompt = (
        f"用户问题：{question}\n"
        f"数据块标题：{block.get('title')}\n"
        f"分析目的：{block.get('purpose')}\n"
        f"SQL：{block.get('sql')}\n"
        f"字段：{block.get('fields')}\n"
        f"查询结果样例：{_compact_rows(rows)}"
    )
    return _llm_text(llm, [SystemMessage(content=SUMMARY_PROMPT), HumanMessage(content=prompt)])


def _final_answer(llm, question: str, intro: str, blocks: list[dict[str, Any]]) -> str:
    block_details = []
    for block in blocks:
        data = block.get("data") or []
        block_details.append(
            {
                "title": block.get("title"),
                "purpose": block.get("purpose"),
                "summary": block.get("summary"),
                "fields": block.get("fields"),
                "row_count": len(data),
                "rows": data[:12],
            }
        )
    payload = orjson.dumps(block_details).decode()
    prompt = (
        f"用户问题：{question}\n"
        f"问题理解：{intro}\n"
        f"各数据块（含真实查询数据 rows，所有数字结论必须取自这些 rows，禁止编造或臆测未提供的数字）：\n"
        f"{payload[:16000]}"
    )
    return _llm_text(llm, [SystemMessage(content=FINAL_PROMPT), HumanMessage(content=prompt)])


def _initial_outline_messages(request: AnalysisAssistantRequest) -> list[BaseMessage]:
    question = request.messages[-1].content.strip()
    history = [
        {"role": item.role, "content": item.content}
        for item in request.messages[-6:-1]
        if item.content.strip()
    ]
    user_content = (
        f"页面上下文：{request.context or ''}\n"
        f"历史对话：{orjson.dumps(history).decode()}\n"
        f"用户问题：{question}"
    )
    return [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=INITIAL_OUTLINE_PROMPT + "\n\n" + user_content)]


def _build_plan(
    llm,
    request: AnalysisAssistantRequest,
    schema: str,
    sample_data: str,
    datasource: CoreDatasource,
    data_profile: str = "",
    knowledge: str = "",
) -> dict[str, Any]:
    question = request.messages[-1].content.strip()
    context = request.context or ""
    now = datetime.now().strftime("%Y-%m-%d")
    history = [
        {"role": item.role, "content": item.content}
        for item in request.messages[-6:-1]
        if item.content.strip()
    ]
    user_content = (
        f"今天日期：{now}\n"
        f"数据源：{datasource.name}（{datasource.type}）\n"
        f"页面上下文：{context}\n"
        f"历史对话：{orjson.dumps(history).decode()}\n"
        f"用户问题：{question}\n\n"
        f"{_knowledge_block(knowledge)}"
        f"数据库 schema：\n{schema[:18000]}\n\n"
        f"样例数据：\n{sample_data[:6000]}\n\n"
        f"实际数据画像（必须优先使用这些真实枚举值，不要编造 event_name/status/属性值）：\n{data_profile[:12000]}"
    )
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=PLAN_PROMPT + "\n\n" + user_content)]
    text = _llm_text(llm, messages)
    try:
        plan = _extract_json_object(text)
    except Exception:
        retry = _llm_text(
            llm,
            messages
            + [
                AIMessage(content=text),
                HumanMessage(content="上一次输出无法解析。请严格只返回一个合法 JSON 对象，字段和格式必须符合要求。"),
            ],
        )
        plan = _extract_json_object(retry)

    queries = plan.get("queries") or []
    if not isinstance(queries, list) or not queries:
        raise ValueError("模型没有生成可执行的数据召回计划")
    plan["queries"] = queries[:MAX_ANALYSIS_QUERIES]
    return plan


def _build_forecast_plan(
    llm,
    request: AnalysisAssistantRequest,
    schema: str,
    sample_data: str,
    datasource: CoreDatasource,
    data_profile: str = "",
    knowledge: str = "",
) -> dict[str, Any]:
    question = request.messages[-1].content.strip()
    context = request.context or ""
    now = datetime.now().strftime("%Y-%m-%d")
    history = [
        {"role": item.role, "content": item.content}
        for item in request.messages[-6:-1]
        if item.content.strip()
    ]
    user_content = (
        f"今天日期：{now}\n"
        f"数据源：{datasource.name}（{datasource.type}）\n"
        f"页面上下文：{context}\n"
        f"历史对话：{orjson.dumps(history).decode()}\n"
        f"用户问题：{question}\n\n"
        f"{_knowledge_block(knowledge)}"
        f"数据库 schema：\n{schema[:22000]}\n\n"
        f"样例数据：\n{sample_data[:8000]}\n\n"
        f"实际数据画像（必须优先使用这些真实枚举值，不要编造 event_name/status/属性值）：\n{data_profile[:12000]}"
    )
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=FORECAST_PLAN_PROMPT + "\n\n" + user_content)]
    text = _llm_text(llm, messages)
    try:
        plan = _extract_json_object(text)
    except Exception:
        retry = _llm_text(
            llm,
            messages
            + [
                AIMessage(content=text),
                HumanMessage(content="上一次输出无法解析。请严格只返回一个合法 JSON 对象，字段和格式必须符合要求。"),
            ],
        )
        plan = _extract_json_object(retry)

    queries = plan.get("queries") or []
    if not isinstance(queries, list) or not queries:
        raise ValueError("模型没有生成可执行的预测数据召回计划")
    plan["queries"] = queries[:MAX_FORECAST_QUERIES]
    return plan


@router.post("/chat", include_in_schema=False)
@require_permissions(permission=SqlbotPermission(type='ds', keyExpression="request.datasource_id"))
async def chat(request: AnalysisAssistantRequest, current_user: CurrentUser, session: SessionDep):
    if not current_user:
        raise RuntimeError("Unauthorized")
    if not request.messages or not request.messages[-1].content.strip():
        raise RuntimeError("Question cannot be Empty")

    llm = await _create_llm()

    def generate():
        question = request.messages[-1].content.strip()
        blocks: list[dict[str, Any]] = []
        try:
            outline_text = ""
            for chunk in llm.stream(_initial_outline_messages(request)):
                content = _chunk_text(chunk.content)
                if content:
                    outline_text += content
                    yield _sse({"type": "plan_delta", "content": content})
            if not outline_text.strip():
                yield _sse({"type": "plan_delta", "content": "我会先理解你的分析目标，再拆解关键维度并结合数据给出结论和建议。"})
            yield _trace("正在确认本次分析使用的业务口径。")
            datasource = _get_datasource(session, current_user, request.datasource_id)
            yield _trace("正在结合当前业务数据，梳理可分析的关键维度。")
            schema, allowed_tables = get_table_schema(session, current_user, datasource, question, embedding=False)
            if not allowed_tables:
                raise RuntimeError("当前用户在该数据源下没有可分析的数据表权限")
            sample_data = "" if is_normal_user(current_user) else get_tables_sample_data(session, current_user, datasource)
            data_profile = "" if is_normal_user(current_user) else _get_data_profile(datasource, schema)
            oid = current_user.oid if current_user.oid is not None else 1
            knowledge = _collect_metric_knowledge(session, oid, datasource.id, question)
            if knowledge.strip():
                yield _trace("已加载本工作空间配置的统一业务口径（术语定义与标准 SQL 示例），将据此对齐指标算法。")
            forecast_requested = _is_forecast_question(question)
            if forecast_requested:
                yield _trace("正在识别预测指标、目标人群和可用的历史观察窗口。")
                plan = _build_forecast_plan(llm, request, schema, sample_data, datasource, data_profile, knowledge)
                yield _trace("预测方法和数据检查项已确定，下面按预测口径召回数据。")
            else:
                yield _trace("正在把分析框架拆成可执行的数据检查项。")
                plan = _build_plan(llm, request, schema, sample_data, datasource, data_profile, knowledge)

            intro = str(plan.get("intro") or "我会先识别问题指标，再从多个角度查看数据并给出分析建议。")
            yield _trace("具体执行步骤已确定，下面按关键维度逐一分析。")

            for index, raw_query in enumerate(plan.get("queries") or [], start=1):
                if not isinstance(raw_query, dict):
                    continue
                block_id = str(raw_query.get("id") or f"q{index}")
                title = str(raw_query.get("title") or f"分析 {index}")
                purpose = str(raw_query.get("purpose") or "")
                yield _sse(
                    {
                        "type": "progress",
                        "content": f"正在分析：{title}",
                        "block_id": block_id,
                    }
                )
                yield _trace(f"先看「{title}」这个角度。", block_id=block_id)

                block: dict[str, Any] = {
                    "id": block_id,
                    "title": title,
                    "purpose": purpose,
                    "sql": "",
                    "fields": [],
                    "data": [],
                    "chart": None,
                    "summary": "",
                }
                try:
                    raw_query["_user_question"] = question
                    sql = _prepare_sql_for_execution(
                        llm, session, current_user, datasource, str(raw_query.get("sql") or ""), allowed_tables
                    )
                    block["sql"] = sql
                    raw_query["sql"] = sql
                    try:
                        result = exec_sql(datasource, sql, origin_column=False)
                    except Exception as first_error:
                        yield _trace("这个角度的数据口径需要校准，正在重新整理后再试。", block_id=block_id)
                        repaired_sql = _repair_sql(llm, question, raw_query, sql, first_error, schema, sample_data, data_profile, knowledge)
                        sql = _prepare_sql_for_execution(
                            llm, session, current_user, datasource, repaired_sql, allowed_tables
                        )
                        block["sql"] = sql
                        raw_query["sql"] = sql
                        result = exec_sql(datasource, sql, origin_column=False)
                    semantic_error = _semantic_validation_error(raw_query, result)
                    if semantic_error:
                        yield _trace("这个角度的累计口径不一致，正在按同 cohort 口径重新校准。", block_id=block_id)
                        repaired_sql = _repair_sql(llm, question, raw_query, sql, ValueError(semantic_error), schema, sample_data, data_profile, knowledge)
                        sql = _prepare_sql_for_execution(
                            llm, session, current_user, datasource, repaired_sql, allowed_tables
                        )
                        block["sql"] = sql
                        raw_query["sql"] = sql
                        result = exec_sql(datasource, sql, origin_column=False)
                        semantic_error = _semantic_validation_error(raw_query, result)
                        if semantic_error:
                            raise ValueError(semantic_error)
                    block["fields"] = [str(field) for field in result.get("fields") or []]
                    block["data"] = result.get("data") or []
                    yield _trace("这个角度的数据已经整理好，正在提炼关键发现。", block_id=block_id)
                    block["chart"] = _build_chart_config(raw_query, result)
                    block["summary"] = _summarise_block(llm, question, block)
                except Exception as query_error:
                    traceback.print_exc()
                    block["error"] = "数据计算失败"
                    block["summary"] = "这个角度的数据暂时无法稳定计算，已先跳过；其它维度的分析会继续完成。"

                blocks.append(block)
                yield _sse({"type": "block", "block": block})

            yield _trace("正在汇总各个角度的发现，形成最终判断和建议。")
            final = _final_answer(llm, question, intro, blocks)
            yield _sse({"type": "final", "content": final})
            yield _sse({"type": "finish"})
        except Exception as e:
            traceback.print_exc()
            yield _sse({"type": "error", "content": str(e)})

    return StreamingResponse(generate(), media_type="text/event-stream")
