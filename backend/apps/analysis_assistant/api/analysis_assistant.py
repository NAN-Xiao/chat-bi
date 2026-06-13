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
from apps.datasource.crud.datasource import get_table_schema, get_tables_sample_data
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import exec_sql
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
- 先用一段话说明你理解用户想分析什么，以及你会从哪些业务角度分析。
- 然后用 4 到 6 条编号步骤说明后续分析路径。
- 默认使用简体中文。
"""

CHART_TYPES = {"table", "bar", "column", "line", "pie"}
MAX_ANALYSIS_QUERIES = 4
MAX_SQL_ROWS = 200


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
      "chart_type": "line|column|bar|pie|table",
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
- 如果用户提到“最近一个月/近期”，优先以相关事实表里的最大日期为基准，而不是系统当前日期。
- 如果问题是归因类，至少覆盖趋势、结构拆解、关键分组/渠道/产品/服务器等角度中的两个。
"""


SUMMARY_PROMPT = """你是业务数据分析师。请根据用户问题和查询结果，总结这个数据块。

要求：
- 简体中文。
- 2 到 4 句话。
- 必须引用查询结果里能支撑的现象。
- 不要编造查询结果之外的数字。
"""


FINAL_PROMPT = """你是业务数据分析师。请基于多个数据块的总结，回答用户最初的问题。

输出结构：
1. 先给最终判断。
2. 再给关键依据。
3. 最后给 3 条以内改进建议。

要求简洁、可执行，不要编造没有数据支撑的信息。
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
    oid = current_user.oid if current_user.oid is not None else 1
    stmt = select(CoreDatasource).where(CoreDatasource.oid == oid)
    if datasource_id:
        stmt = stmt.where(CoreDatasource.id == datasource_id)
    datasource = session.exec(stmt.order_by(CoreDatasource.id)).first()
    if not datasource:
        raise RuntimeError("当前工作空间没有可用数据源")
    return datasource


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


def _build_chart_config(query: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    fields = [str(field) for field in result.get("fields") or []]
    rows = result.get("data") or []
    columns = [{"name": _field_label(field), "value": field} for field in fields]

    chart_type = str(query.get("chart_type") or "table").lower()
    if chart_type not in CHART_TYPES:
        chart_type = "table"
    if not rows or len(fields) < 2:
        chart_type = "table"

    numeric = _numeric_fields(fields, rows)
    x_field = _match_field(query.get("x"), fields)
    y_field = _match_field(query.get("y"), fields)
    series_field = _match_field(query.get("series"), fields)

    if not x_field:
        x_field = next((field for field in fields if field not in numeric), fields[0] if fields else None)
    if not y_field:
        y_field = next((field for field in numeric if field != x_field), None)

    if chart_type != "table" and (not x_field or not y_field):
        chart_type = "table"

    chart: dict[str, Any] = {
        "type": chart_type,
        "title": str(query.get("title") or "分析结果"),
        "columns": columns,
        "axis": {},
    }
    if series_field in numeric:
        series_field = None

    if chart_type != "table" and x_field and y_field:
        chart["axis"]["x"] = {"name": _field_label(x_field), "value": x_field}
        chart["axis"]["y"] = {"name": _field_label(y_field), "value": y_field}
        if chart_type != "pie" and series_field and series_field not in {x_field, y_field}:
            chart["axis"]["series"] = {"name": _field_label(series_field), "value": series_field}
    return chart


def _compact_rows(rows: list[dict[str, Any]], limit: int = 30) -> str:
    return orjson.dumps(rows[:limit]).decode()


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
    block_summaries = [
        {
            "title": block.get("title"),
            "purpose": block.get("purpose"),
            "summary": block.get("summary"),
            "row_count": len(block.get("data") or []),
        }
        for block in blocks
    ]
    prompt = (
        f"用户问题：{question}\n"
        f"问题理解：{intro}\n"
        f"数据块总结：{orjson.dumps(block_summaries).decode()}"
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


def _build_plan(llm, request: AnalysisAssistantRequest, schema: str, sample_data: str, datasource: CoreDatasource) -> dict[str, Any]:
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
        f"数据库 schema：\n{schema[:18000]}\n\n"
        f"样例数据：\n{sample_data[:6000]}"
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


@router.post("/chat", include_in_schema=False)
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
            schema, _tables = get_table_schema(session, current_user, datasource, question, embedding=False)
            sample_data = get_tables_sample_data(session, current_user, datasource)
            yield _trace("正在把分析框架拆成可执行的数据检查项。")
            plan = _build_plan(llm, request, schema, sample_data, datasource)

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
                    sql = _normalise_sql(str(raw_query.get("sql") or ""))
                    block["sql"] = sql
                    result = exec_sql(datasource, sql, origin_column=False)
                    block["fields"] = [str(field) for field in result.get("fields") or []]
                    block["data"] = result.get("data") or []
                    yield _trace("这个角度的数据已经整理好，正在提炼关键发现。", block_id=block_id)
                    block["chart"] = _build_chart_config(raw_query, result)
                    block["summary"] = _summarise_block(llm, question, block)
                except Exception as query_error:
                    block["error"] = str(query_error)
                    block["summary"] = f"这个角度暂时无法完成分析：{query_error}"

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
