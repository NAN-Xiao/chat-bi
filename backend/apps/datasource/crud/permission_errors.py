"""
脚本说明：这个脚本封装数据源的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
from common.user_facing_errors import (
    PERMISSION_DENIED_AGENT_GUIDANCE,
    PERMISSION_DENIED_DISPLAY_MESSAGE,
    PERMISSION_DENIED_ERROR_TYPE,
    PERMISSION_DENIED_RESULT_MESSAGE,
    permission_denied_data_result,
)


def looks_like_permission_scope_error(message: str) -> bool:
    """
    是什么：looks_like_permission_scope_error 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
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


def permission_denied_result(message: str = PERMISSION_DENIED_DISPLAY_MESSAGE) -> dict:
    """
    是什么：permission_denied_result 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return permission_denied_data_result(message)
