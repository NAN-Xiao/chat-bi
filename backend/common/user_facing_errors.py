"""
脚本说明：统一面向用户的错误分类，避免把业务可解释问题展示成系统 Bug。
"""
from __future__ import annotations

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
