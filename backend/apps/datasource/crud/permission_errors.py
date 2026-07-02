"""
脚本说明：这个脚本封装数据源的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
import json
from typing import Any

from common.user_facing_errors import (
    PERMISSION_DENIED_AGENT_GUIDANCE,
    PERMISSION_DENIED_DISPLAY_MESSAGE,
    PERMISSION_DENIED_ERROR_TYPE,
    PERMISSION_DENIED_RESULT_MESSAGE,
    looks_like_permission_denied_error,
    permission_denied_data_result,
)
from common.utils.utils import AppLogUtil


def looks_like_permission_scope_error(message: str) -> bool:
    """
    是什么：looks_like_permission_scope_error 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return looks_like_permission_denied_error(message)


def permission_denied_result(message: str = PERMISSION_DENIED_DISPLAY_MESSAGE) -> dict:
    """
    是什么：permission_denied_result 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return permission_denied_data_result(message)


def audit_permission_denied(
        *,
        current_user: Any | None = None,
        datasource_id: Any | None = None,
        record_id: Any | None = None,
        operation: str,
        reason: str,
        tables: list[str] | set[str] | tuple[str, ...] | None = None,
        fields: list[str] | set[str] | tuple[str, ...] | None = None,
        rule_type: str | None = None,
) -> None:
    """
    是什么：记录权限拒绝的服务端审计信息。
    谁调用：用户侧脱敏前的权限失败路径。
    做了什么：保留 user/tenant/resource/原因，方便管理员排查；不返回给普通用户。
    """
    payload = {
        "event": "permission_denied",
        "operation": operation,
        "user_id": getattr(current_user, "id", None),
        "tenant_id": getattr(current_user, "tenant_id", None),
        "datasource_id": datasource_id,
        "record_id": record_id,
        "tables": sorted({str(item) for item in tables or [] if str(item).strip()}),
        "fields": sorted({str(item) for item in fields or [] if str(item).strip()}),
        "rule_type": rule_type,
        "reason": reason,
    }
    AppLogUtil.warning(
        "Permission denied audit: "
        + json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
    )
