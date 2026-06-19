import json
import re
import traceback
from datetime import datetime
from typing import Any, Literal

import orjson
import sqlglot
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlglot import exp
from sqlmodel import select

from apps.ai_model.model_factory import LLMFactory, get_default_config
from apps.chat.curd.custom_prompt import CustomPromptTargetScopeEnum, CustomPromptTypeEnum
from apps.datasource.crud.analysis_context import (
    collect_custom_agent_context,
    collect_metric_knowledge,
    resolve_datasource_context,
)
from apps.datasource.crud.datasource import get_table_schema, get_tables_sample_data
from apps.datasource.crud.permission import get_row_permission_filters, is_normal_user
from apps.datasource.crud.sql_permission import apply_row_permission_filters, validate_sql_scope, validate_sql_table_scope
from apps.datasource.models.datasource import CoreDatasource
from apps.db.constant import DB
from apps.db.db import exec_sql, get_sqlglot_dialect
from common.core.deps import CurrentUser, SessionDep
from common.utils.utils import extract_nested_json

router = APIRouter(tags=["analysis_assistant"], prefix="/analysis-assistant")


class AnalysisAssistantMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(default="")


class AnalysisAssistantRequest(BaseModel):
    messages: list[AnalysisAssistantMessage] = Field(default_factory=list)
    context: str | None = None
    datasource_id: int | None = None
    custom_prompt_id: int | None = None


SYSTEM_PROMPT = """你是星通智数内置的综合分析助手，一个独立于“智能报表”的业务分析 Agent。

你的职责：
1. 将用户的自然语言问题转成业务分析框架。
2. 判断需要召回哪些数据，并生成只读 SQL。
3. 基于召回数据做图表解释、异常归因、结论提炼和改进建议。
4. 你可以复用系统的项目连接能力，但不要复用“智能报表”的对话状态和提示词。

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
- 用户问题里的时间范围、目标对象和指标名称要按原文理解，不要擅自扩大、缩小或改写。
- 具体指标定义、业务口径和标准算法以项目已配置的术语与 SQL 示例为准。
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


def _db_info(datasource: CoreDatasource) -> DB:
    return DB.get_db(getattr(datasource, "type", None), default_if_none=True)


def _database_name(datasource: CoreDatasource) -> str:
    return _db_info(datasource).db_name


def _sqlglot_write_dialect(datasource: CoreDatasource) -> str | None:
    ds_type = str(getattr(datasource, "type", "") or "")
    dialect = get_sqlglot_dialect(ds_type)
    if dialect:
        return dialect
    if ds_type.casefold() in {"pg", "excel"}:
        return "postgres"
    if ds_type.casefold() in {"redshift", "kingbase"}:
        return "postgres"
    if ds_type.casefold() == "oracle":
        return "oracle"
    if ds_type.casefold() == "ck":
        return "clickhouse"
    return None


def _limit_instruction(datasource: CoreDatasource) -> str:
    database_name = _database_name(datasource)
    ds_type = str(getattr(datasource, "type", "") or "")
    if ds_type.casefold() == "sqlserver":
        syntax = f"使用 SELECT TOP {MAX_SQL_ROWS} ...，或 OFFSET/FETCH 分页语法；禁止使用 LIMIT。"
    elif ds_type.casefold() == "oracle":
        syntax = f"使用 FETCH FIRST {MAX_SQL_ROWS} ROWS ONLY；复杂聚合也可以在最外层使用 ROWNUM <= {MAX_SQL_ROWS}。"
    else:
        syntax = f"使用 LIMIT {MAX_SQL_ROWS}。"
    return (
        f"当前数据源数据库：{database_name}（type={ds_type or 'unknown'}）。"
        f"生成和修正 SQL 必须使用该数据库方言，最多返回 {MAX_SQL_ROWS} 行；"
        f"{syntax}"
    )


def _dialect_block(datasource: CoreDatasource) -> str:
    db = _db_info(datasource)
    return (
        "数据库方言强制规则：\n"
        f"- {_limit_instruction(datasource)}\n"
        f"- 标识符引用请使用 {db.db_name} 的习惯写法（前缀 {db.prefix}，后缀 {db.suffix}），"
        "不要混用其它数据库的专属语法。\n\n"
    )


def _clean_identifier(identifier: str) -> str:
    value = str(identifier or "").strip()
    if value.startswith("[") and value.endswith("]"):
        return value[1:-1]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("`") and value.endswith("`")):
        return value[1:-1]
    return value


def _quote_identifier(identifier: str, datasource: CoreDatasource) -> str:
    db = _db_info(datasource)
    value = _clean_identifier(identifier)
    if db.prefix == "[" and db.suffix == "]":
        value = value.replace("]", "]]")
    elif db.prefix == "`":
        value = value.replace("`", "``")
    elif db.prefix == '"':
        value = value.replace('"', '""')
    return f"{db.prefix}{value}{db.suffix}"


def _quote_table_reference(table_ref: str, datasource: CoreDatasource) -> str:
    parts = [_clean_identifier(part) for part in str(table_ref or "").split(".") if part.strip()]
    return ".".join(_quote_identifier(part, datasource) for part in parts)


def _profile_table_reference(raw_table: str, datasource: CoreDatasource) -> str:
    ds_type = str(getattr(datasource, "type", "") or "").casefold()
    table_ref = str(raw_table or "").strip()
    if "." in table_ref and ds_type not in {"sqlserver", "oracle", "dm"}:
        table_ref = table_ref.split(".")[-1].strip()
    return _quote_table_reference(table_ref, datasource)


def _normalise_aggregate_alias(expression: str, alias: str, datasource: CoreDatasource) -> str:
    return f"{expression} AS {_quote_identifier(alias, datasource)}"


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
      "sql": "只读 SQL，必须使用当前数据源数据库方言，最多返回 200 行",
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
- 具体指标定义、字段选择、计算算法、时间窗口和异常判断必须优先遵循“统一业务口径”的术语与 SQL 示例；知识块没有覆盖时，才结合 schema 和样例数据做业务合理推断。
- 如果用户提到“最近一个月/近期”等相对时间，并且上下文提供了真实数据时间边界，优先以相关数据表里的最大日期为基准，而不是系统当前日期。
- 如果用户明确给出“最近 7 天/近 7 日/最近 N 天”等时间范围，SQL、标题和分析口径必须严格使用这个范围，不要擅自扩大成 30 天或最近一个月。
- 如果问题是归因类，至少覆盖趋势、结构拆解、关键分组维度等角度中的两个；具体分组字段必须来自当前 schema 或语义层。
- 图表类型应尽量可视化：核心单值指标用 metric，趋势用 line，结构/分布/占比用 bar/pie/treemap，步骤转化用 funnel，矩阵或二维分布用 heatmap，二维关系用 scatter，来源去向或路径流转用 sankey；只有无法确定维度和指标时才使用 table。
"""


FORECAST_PLAN_PROMPT = """请基于用户问题、页面上下文、数据库 schema 和样例数据，生成“通用预测分析计划”。

你必须只输出一个合法 JSON 对象，不要输出 Markdown，不要输出额外解释。

JSON 格式：
{
  "intro": "用业务语言说明用户想预测什么指标、目标对象是什么、你会如何使用已观测数据和历史规律进行预测。",
  "forecast_metric": "预测指标，例如当前语义层定义的核心指标、金额、比率、均值、数量或 other",
  "forecast_target": "预测对象，例如某个分组、最近 N 天目标群体、未来 N 天指标等",
  "forecast_method": "简要说明预测方法，必须说明已观测数据、历史基准、成熟样本、置信度如何使用",
  "steps": ["预测步骤1", "预测步骤2"],
  "queries": [
    {
      "id": "q1",
      "title": "图表标题",
      "purpose": "为什么要查这组数据",
      "sql": "只读 SQL，必须使用当前数据源数据库方言，最多返回 200 行",
      "chart_type": "line|column|bar|pie|metric|funnel|heatmap|scatter|sankey|treemap|table",
      "x": "结果集中作为时间、序列位置或维度的字段别名",
      "y": "结果集中作为预测值或核心指标的字段别名",
      "series": "可选，结果集中作为分组系列的字段别名"
    }
  ]
}

通用预测原则：
- 你是通用预测分析助手，必须根据用户问题和项目语义层识别预测指标、目标对象、观察窗口和预测周期。
- 具体预测算法、字段选择、指标口径和行业定义必须优先遵循“统一业务口径”的术语与 SQL 示例；不要在提示词中写死某一个指标的算法。
- 用户问题如果给出目标对象、时间范围或预测周期，必须按原文理解，不要擅自扩大、缩小或改写。
- SQL 只能 SELECT 或 WITH，不允许 INSERT/UPDATE/DELETE/DDL，不要创建表、视图或持久化聚合。
- 不要查询不存在于 schema 的表或字段，所有输出字段使用英文小写别名。
- 预测必须尽量基于明细事实表在查询时计算，不要假设存在 agg/kpi/snapshot 表。
- 预测结果要区分已观测值、历史基准、预测值和置信度；数据不足时要明确说明不确定性，不要把无数据当成确定结论。
- 查询结果中如果包含 confidence/confidence_level，取值必须与样本量、已观测天数和历史基准可用性一致；不要出现字段为 High 但总结又说 Low 的矛盾。
- 查询结果中尽量包含 sample_size、actual_value、predicted_value、benchmark_value、forecast_basis、confidence 等字段；如果字段命名和业务不匹配，可用同义字段，但必须让图表和总结能区分实测与预测。
- 折线图必须至少有两个时间点或序列位置；单个倍率、单个基准值、单行结果不要使用 line，应使用 table、metric 或 bar。
- 趋势或序列曲线用 line；核心单值指标用 metric；分组对比用 bar/column；占比结构且指标可累加时可用 pie，层级/贡献结构可用 treemap；步骤转化用 funnel；矩阵或二维分布用 heatmap；二维关系用 scatter；来源去向或路径流转用 sankey。
- queries 数量 2 到 4 个：至少包含一个主预测曲线/预测表；如果用户需要归因或结构拆解，再包含当前 schema 或语义层中可用的关键维度。
"""


SQL_REPAIR_PROMPT = """你是当前数据源的 SQL 查询修正器。请根据执行错误、原始 SQL 和 schema 修正 SQL。

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
- 具体指标定义、字段选择、枚举值含义和业务算法优先依据随后的统一业务口径、schema、样例数据和实际数据画像。
- 修正时只解决执行错误、权限范围、字段不存在、语法错误或明显的数据一致性问题，不要引入提示词中未提供的业务算法。
"""


SUMMARY_PROMPT = """你是业务数据分析师。请根据用户问题和查询结果，总结这个数据块。

要求：
- 简体中文。
- 2 到 4 句话。
- 必须引用查询结果里能支撑的现象。
- 不要编造查询结果之外的数字。
- 术语、口径、字段解释优先遵循用户问题和随后的统一业务口径。
- 如果查询结果包含样本量、预测值、历史基准、置信度、空值或异常提示，要用业务语言解释它们代表什么。
"""


FINAL_PROMPT = """你是业务数据分析师。请基于多个数据块的总结和它们附带的真实查询数据 rows，回答用户最初的问题。

输出结构：
1. 先给最终判断。
2. 再给关键依据。
3. 最后给 3 条以内改进建议。

要求简洁、可执行，不要编造没有数据支撑的信息。
所有具体数字（金额、人数、比率、预测值等）必须直接来自数据块的 rows 字段；如果 rows 里没有某个数字，就不要给出该数字，而要说明数据未覆盖。
术语、口径、字段解释和异常判断优先遵循用户问题、数据块说明以及随后的统一业务口径。
如果数据不足以支持确定判断，要说明不确定性和需要补充的数据。
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


async def _create_llm(custom_model_id: int | None = None):
    config = await get_default_config(custom_model_id)
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


def _contains_row_limit(sql: str) -> bool:
    return bool(
        re.search(r"\blimit\s+\d+\b", sql, flags=re.IGNORECASE)
        or re.search(r"\btop\s+\(?\d+\)?\b", sql, flags=re.IGNORECASE)
        or re.search(r"\bfetch\s+(?:first|next)\s+\d+\s+rows\s+only\b", sql, flags=re.IGNORECASE)
        or re.search(r"\brownum\s*<=\s*\d+\b", sql, flags=re.IGNORECASE)
    )


def _clamp_common_limit_syntax(sql: str) -> str:
    def replace(match: re.Match[str]) -> str:
        value = int(match.group("value"))
        if value <= MAX_SQL_ROWS:
            return match.group(0)
        suffix = match.groupdict().get("suffix") or ""
        return f"{match.group('prefix')}{MAX_SQL_ROWS}{suffix}"

    patterns = (
        r"(?P<prefix>\blimit\s+)(?P<value>\d+)(?P<suffix>\b)(?!\s*,)",
        r"(?P<prefix>\btop\s+\(?)(?P<value>\d+)(?P<suffix>\)?\b)",
        r"(?P<prefix>\bfetch\s+(?:first|next)\s+)(?P<value>\d+)(?P<suffix>\s+rows\s+only\b)",
        r"(?P<prefix>\brownum\s*<=\s*)(?P<value>\d+)(?P<suffix>\b)",
    )
    for pattern in patterns:
        sql = re.sub(pattern, replace, sql, flags=re.IGNORECASE)
    return sql


def _limit_literal(limit: exp.Expression | None) -> exp.Literal | None:
    if limit is None:
        return None
    value = limit.args.get("expression") or limit.args.get("count")
    return value if isinstance(value, exp.Literal) else None


def _enforce_max_limit(statement: exp.Expression) -> None:
    limit = statement.args.get("limit")
    if limit is None:
        if not isinstance(statement, exp.Query):
            raise ValueError("综合分析助手只允许执行查询语句")
        statement.set("limit", exp.Limit(expression=exp.Literal.number(MAX_SQL_ROWS)))
        return

    literal = _limit_literal(limit)
    if literal is None:
        return
    try:
        value = int(str(literal.this))
    except (TypeError, ValueError):
        return
    if value <= MAX_SQL_ROWS:
        return
    if "count" in limit.args:
        limit.set("count", exp.Literal.number(MAX_SQL_ROWS))
    else:
        limit.set("expression", exp.Literal.number(MAX_SQL_ROWS))


def _supports_limit_wrapper(datasource: CoreDatasource) -> bool:
    ds_type = str(getattr(datasource, "type", "") or "")
    return ds_type.casefold() not in {"sqlserver", "oracle"}


def _normalise_sql(sql: str, datasource: CoreDatasource | None = None) -> str:
    sql = (sql or "").strip()
    sql = re.sub(r"^```(?:sql)?", "", sql, flags=re.IGNORECASE).strip()
    sql = re.sub(r"```$", "", sql).strip()
    while sql.endswith(";"):
        sql = sql[:-1].strip()
    if not re.match(r"^(select|with)\b", sql, flags=re.IGNORECASE):
        raise ValueError("综合分析助手只允许执行 SELECT/WITH 查询")
    if ";" in sql:
        raise ValueError("综合分析助手每个数据块只允许执行一条 SELECT/WITH 查询")
    sql = _clamp_common_limit_syntax(sql)
    if datasource is None:
        datasource = CoreDatasource(type="pg", name="", configuration="{}", create_by=0, recommended_config=0)
    dialect = _sqlglot_write_dialect(datasource)
    try:
        statements = [statement for statement in sqlglot.parse(sql, dialect=dialect) if statement is not None]
        if len(statements) != 1:
            raise ValueError("综合分析助手每个数据块只允许执行一条 SELECT/WITH 查询")
        statement = statements[0]
        _enforce_max_limit(statement)
        return statement.sql(dialect=dialect)
    except ValueError:
        raise
    except Exception as exc:
        if _contains_row_limit(sql):
            return sql
        if _supports_limit_wrapper(datasource):
            return f"select * from ({sql}) as analysis_query_limit limit {MAX_SQL_ROWS}"
        raise ValueError("SQL 解析失败，无法安全应用当前数据库的行数限制") from exc
    return sql


def _get_datasource(
    session: SessionDep, current_user: CurrentUser, datasource_id: int | None
) -> CoreDatasource:
    return resolve_datasource_context(
        session,
        current_user,
        datasource_id,
        require_explicit_when_multiple=True,
    ).datasource


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
    return _normalise_sql(apply_row_permission_filters(sql, datasource, filters), datasource)


def _prepare_sql_for_execution(
    llm,
    session: SessionDep,
    current_user: CurrentUser,
    datasource: CoreDatasource,
    raw_sql: str,
    allowed_tables: list[str],
) -> str:
    sql = _normalise_sql(raw_sql, datasource)
    _statements, tables_set, _permission_scope = validate_sql_scope(session, current_user, datasource, sql)
    tables = sorted(tables_set)
    unauthorized_tables = tables_set - set(allowed_tables)
    if unauthorized_tables:
        raise ValueError(f"SQL 包含无权限表：{', '.join(sorted(unauthorized_tables))}")
    sql = _apply_row_permissions(llm, session, current_user, datasource, sql, tables)
    rewritten_tables = validate_sql_table_scope(session, current_user, datasource, sql)
    unauthorized_tables = rewritten_tables - set(allowed_tables)
    if unauthorized_tables:
        raise ValueError(f"SQL 包含无权限表：{', '.join(sorted(unauthorized_tables))}")
    return sql


def _collect_metric_knowledge(
    session: SessionDep, datasource_id: int | None, question: str, current_user: CurrentUser | None = None
) -> str:
    """Reuse the project's existing semantic layer (术语 terminology + 数据训练 SQL 示例)
    so the assistant shares the SAME metric definitions as 智能报表, instead of letting
    the LLM re-invent 口径 every time."""
    knowledge, _terms, _examples = collect_metric_knowledge(session, datasource_id, question)
    return knowledge


def _collect_custom_agent_context(
    session: SessionDep,
    datasource_id: int | None,
    custom_prompt_id: int | None,
    current_user: CurrentUser | None,
) -> tuple[str, int | None]:
    if not custom_prompt_id:
        return "", None
    for custom_prompt_type in (
        CustomPromptTypeEnum.ANALYSIS,
        CustomPromptTypeEnum.GENERATE_SQL,
        CustomPromptTypeEnum.PREDICT_DATA,
    ):
        prompt_text, _prompt_list, ai_model_id = collect_custom_agent_context(
            session,
            datasource_id,
            custom_prompt_id,
            current_user,
            target_scope=CustomPromptTargetScopeEnum.ANALYSIS_ASSISTANT,
            custom_prompt_type=custom_prompt_type,
        )
        if prompt_text:
            return prompt_text, ai_model_id
    return "", None


def _knowledge_block(knowledge: str) -> str:
    if not knowledge or not knowledge.strip():
        return ""
    return (
        "统一业务口径（以下是本项目已配置的术语定义/同义词与标准 SQL 示例，"
        "是权威口径。生成 SQL 时必须优先遵循其中的指标定义、字段选择和计算算法；"
        "当它与你的默认理解冲突时，一律以此为准）：\n"
        f"{knowledge[:12000]}\n\n"
    )


def _custom_agent_block(custom_agent: str) -> str:
    if not custom_agent or not custom_agent.strip():
        return ""
    return (
        "自定义 Agent 补充设定（仅作为回答风格、分析侧重点、任务偏好和补充约束使用；"
        "不得替换或覆盖平台内置核心提示词、SQL 示例、术语口径、思考/输出格式、数据库 Schema、"
        "数据范围、权限、安全规则或 SQL 规范；冲突时以内置规则为准）：\n"
        f"{custom_agent[:6000]}\n\n"
    )


def _context_blocks(knowledge: str = "", custom_agent: str = "") -> str:
    return f"{_knowledge_block(knowledge)}{_custom_agent_block(custom_agent)}"


def _custom_agent_final_system_rules(custom_agent: str = "") -> str:
    if not custom_agent or not custom_agent.strip():
        return ""
    return (
        "\n\n自定义 Agent 最终回答强制规则：\n"
        "- 以下自定义 Agent 内容是本次最终回答的强制补充规范，尤其适用于统计口径、计算方法、评价规则、好坏判断口径和输出结构。\n"
        "- 如果自定义 Agent 中定义了某类统计的统一口径、公式、分子分母、好坏评价标准或风险/置信度规则，最终回答必须先识别命中的统计类型，再按这些规则评价。\n"
        "- 如果自定义 Agent 中定义了项目组自己的阈值分档、等级标准或好坏判断标准，最终回答必须计算对应指标的实际值，并按自定义阈值映射最终结论。例如遇到优秀/及格/差、A/B/C、高/中/低等分档规则时，最终的好坏、异常、风险等级和总结判断必须使用该尺度。\n"
        "- 项目组阈值和评价标准默认作为内部评判尺度，不要把自定义 Agent 的完整规则或阈值原文暴露给最终用户。最终回答只需要给出命中档位、实际值和必要判断理由；只有当用户明确询问“按什么标准/口径/阈值判断”时，才展开说明评价标准。\n"
        "- 不得使用模型默认经验替代项目组阈值；当自定义 Agent 已给出明确阈值时，最终评判必须以该阈值为准。若 rows 中缺少计算该阈值所需的分子或分母，必须说明无法评级以及需要补充的数据。\n"
        "- 如果自定义 Agent 要求显式输出模块标题，例如“命中统计类型 / 统计口径 / 计算方法 / 评价规范 / 数据事实 / 推测原因 / 风险等级与置信度 / 下一步建议”，最终回答必须保留这些模块，不得合并或省略。\n"
        "- 自定义 Agent 不能覆盖数据库 Schema、数据权限、SQL 安全规则和已配置的统一业务口径；如果发生冲突，以平台内置规则和项目统一业务口径为准。\n"
        "- 所有数字结论仍必须直接来自 rows；自定义评价规则只能决定如何计算、如何解释和如何判断好坏，不能允许编造数据。\n\n"
        f"{custom_agent[:6000]}"
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
        table_name = raw_table.strip()
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
            quoted_field = _quote_identifier(field, datasource)
            select_parts.append(f"{_normalise_aggregate_alias(f'MAX({quoted_field})', f'f{index}_max', datasource)}")
            select_parts.append(f"{_normalise_aggregate_alias(f'MIN({quoted_field})', f'f{index}_min', datasource)}")
        sql = f"SELECT {', '.join(select_parts)} FROM {_profile_table_reference(table_name, datasource)}"
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
    return _collect_date_bounds(datasource, schema)[:12000]


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
        (("预测", "预估", "forecast", "predict"), ("predicted", "forecast", "actual", "benchmark")),
        (("金额", "收入", "流水", "revenue", "amount", "income", "gmv"), ("revenue", "amount", "income", "gmv")),
        (("比率", "比例", "转化", "rate", "ratio", "conversion"), ("rate", "ratio", "conversion", "pct", "percent")),
        (("均值", "平均", "average", "avg", "mean"), ("avg", "average", "mean", "per_")),
        (("数量", "总数", "人数", "次数", "count", "total", "number"), ("count", "cnt", "total", "num", "users", "items", "orders")),
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
            if _field_matches(field, ("revenue", "amount", "income", "gmv"))
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
    if any(keyword in text for keyword in ("热力", "热力图", "矩阵", "二维分布", "heatmap", "matrix")):
        return "heatmap"
    if any(keyword in text for keyword in ("散点", "相关性", "关系分布", "scatter")):
        return "scatter"
    if any(keyword in text for keyword in ("流向", "路径流转", "来源去向", "桑基", "sankey")):
        return "sankey"
    if any(keyword in text for keyword in ("矩形树", "树图", "层级贡献", "treemap")):
        return "treemap"

    if _looks_like_time_field(x_field) or any(keyword in text for keyword in ("趋势", "变化", "按天", "每日", "time trend")):
        return "line"

    structure_keywords = ("结构", "分布", "占比", "构成", "来源", "类型", "类别", "分组")
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
        for keyword in ("倍率", "倍数", "增长率", "预测", "预估", "predicted", "forecast")
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
                if _field_matches(field, ("users", "user_count", "entity", "entity_count", "converted", "count"))
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
    rate_keywords = ("rate", "ratio", "conversion", "比率", "比例", "转化率", "流失率")
    pct_keywords = ("_pct", "percent", "百分")
    count_keywords = ("count", "cnt", "total", "num", "users", "items", "orders", "人数", "数量", "次数", "总数")
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
                    "比率、转化率、占比等字段应落在 0~100%（或 0~1）之间，"
                    "请检查是否分母错误、口径混用，或把累计值/计数当成了比率。"
                )
            if is_count and value < -1e-6:
                return (
                    f"字段 {field} 出现负的计数值 {value:.6g}；人数、订单数、次数等计数不可能为负，"
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
        if _field_matches(field, ("total", "users", "user_count", "items", "item_count", "count", "cnt"))
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
            "而不是同一分析对象内的 distinct entity id。请先按实体粒度生成每个对象的步骤完成状态，"
            "再按当前 schema 或语义层中的分组维度汇总数量和转化率。"
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

        y_field = _match_field(query.get("y"), fields)
        preferred = ("users", "user_count", "items", "item_count", "converted", "count", "cnt")
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
                        f"{label}={value:.6g} 出现倒挂；漏斗必须按同一分析对象集合的递进 distinct entity id 计算，"
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
                "请核对实际步骤、状态或事件枚举，并改用真实存在的递进步骤。"
            )
        return None
    return None


def _repair_sql(
    llm,
    question: str,
    raw_query: dict[str, Any],
    failed_sql: str,
    error: Exception,
    schema: str,
    sample_data: str,
    datasource: CoreDatasource,
    data_profile: str = "",
    knowledge: str = "",
    custom_agent: str = "",
) -> str:
    prompt = (
        f"用户问题：{question}\n"
        f"数据块标题：{raw_query.get('title')}\n"
        f"分析目的：{raw_query.get('purpose')}\n"
        f"原始 SQL：\n{failed_sql}\n\n"
        f"执行错误：\n{str(error)[:3000]}\n\n"
        f"{_context_blocks(knowledge, custom_agent)}"
        f"数据库 schema：\n{schema[:18000]}\n\n"
        f"样例数据：\n{sample_data[:6000]}\n\n"
        f"实际数据画像（必须优先使用这些真实枚举值，不要编造 event_name/status/属性值）：\n{data_profile[:12000]}"
    )
    text = _llm_text(
        llm,
        [
            SystemMessage(content=SQL_REPAIR_PROMPT + "\n\n" + _dialect_block(datasource)),
            HumanMessage(content=prompt),
        ],
    )
    try:
        data = _extract_json_object(text)
        repaired_sql = str(data.get("sql") or "")
    except Exception:
        repaired_sql = text
    return _normalise_sql(repaired_sql, datasource)


def _summarise_block(
    llm,
    question: str,
    block: dict[str, Any],
    knowledge: str = "",
    custom_agent: str = "",
) -> str:
    rows = block.get("data") or []
    if not rows:
        return "这组查询没有返回数据，暂时不能从该角度形成确定判断。"
    prompt = (
        f"用户问题：{question}\n"
        f"数据块标题：{block.get('title')}\n"
        f"分析目的：{block.get('purpose')}\n"
        f"{_context_blocks(knowledge, custom_agent)}"
        f"SQL：{block.get('sql')}\n"
        f"字段：{block.get('fields')}\n"
        f"查询结果样例：{_compact_rows(rows)}"
    )
    return _llm_text(
        llm,
        [SystemMessage(content=SUMMARY_PROMPT + _custom_agent_final_system_rules(custom_agent)),
         HumanMessage(content=prompt)],
    )


def _final_answer(
    llm,
    question: str,
    intro: str,
    blocks: list[dict[str, Any]],
    knowledge: str = "",
    custom_agent: str = "",
) -> str:
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
        f"{_context_blocks(knowledge, custom_agent)}"
        f"各数据块（含真实查询数据 rows，所有数字结论必须取自这些 rows，禁止编造或臆测未提供的数字）：\n"
        f"{payload[:16000]}"
    )
    return _llm_text(
        llm,
        [SystemMessage(content=FINAL_PROMPT + _custom_agent_final_system_rules(custom_agent)),
         HumanMessage(content=prompt)],
    )


def _initial_outline_messages(request: AnalysisAssistantRequest, custom_agent: str = "") -> list[BaseMessage]:
    question = request.messages[-1].content.strip()
    history = [
        {"role": item.role, "content": item.content}
        for item in request.messages[-6:-1]
        if item.content.strip()
    ]
    user_content = (
        f"页面上下文：{request.context or ''}\n"
        f"历史对话：{orjson.dumps(history).decode()}\n"
        f"用户问题：{question}\n\n"
        f"{_custom_agent_block(custom_agent)}"
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
    custom_agent: str = "",
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
        f"项目：{datasource.name}（{datasource.type} / {_database_name(datasource)}）\n"
        f"页面上下文：{context}\n"
        f"历史对话：{orjson.dumps(history).decode()}\n"
        f"用户问题：{question}\n\n"
        f"{_dialect_block(datasource)}"
        f"{_context_blocks(knowledge, custom_agent)}"
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
    custom_agent: str = "",
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
        f"项目：{datasource.name}（{datasource.type} / {_database_name(datasource)}）\n"
        f"页面上下文：{context}\n"
        f"历史对话：{orjson.dumps(history).decode()}\n"
        f"用户问题：{question}\n\n"
        f"{_dialect_block(datasource)}"
        f"{_context_blocks(knowledge, custom_agent)}"
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
async def chat(request: AnalysisAssistantRequest, current_user: CurrentUser, session: SessionDep):
    if not current_user:
        raise RuntimeError("Unauthorized")
    if not request.messages or not request.messages[-1].content.strip():
        raise RuntimeError("Question cannot be Empty")

    datasource = CoreDatasource.model_construct(
        **_get_datasource(session, current_user, request.datasource_id).model_dump()
    )
    custom_agent, custom_agent_model_id = _collect_custom_agent_context(
        session,
        datasource.id,
        request.custom_prompt_id,
        current_user,
    )
    llm = await _create_llm(custom_agent_model_id)

    def generate():
        question = request.messages[-1].content.strip()
        blocks: list[dict[str, Any]] = []
        try:
            outline_text = ""
            for chunk in llm.stream(_initial_outline_messages(request, custom_agent)):
                content = _chunk_text(chunk.content)
                if content:
                    outline_text += content
                    yield _sse({"type": "plan_delta", "content": content})
            if not outline_text.strip():
                yield _sse({"type": "plan_delta", "content": "我会先理解你的分析目标，再拆解关键维度并结合数据给出结论和建议。"})
            yield _trace("正在确认本次分析使用的业务口径。")
            yield _trace("正在结合当前业务数据，梳理可分析的关键维度。")
            schema, allowed_tables = get_table_schema(session, current_user, datasource, question, embedding=False)
            if not allowed_tables:
                raise RuntimeError("当前用户在该项目下没有可分析的数据表权限")
            sample_data = "" if is_normal_user(current_user) else get_tables_sample_data(session, current_user, datasource)
            data_profile = "" if is_normal_user(current_user) else _get_data_profile(datasource, schema)
            knowledge = _collect_metric_knowledge(session, datasource.id, question, current_user)
            if knowledge.strip():
                yield _trace("已加载本项目配置的统一业务口径（术语定义与标准 SQL 示例），将据此对齐指标算法。")
            if custom_agent.strip():
                yield _trace("已应用本次选择的自定义 Agent 补充设定，但核心 SQL 示例、权限和安全规则保持不变。")
            forecast_requested = _is_forecast_question(question)
            if forecast_requested:
                yield _trace("正在识别预测指标、目标人群和可用的历史观察窗口。")
                plan = _build_forecast_plan(
                    llm, request, schema, sample_data, datasource, data_profile, knowledge, custom_agent
                )
                yield _trace("预测方法和数据检查项已确定，下面按预测口径召回数据。")
            else:
                yield _trace("正在把分析框架拆成可执行的数据检查项。")
                plan = _build_plan(
                    llm, request, schema, sample_data, datasource, data_profile, knowledge, custom_agent
                )

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
                        repaired_sql = _repair_sql(
                            llm, question, raw_query, sql, first_error, schema, sample_data, datasource, data_profile, knowledge,
                            custom_agent
                        )
                        sql = _prepare_sql_for_execution(
                            llm, session, current_user, datasource, repaired_sql, allowed_tables
                        )
                        block["sql"] = sql
                        raw_query["sql"] = sql
                        result = exec_sql(datasource, sql, origin_column=False)
                    semantic_error = _semantic_validation_error(raw_query, result)
                    if semantic_error:
                        yield _trace("这个角度的数据一致性检查未通过，正在按项目口径重新校准。", block_id=block_id)
                        repaired_sql = _repair_sql(
                            llm, question, raw_query, sql, ValueError(semantic_error), schema, sample_data, datasource,
                            data_profile, knowledge, custom_agent
                        )
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
                    block["summary"] = _summarise_block(llm, question, block, knowledge, custom_agent)
                except Exception as query_error:
                    block["error"] = "数据计算失败"
                    block["error_detail"] = str(query_error)
                    block["summary"] = "这个角度的数据暂时无法稳定计算，已先跳过；其它维度的分析会继续完成。"

                blocks.append(block)
                yield _sse({"type": "block", "block": block})

            yield _trace("正在汇总各个角度的发现，形成最终判断和建议。")
            final = _final_answer(llm, question, intro, blocks, knowledge, custom_agent)
            yield _sse({"type": "final", "content": final})
            yield _sse({"type": "finish"})
        except Exception as e:
            yield _sse({"type": "error", "content": str(e), "detail": traceback.format_exc()[-4000:]})

    return StreamingResponse(generate(), media_type="text/event-stream")
