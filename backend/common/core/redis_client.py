"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
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
    是什么：_quote 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return urllib.parse.quote(value or "", safe="")


def _format_host(host: str) -> str:
    """
    是什么：_format_host 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def build_redis_url() -> str:
    """
    是什么：build_redis_url 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存后端基础能力需要的东西，让后续流程能继续往下走。
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
    是什么：mask_redis_url 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
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
    是什么：get_redis_client 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力需要的数据找出来，整理成后面好用的样子。
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
    是什么：ping_redis 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    client = get_redis_client()
    return bool(await client.ping())


async def close_redis_client() -> None:
    """
    是什么：close_redis_client 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力这次处理做收尾，记录结果并关掉不再需要的资源。
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
    是什么：redis_key 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    suffix = ":".join(str(part).strip(":") for part in parts if part is not None and str(part) != "")
    return f"{settings.REDIS_KEY_PREFIX}:{suffix}" if suffix else settings.REDIS_KEY_PREFIX


def platform_redis_key(*parts: object) -> str:
    """
    是什么：platform_redis_key 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return redis_key("platform", *parts)


def tenant_redis_key(tenant_id: int | str | None, *parts: object) -> str:
    """
    是什么：tenant_redis_key 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if tenant_id in (None, ""):
        raise ValueError("Tenant context is required for tenant-scoped Redis keys")
    return redis_key("tenant", tenant_id, *parts)


def user_redis_key(tenant_id: int | str | None, user_id: int | str | None, *parts: object) -> str:
    """
    是什么：user_redis_key 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if user_id in (None, ""):
        raise ValueError("User context is required for user-scoped Redis keys")
    return tenant_redis_key(tenant_id, "user", user_id, *parts)


def datasource_redis_key(tenant_id: int | str | None, datasource_id: int | str | None, *parts: object) -> str:
    """
    是什么：datasource_redis_key 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
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
    是什么：redis_lock 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
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
    是什么：redis_health 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
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
