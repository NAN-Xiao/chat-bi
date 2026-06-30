import urllib.parse
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import LockError, RedisError

from common.core.config import settings
from common.utils.utils import AppLogUtil

_redis_client: redis.Redis | None = None
_redis_pool: ConnectionPool | None = None
_redis_url: str | None = None


def _quote(value: str | None) -> str:
    """
    是什么：_quote 是 backend/common/core/redis_client.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _quote 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    return urllib.parse.quote(value or "", safe="")


def _format_host(host: str) -> str:
    """
    是什么：_format_host 是 backend/common/core/redis_client.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化核心配置和基础设施相关数据，生成后续流程可使用的结构。
    """
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def build_redis_url() -> str:
    """
    是什么：build_redis_url 是 backend/common/core/redis_client.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装核心配置和基础设施相关对象和数据，并返回或写入对应状态。
    """
    if settings.SHUZHI_REDIS_URL:
        return settings.SHUZHI_REDIS_URL

    scheme = "rediss" if settings.REDIS_SSL else "redis"
    auth = ""
    if settings.REDIS_USERNAME and settings.REDIS_PASSWORD:
        auth = f"{_quote(settings.REDIS_USERNAME)}:{_quote(settings.REDIS_PASSWORD)}@"
    elif settings.REDIS_PASSWORD:
        auth = f":{_quote(settings.REDIS_PASSWORD)}@"

    host = _format_host(settings.SHUZHI_REDIS_HOST)
    port = settings.SHUZHI_REDIS_PORT
    return f"{scheme}://{auth}{host}:{port}/{settings.REDIS_DB}"


def mask_redis_url(url: str) -> str:
    """
    是什么：mask_redis_url 是 backend/common/core/redis_client.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 mask_redis_url 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    parsed = urllib.parse.urlsplit(url)
    if not parsed.password:
        return url

    username = urllib.parse.quote(parsed.username or "", safe="")
    auth = f"{username}:******@" if username else ":******@"
    netloc = f"{auth}{parsed.hostname or ''}"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def get_redis_client() -> redis.Redis:
    """
    是什么：get_redis_client 是 backend/common/core/redis_client.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询核心配置和基础设施相关数据，整理后返回给调用方。
    """
    global _redis_client, _redis_pool, _redis_url

    if _redis_client is not None:
        return _redis_client

    redis_url = build_redis_url()
    _redis_url = redis_url
    _redis_pool = ConnectionPool.from_url(
        redis_url,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
        health_check_interval=settings.REDIS_HEALTH_CHECK_INTERVAL,
    )
    _redis_client = redis.Redis(connection_pool=_redis_pool)
    return _redis_client


async def ping_redis() -> bool:
    """
    是什么：ping_redis 是 backend/common/core/redis_client.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 ping_redis 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    client = get_redis_client()
    return bool(await client.ping())


async def close_redis_client() -> None:
    """
    是什么：close_redis_client 是 backend/common/core/redis_client.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：完成或关闭核心配置和基础设施流程，释放资源并记录最终状态。
    """
    global _redis_client, _redis_pool, _redis_url

    if _redis_client is not None:
        await _redis_client.aclose()
    if _redis_pool is not None:
        await _redis_pool.aclose()

    _redis_client = None
    _redis_pool = None
    _redis_url = None


def redis_key(*parts: object) -> str:
    """
    是什么：redis_key 是 backend/common/core/redis_client.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 redis_key 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    suffix = ":".join(str(part).strip(":") for part in parts if part is not None and str(part) != "")
    return f"{settings.REDIS_KEY_PREFIX}:{suffix}" if suffix else settings.REDIS_KEY_PREFIX


def platform_redis_key(*parts: object) -> str:
    """
    是什么：platform_redis_key 是 backend/common/core/redis_client.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 platform_redis_key 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    return redis_key("platform", *parts)


def tenant_redis_key(tenant_id: int | str | None, *parts: object) -> str:
    """
    是什么：tenant_redis_key 是 backend/common/core/redis_client.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 tenant_redis_key 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    if tenant_id in (None, ""):
        raise ValueError("Tenant context is required for tenant-scoped Redis keys")
    return redis_key("tenant", tenant_id, *parts)


def user_redis_key(tenant_id: int | str | None, user_id: int | str | None, *parts: object) -> str:
    """
    是什么：user_redis_key 是 backend/common/core/redis_client.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 user_redis_key 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    if user_id in (None, ""):
        raise ValueError("User context is required for user-scoped Redis keys")
    return tenant_redis_key(tenant_id, "user", user_id, *parts)


def datasource_redis_key(tenant_id: int | str | None, datasource_id: int | str | None, *parts: object) -> str:
    """
    是什么：datasource_redis_key 是 backend/common/core/redis_client.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 datasource_redis_key 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    if datasource_id in (None, ""):
        raise ValueError("Datasource context is required for datasource-scoped Redis keys")
    return tenant_redis_key(tenant_id, "datasource", datasource_id, *parts)


@asynccontextmanager
async def redis_lock(
    name: str,
    *,
    timeout: int = 30,
    blocking_timeout: int = 5,
) -> AsyncIterator[None]:
    """
    是什么：redis_lock 是 backend/common/core/redis_client.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 redis_lock 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    client = get_redis_client()
    lock = client.lock(
        redis_key("lock", name),
        timeout=timeout,
        blocking_timeout=blocking_timeout,
    )
    acquired = await lock.acquire(blocking=True)
    if not acquired:
        raise TimeoutError(f"Could not acquire Redis lock: {name}")

    try:
        yield
    finally:
        try:
            await lock.release()
        except LockError:
            AppLogUtil.warning(f"Redis lock already released or expired: {name}")


async def redis_health() -> dict:
    """
    是什么：redis_health 是 backend/common/core/redis_client.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 redis_health 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    redis_url = _redis_url or build_redis_url()
    try:
        await ping_redis()
        return {
            "status": "ok",
            "type": "redis",
            "url": mask_redis_url(redis_url),
        }
    except RedisError as exc:
        return {
            "status": "error",
            "type": "redis",
            "url": mask_redis_url(redis_url),
            "message": str(exc),
        }
