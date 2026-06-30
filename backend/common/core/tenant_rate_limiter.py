import json
import time
from dataclasses import dataclass
from typing import Any

from redis.exceptions import RedisError

from common.core.config import settings
from common.core.redis_client import get_redis_client, tenant_redis_key
from common.utils.utils import AppLogUtil


WINDOW_SECONDS = 60


@dataclass
class TenantRateLimitState:
    allowed: bool
    action: str
    limit: int
    used: int
    remaining: int
    retry_after_seconds: int


_memory_counters: dict[tuple[int, str, int], int] = {}
_ACTION_LIMIT_KEYS = {
    "chat": "chat_requests_per_minute",
    "analysis": "analysis_requests_per_minute",
    "recommend": "recommend_requests_per_minute",
    "llm": "llm_requests_per_minute",
}


def _tenant_id(value: int | str | None) -> int:
    """
    是什么：_tenant_id 是 backend/common/core/tenant_rate_limiter.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _tenant_id 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    if value in (None, ""):
        raise ValueError("Tenant context is required")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Tenant context is required") from exc


def _window(now: int | None = None) -> tuple[int, int]:
    """
    是什么：_window 是 backend/common/core/tenant_rate_limiter.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _window 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    current = int(time.time()) if now is None else int(now)
    window_id = current // WINDOW_SECONDS
    retry_after = WINDOW_SECONDS - (current % WINDOW_SECONDS)
    return window_id, max(1, retry_after)


def _limit_for_action(action: str) -> int:
    """
    是什么：_limit_for_action 是 backend/common/core/tenant_rate_limiter.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _limit_for_action 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    normalized = str(action or "").strip().lower()
    if normalized == "chat":
        return settings.TENANT_CHAT_REQUESTS_PER_MINUTE
    if normalized == "analysis":
        return settings.TENANT_ANALYSIS_REQUESTS_PER_MINUTE
    if normalized == "recommend":
        return settings.TENANT_RECOMMEND_REQUESTS_PER_MINUTE
    return settings.TENANT_LLM_REQUESTS_PER_MINUTE


def _parse_plan_overrides() -> dict[str, Any]:
    """
    是什么：_parse_plan_overrides 是 backend/common/core/tenant_rate_limiter.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化核心配置和基础设施相关数据，生成后续流程可使用的结构。
    """
    raw = (settings.TENANT_RATE_LIMIT_PLAN_OVERRIDES or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        AppLogUtil.error("TENANT_RATE_LIMIT_PLAN_OVERRIDES is not valid JSON")
        return {}
    return data if isinstance(data, dict) else {}


def _plan_limit(plan: str | None, action: str) -> int | None:
    """
    是什么：_plan_limit 是 backend/common/core/tenant_rate_limiter.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _plan_limit 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    plan_key = (plan or "default").strip().lower() or "default"
    action_key = str(action or "").strip().lower() or "llm"
    limit_key = _ACTION_LIMIT_KEYS.get(action_key, _ACTION_LIMIT_KEYS["llm"])
    overrides = _parse_plan_overrides()
    plan_config = overrides.get(plan_key)
    if not isinstance(plan_config, dict):
        return None
    value = plan_config.get(limit_key)
    if value is None:
        value = plan_config.get(action_key)
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return None
    return limit if limit > 0 else None


def resolve_tenant_rate_limit(session: Any, tenant_id: int | str | None, action: str) -> int:
    """
    是什么：resolve_tenant_rate_limit 是 backend/common/core/tenant_rate_limiter.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 resolve_tenant_rate_limit 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    resolved_tenant_id = _tenant_id(tenant_id)
    plan = "default"
    try:
        from apps.system.models.tenant import TenantModel

        tenant = session.get(TenantModel, resolved_tenant_id) if session is not None else None
        if tenant and getattr(tenant, "plan", None):
            plan = str(tenant.plan)
    except Exception:
        AppLogUtil.exception("Could not resolve tenant plan for rate limit")

    override = _plan_limit(plan, action)
    return override if override is not None else _limit_for_action(action)


def _memory_prune(current_window: int) -> None:
    """
    是什么：_memory_prune 是 backend/common/core/tenant_rate_limiter.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _memory_prune 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    expired = [key for key in _memory_counters if key[2] < current_window]
    for key in expired:
        _memory_counters.pop(key, None)


def _state(action: str, limit: int, used: int, retry_after_seconds: int) -> TenantRateLimitState:
    """
    是什么：_state 是 backend/common/core/tenant_rate_limiter.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _state 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    return TenantRateLimitState(
        allowed=used <= limit,
        action=action,
        limit=limit,
        used=used,
        remaining=max(0, limit - used),
        retry_after_seconds=retry_after_seconds,
    )


async def consume_tenant_rate_limit(
    tenant_id: int | str | None,
    action: str,
    *,
    limit: int | None = None,
) -> TenantRateLimitState:
    """
    是什么：consume_tenant_rate_limit 是 backend/common/core/tenant_rate_limiter.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 consume_tenant_rate_limit 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    resolved_limit = _limit_for_action(action) if limit is None else int(limit)
    if not settings.TENANT_RATE_LIMIT_ENABLED or resolved_limit <= 0:
        return TenantRateLimitState(
            allowed=True,
            action=action,
            limit=resolved_limit,
            used=0,
            remaining=max(0, resolved_limit),
            retry_after_seconds=0,
        )

    resolved_tenant_id = _tenant_id(tenant_id)
    window_id, retry_after = _window()
    if (settings.CACHE_TYPE or "").lower() == "redis":
        try:
            client = get_redis_client()
            key = tenant_redis_key(resolved_tenant_id, "rate_limit", action, window_id)
            used = int(await client.incr(key))
            if used == 1:
                await client.expire(key, retry_after + 1)
            return _state(action, resolved_limit, used, retry_after)
        except RedisError:
            AppLogUtil.exception("Redis tenant rate limiter unavailable")
            if settings.APP_ENV == "production":
                raise RuntimeError("Tenant rate limiter unavailable")

    _memory_prune(window_id)
    key = (resolved_tenant_id, str(action), window_id)
    used = _memory_counters.get(key, 0) + 1
    _memory_counters[key] = used
    return _state(action, resolved_limit, used, retry_after)


def reset_memory_tenant_rate_limiter() -> None:
    """
    是什么：reset_memory_tenant_rate_limiter 是 backend/common/core/tenant_rate_limiter.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：删除或清理核心配置和基础设施相关数据、缓存或临时状态。
    """
    _memory_counters.clear()
