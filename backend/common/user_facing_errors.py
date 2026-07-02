"""
脚本说明：统一面向用户的错误分类，避免把业务可解释问题展示成系统 Bug。
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


PERMISSION_DENIED_ERROR_TYPE = "permission_denied"
DATA_UNAVAILABLE_ERROR_TYPE = "data_unavailable"
DATASOURCE_UNAVAILABLE_ERROR_TYPE = "datasource_unavailable"
SQL_EXECUTION_ERROR_TYPE = "sql_execution_failed"
SYSTEM_ERROR_TYPE = "system_error"

BUSINESS_ERROR_TYPES = {
    PERMISSION_DENIED_ERROR_TYPE,
    DATA_UNAVAILABLE_ERROR_TYPE,
}

PERMISSION_DENIED_DISPLAY_MESSAGE = "没有查看权限"
PERMISSION_DENIED_RESULT_MESSAGE = "当前用户对该项目的表或字段权限受限，无法返回这部分数据。"
PERMISSION_DENIED_AGENT_GUIDANCE = (
    "当前账号缺少本次查询或分析所需的部分数据权限。"
    "如果还有其它数据块成功返回，最终结论只能基于已返回数据，"
    "并提示用户可能因缺少受限数据而存在偏差；不要猜测或暴露具体受限表名、字段名、行权限条件或权限配置。"
)

DATA_UNAVAILABLE_DISPLAY_MESSAGE = "当前数据源缺少本次问题所需的表、字段或埋点数据。"
DATA_UNAVAILABLE_AGENT_GUIDANCE = (
    "当前数据源缺少本次问题所需的数据结构、字段、事件或埋点。"
    "如果还有其它数据块成功返回，最终结论只能基于已返回数据；"
    "不要编造不存在的表、字段、事件、指标或数据结果。"
)

DATA_UNAVAILABLE_SQLSTATES = {
    "3F000",  # invalid_schema_name
    "42P01",  # undefined_table
    "42703",  # undefined_column
    "42S02",  # ODBC/base table not found
    "42S22",  # ODBC/column not found
}
PERMISSION_DENIED_SQLSTATES = {
    "28000",  # invalid authorization specification / access denied
    "42501",  # insufficient_privilege
}
DATA_UNAVAILABLE_ERRNOS = {
    1146,  # MySQL table doesn't exist
    1054,  # MySQL unknown column
    208,  # SQL Server invalid object name
    207,  # SQL Server invalid column name
    942,  # Oracle ORA-00942 table or view does not exist
    904,  # Oracle ORA-00904 invalid identifier
    60,  # ClickHouse unknown table
    47,  # ClickHouse unknown identifier
}
PERMISSION_DENIED_ERRNOS = {
    1044,  # MySQL access denied for database
    1142,  # MySQL command denied
    1227,  # MySQL access denied; need privilege
    229,  # SQL Server permission denied
    1031,  # Oracle ORA-01031 insufficient privileges
}

DATA_UNAVAILABLE_TEXT_PATTERNS = [
    r"\bundefinedtable\b",
    r"\bundefinedcolumn\b",
    r"\bno such table\b",
    r"\bno such column\b",
    r"\bunknown column\b",
    r"\binvalid column name\b",
    r"\binvalid object name\b",
    r"\brelation\s+.+\s+does not exist\b",
    r"\bcolumn\s+.+\s+does not exist\b",
    r"\btable\s+.+\s+does not exist\b",
    r"\bdoesn't exist\b",
    r"\bora-00942\b",
    r"\bora-00904\b",
    r"表[“\"]?[^”\"\s]+[”\"]?不存在",
    r"列[“\"]?[^”\"\s]+[”\"]?不存在",
    r"字段[“\"]?[^”\"\s]+[”\"]?不存在",
    r"无效的列名",
    r"对象名.+无效",
]
PERMISSION_DENIED_TEXT_MARKERS = (
    "无权",
    "无权限",
    "权限",
    "select *",
    "unauthorized",
    "allowed tables",
    "permission",
    "表范围",
    "字段权限",
    "permission_scope",
    "permission denied",
    "insufficient privilege",
    "not permitted",
    "access denied",
    "ora-01031",
)


@dataclass(frozen=True)
class ErrorClassification:
    error_type: str | None = None
    source: str = "unknown"
    code: str | int | None = None
    message: str = ""


def is_business_error_type(error_type: str | None) -> bool:
    """
    是什么：判断错误类型是否属于业务可解释问题。
    谁调用：前后端错误展示和 Agent 上下文整理。
    做了什么：把权限、数据缺失与真正系统失败分开。
    """
    return str(error_type or "") in BUSINESS_ERROR_TYPES


def agent_guidance_for_error_type(error_type: str | None) -> str | None:
    """
    是什么：根据标准错误类型返回 Agent 可遵循的说明。
    谁调用：把失败数据块传回大模型生成解释时使用。
    做了什么：避免把权限问题和数据缺失问题混成同一种回答。
    """
    if error_type == PERMISSION_DENIED_ERROR_TYPE:
        return PERMISSION_DENIED_AGENT_GUIDANCE
    if error_type == DATA_UNAVAILABLE_ERROR_TYPE:
        return DATA_UNAVAILABLE_AGENT_GUIDANCE
    return None


def _walk_error_chain(error: Any):
    seen: set[int] = set()
    stack = [error]
    while stack:
        item = stack.pop(0)
        if item is None:
            continue
        item_id = id(item)
        if item_id in seen:
            continue
        seen.add(item_id)
        yield item
        for attr in ("orig", "original", "__cause__", "__context__"):
            next_item = getattr(item, attr, None)
            if next_item is not None:
                stack.append(next_item)


def _candidate_sqlstates(error: Any) -> list[str]:
    states: list[str] = []
    for item in _walk_error_chain(error):
        for attr in ("sqlstate", "pgcode"):
            value = getattr(item, attr, None)
            if value:
                states.append(str(value).upper())
        diag = getattr(item, "diag", None)
        value = getattr(diag, "sqlstate", None) if diag is not None else None
        if value:
            states.append(str(value).upper())
        for arg in getattr(item, "args", ()) or ():
            if isinstance(arg, str):
                for match in re.finditer(r"\b[0-9A-Z]{5}\b", arg.upper()):
                    states.append(match.group(0))
    return list(dict.fromkeys(states))


def _candidate_errnos(error: Any) -> list[int]:
    numbers: list[int] = []
    for item in _walk_error_chain(error):
        for attr in ("errno", "number", "code"):
            value = getattr(item, attr, None)
            if isinstance(value, int):
                numbers.append(value)
            elif isinstance(value, str) and value.isdigit():
                numbers.append(int(value))
        for arg in getattr(item, "args", ()) or ():
            if isinstance(arg, int):
                numbers.append(arg)
            elif isinstance(arg, str):
                for pattern in (r"\bORA-(\d{5})\b", r"\bError\s+(\d{2,5})\b", r"\[(\d{2,5})\]"):
                    for match in re.finditer(pattern, arg, flags=re.IGNORECASE):
                        try:
                            numbers.append(int(match.group(1)))
                        except (TypeError, ValueError):
                            pass
    return list(dict.fromkeys(numbers))


def _message_for_error(error: Any) -> str:
    if isinstance(error, str):
        return error
    messages = []
    for item in _walk_error_chain(error):
        text = str(item or "")
        if text and text not in messages:
            messages.append(text)
    return " | ".join(messages)


def _matches_data_unavailable_text(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in DATA_UNAVAILABLE_TEXT_PATTERNS)


def _matches_permission_denied_text(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(marker in lowered for marker in PERMISSION_DENIED_TEXT_MARKERS)


def classify_error(error: Any) -> ErrorClassification:
    """
    是什么：统一把底层异常或历史错误文本分类成平台标准错误类型。
    谁调用：SQL 执行、工作流和兼容旧入口的 looks_like_* 函数。
    做了什么：优先使用 SQLSTATE/errno 等结构化错误码，文本正则只作为 fallback。
    """
    message = _message_for_error(error)
    for state in _candidate_sqlstates(error):
        if state in DATA_UNAVAILABLE_SQLSTATES:
            return ErrorClassification(DATA_UNAVAILABLE_ERROR_TYPE, "sqlstate", state, message)
        if state in PERMISSION_DENIED_SQLSTATES:
            return ErrorClassification(PERMISSION_DENIED_ERROR_TYPE, "sqlstate", state, message)
    for errno in _candidate_errnos(error):
        if errno in DATA_UNAVAILABLE_ERRNOS:
            return ErrorClassification(DATA_UNAVAILABLE_ERROR_TYPE, "errno", errno, message)
        if errno in PERMISSION_DENIED_ERRNOS:
            return ErrorClassification(PERMISSION_DENIED_ERROR_TYPE, "errno", errno, message)
    if _matches_permission_denied_text(message):
        return ErrorClassification(PERMISSION_DENIED_ERROR_TYPE, "text", None, message)
    if _matches_data_unavailable_text(message) or looks_like_data_unavailable_business_message(message):
        return ErrorClassification(DATA_UNAVAILABLE_ERROR_TYPE, "text", None, message)
    return ErrorClassification(None, "unknown", None, message)


def error_type_for(error: Any) -> str | None:
    return classify_error(error).error_type


def looks_like_permission_denied_error(error: Any) -> bool:
    return error_type_for(error) == PERMISSION_DENIED_ERROR_TYPE


def looks_like_data_unavailable_error(error: Any) -> bool:
    return error_type_for(error) == DATA_UNAVAILABLE_ERROR_TYPE


def failed_data_result(
    *,
    error_type: str,
    message: str,
    reason: str | None = None,
    warning: str | None = None,
    agent_guidance: str | None = None,
) -> dict[str, Any]:
    """
    是什么：生成统一的失败数据块结构。
    谁调用：SQL 查询、Smart Q&A、分析助手等需要保存失败数据块时调用。
    做了什么：保证 status/error_type/message/reason 等字段一致。
    """
    display_message = message or ""
    result: dict[str, Any] = {
        "status": "failed",
        "error_type": error_type,
        "fields": [],
        "data": [],
        "message": display_message,
        "reason": reason or display_message,
        "warning": warning or display_message,
    }
    guidance = agent_guidance or agent_guidance_for_error_type(error_type)
    if guidance:
        result["agent_guidance"] = guidance
    return result


def permission_denied_data_result(message: str = PERMISSION_DENIED_DISPLAY_MESSAGE) -> dict[str, Any]:
    """
    是什么：生成权限受限的标准失败数据块。
    谁调用：权限校验失败路径。
    做了什么：隐藏具体受限资源，只保留用户可理解的权限提示。
    """
    reason = PERMISSION_DENIED_RESULT_MESSAGE if message == PERMISSION_DENIED_DISPLAY_MESSAGE else message
    return failed_data_result(
        error_type=PERMISSION_DENIED_ERROR_TYPE,
        message=message,
        reason=reason,
        agent_guidance=PERMISSION_DENIED_AGENT_GUIDANCE,
    )


def data_unavailable_data_result(message: str = DATA_UNAVAILABLE_DISPLAY_MESSAGE) -> dict[str, Any]:
    """
    是什么：生成数据/Schema/埋点不可用的标准失败数据块。
    谁调用：缺表、缺字段、缺事件或缺埋点路径。
    做了什么：把这类业务问题与真正的 SQL 执行 Bug 分开。
    """
    return failed_data_result(
        error_type=DATA_UNAVAILABLE_ERROR_TYPE,
        message=message or DATA_UNAVAILABLE_DISPLAY_MESSAGE,
        agent_guidance=DATA_UNAVAILABLE_AGENT_GUIDANCE,
    )


def data_unavailable_error_payload(message: str = DATA_UNAVAILABLE_DISPLAY_MESSAGE) -> dict[str, Any]:
    """
    是什么：生成可保存到 record.error 的数据不可用错误载荷。
    谁调用：工作流兜底错误格式化。
    做了什么：不携带 traceback，前端会按业务提示展示。
    """
    return {
        "error_type": DATA_UNAVAILABLE_ERROR_TYPE,
        "type": DATA_UNAVAILABLE_ERROR_TYPE,
        "message": message or DATA_UNAVAILABLE_DISPLAY_MESSAGE,
    }


def looks_like_data_unavailable_business_message(message: str) -> bool:
    """
    是什么：识别旧数据或模型文本里的数据不可用业务提示。
    谁调用：兼容未带 error_type 的历史错误和 LLM success=false 消息。
    做了什么：只匹配明确的数据/Schema/埋点缺失语义，避免误伤权限错误。
    """
    text = str(message or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in (
        "permission",
        "unauthorized",
        "access denied",
        "无权",
        "权限",
    )):
        return False

    markers = [
        "当前数据源缺少本次问题所需",
        "当前数据源缺少所需",
        "当前数据源没有",
        "当前数据库 schema 中不存在",
        "schema 中不存在",
        "缺少所需表",
        "缺少所需字段",
        "缺少所需埋点",
        "缺少埋点",
        "埋点不存在",
        "事件不存在",
        "没有这个数据",
        "没有对应埋点",
        "没有该埋点",
        "table is not present in schema",
        "field is not present in schema",
        "missing required table",
        "missing required field",
        "missing required event",
        "missing tracking event",
    ]
    if any(marker in lowered for marker in markers):
        return True

    patterns = [
        r"(表|字段|列|埋点|事件).{0,30}(不存在|缺失|缺少)",
        r"(缺少|没有).{0,30}(表|字段|列|埋点|事件|数据)",
    ]
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
