from typing import Any


PERMISSION_DENIED_ERROR_TYPE = "permission_denied"
PERMISSION_DENIED_RESULT_MESSAGE = "当前用户对该项目的表或字段权限受限，无法返回这部分数据。"
PERMISSION_DENIED_AGENT_GUIDANCE = (
    "当前账号缺少本次查询或分析所需的部分数据权限。"
    "如果还有其它数据块成功返回，最终结论只能基于已返回数据，"
    "并提示用户可能因缺少受限数据而存在偏差；不要猜测或暴露具体受限表名、字段名、行权限条件或权限配置。"
)


def looks_like_permission_scope_error(message: str) -> bool:
    text = str(message or "").lower()
    return any(marker in text for marker in (
        "无权限",
        "权限",
        "select *",
        "unauthorized",
        "allowed tables",
        "表范围",
        "字段权限",
        "permission_scope",
        "permission denied",
        "insufficient privilege",
        "not permitted",
        "access denied",
    ))


def permission_denied_result(message: str = PERMISSION_DENIED_RESULT_MESSAGE) -> dict[str, Any]:
    return {
        "status": "failed",
        "error_type": PERMISSION_DENIED_ERROR_TYPE,
        "fields": [],
        "data": [],
        "message": message,
        "reason": message,
        "warning": message,
        "agent_guidance": PERMISSION_DENIED_AGENT_GUIDANCE,
    }
