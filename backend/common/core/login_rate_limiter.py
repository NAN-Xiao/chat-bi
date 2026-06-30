import hashlib
import time
from dataclasses import dataclass

from redis.exceptions import RedisError
from starlette.requests import Request

from common.core.config import settings
from common.core.redis_client import get_redis_client, platform_redis_key
from common.utils.utils import AppLogUtil


@dataclass
class LoginLimitState:
    locked: bool
    attempts: int = 0
    retry_after_seconds: int = 0


_memory_failures: dict[str, tuple[int, float]] = {}
_memory_locks: dict[str, float] = {}


def _client_ip(request: Request | None) -> str:
    """
    是什么：_client_ip 是 backend/common/core/login_rate_limiter.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _client_ip 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    if not request:
        return "unknown"
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    if request.client:
        return request.client.host
    return "unknown"


def login_limit_identity(account: str | None, request: Request | None) -> str:
    """
    是什么：login_limit_identity 是 backend/common/core/login_rate_limiter.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 login_limit_identity 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    raw = f"{_client_ip(request)}:{(account or '').strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _memory_prune(now: float) -> None:
    """
    是什么：_memory_prune 是 backend/common/core/login_rate_limiter.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _memory_prune 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    expired_locks = [key for key, expires_at in _memory_locks.items() if expires_at <= now]
    for key in expired_locks:
        _memory_locks.pop(key, None)
    expired_failures = [
        key
        for key, (_count, expires_at) in _memory_failures.items()
        if expires_at <= now
    ]
    for key in expired_failures:
        _memory_failures.pop(key, None)


async def _redis_lock_state(identity: str) -> LoginLimitState | None:
    """
    是什么：_redis_lock_state 是 backend/common/core/login_rate_limiter.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _redis_lock_state 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    if (settings.CACHE_TYPE or "").lower() != "redis":
        return None
    client = get_redis_client()
    lock_key = platform_redis_key("auth", "login", "lock", identity)
    failure_key = platform_redis_key("auth", "login", "fail", identity)
    retry_after = await client.ttl(lock_key)
    attempts = int(await client.get(failure_key) or 0)
    if retry_after and retry_after > 0:
        return LoginLimitState(True, attempts=attempts, retry_after_seconds=retry_after)
    return LoginLimitState(False, attempts=attempts)


async def get_login_limit_state(identity: str) -> LoginLimitState:
    """
    是什么：get_login_limit_state 是 backend/common/core/login_rate_limiter.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询核心配置和基础设施相关数据，整理后返回给调用方。
    """
    if not settings.LOGIN_RATE_LIMIT_ENABLED:
        return LoginLimitState(False)
    try:
        redis_state = await _redis_lock_state(identity)
        if redis_state is not None:
            return redis_state
    except RedisError:
        AppLogUtil.exception("Redis login rate limiter unavailable, falling back to process memory")

    now = time.time()
    _memory_prune(now)
    lock_expires_at = _memory_locks.get(identity)
    attempts = _memory_failures.get(identity, (0, 0))[0]
    if lock_expires_at and lock_expires_at > now:
        return LoginLimitState(
            True,
            attempts=attempts,
            retry_after_seconds=max(1, int(lock_expires_at - now)),
        )
    return LoginLimitState(False, attempts=attempts)


async def record_login_failure(identity: str) -> LoginLimitState:
    """
    是什么：record_login_failure 是 backend/common/core/login_rate_limiter.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 record_login_failure 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    if not settings.LOGIN_RATE_LIMIT_ENABLED:
        return LoginLimitState(False)
    try:
        if (settings.CACHE_TYPE or "").lower() == "redis":
            client = get_redis_client()
            failure_key = platform_redis_key("auth", "login", "fail", identity)
            lock_key = platform_redis_key("auth", "login", "lock", identity)
            attempts = int(await client.incr(failure_key))
            if attempts == 1:
                await client.expire(failure_key, settings.LOGIN_FAILURE_WINDOW_SECONDS)
            if attempts >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
                await client.set(lock_key, "1", ex=settings.LOGIN_LOCKOUT_SECONDS)
                return LoginLimitState(
                    True,
                    attempts=attempts,
                    retry_after_seconds=settings.LOGIN_LOCKOUT_SECONDS,
                )
            return LoginLimitState(False, attempts=attempts)
    except RedisError:
        AppLogUtil.exception("Redis login rate limiter unavailable, falling back to process memory")

    now = time.time()
    _memory_prune(now)
    attempts, expires_at = _memory_failures.get(identity, (0, 0))
    if expires_at <= now:
        attempts = 0
        expires_at = now + settings.LOGIN_FAILURE_WINDOW_SECONDS
    attempts += 1
    _memory_failures[identity] = (attempts, expires_at)
    if attempts >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
        lock_expires_at = now + settings.LOGIN_LOCKOUT_SECONDS
        _memory_locks[identity] = lock_expires_at
        return LoginLimitState(
            True,
            attempts=attempts,
            retry_after_seconds=settings.LOGIN_LOCKOUT_SECONDS,
        )
    return LoginLimitState(False, attempts=attempts)


async def clear_login_failures(identity: str) -> None:
    """
    是什么：clear_login_failures 是 backend/common/core/login_rate_limiter.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：删除或清理核心配置和基础设施相关数据、缓存或临时状态。
    """
    if not settings.LOGIN_RATE_LIMIT_ENABLED:
        return
    try:
        if (settings.CACHE_TYPE or "").lower() == "redis":
            client = get_redis_client()
            await client.delete(
                platform_redis_key("auth", "login", "fail", identity),
                platform_redis_key("auth", "login", "lock", identity),
            )
            return
    except RedisError:
        AppLogUtil.exception("Redis login rate limiter cleanup failed")
    _memory_failures.pop(identity, None)
    _memory_locks.pop(identity, None)


def reset_memory_login_rate_limiter() -> None:
    """
    是什么：reset_memory_login_rate_limiter 是 backend/common/core/login_rate_limiter.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：删除或清理核心配置和基础设施相关数据、缓存或临时状态。
    """
    _memory_failures.clear()
    _memory_locks.clear()
