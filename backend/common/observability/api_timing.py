"""
脚本说明：记录接口级耗时日志，方便定位页面加载慢在哪个后端边界。
"""
from __future__ import annotations

import time
from typing import Any

from common.utils.utils import AppLogUtil


def log_api_timing(
    endpoint: str,
    *,
    started_at: float,
    tenant_id: Any = None,
    user_id: Any = None,
    **fields: Any,
) -> int:
    """
    是什么：用统一格式记录接口耗时日志。
    做了什么：输出接口名、租户、用户、业务字段和 elapsed_ms，不记录敏感配置或 SQL 全文。
    """
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    parts = [
        f"tenant_id={tenant_id}",
        f"user_id={user_id}",
    ]
    parts.extend(f"{key}={value}" for key, value in fields.items())
    parts.append(f"elapsed_ms={elapsed_ms}")
    AppLogUtil.info(f"{endpoint} finished: " + ", ".join(parts))
    return elapsed_ms
