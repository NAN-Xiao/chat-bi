"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import asyncio
import random
import re
from functools import partial, wraps
from inspect import signature
from typing import Any, Dict, Optional, Tuple

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.coder import JsonCoder
from redis.exceptions import RedisError
from sqlalchemy import event
from sqlmodel import Session

from common.core.config import settings
from common.core.redis_client import (
    build_redis_url,
    close_redis_client,
    get_redis_client,
    mask_redis_url,
    ping_redis,
    platform_redis_key,
    redis_lock,
    redis_health,
)
from common.utils.utils import AppLogUtil

_CACHE_TTL_JITTER_RATIO = 0.1
_SQLALCHEMY_SESSION_MODULES = {"sqlmodel.orm.session", "sqlalchemy.orm.session"}
_LOCAL_CACHE_REBUILD_LOCKS: dict[str, asyncio.Lock] = {}


def _cache_part(value: Any) -> str:
    """
    是什么：_cache_part 把缓存 key 片段规整成字符串。
    谁调用：缓存 key 构建逻辑会调用它。
    做了什么：优先使用枚举等对象的 __str__，并去掉首尾冒号，避免拼出重复分隔符。
    """
    return str(value).strip(":")


def _cache_namespace(namespace: Any) -> str:
    """
    是什么：_cache_namespace 规整缓存命名空间。
    谁调用：缓存读取和清理都会调用它。
    做了什么：保持业务命名空间稳定，同时兼容 Enum 入参。
    """
    return _cache_part(namespace) if namespace else ""


def _prefixed_cache_key(key: str) -> str:
    """
    是什么：_prefixed_cache_key 给自定义 key 补上 FastAPICache 的全局前缀。
    谁调用：缓存读取和清理都会调用它。
    做了什么：因为自定义 key_builder 会绕过 fastapi-cache 默认拼接，这里显式补齐 prefix。
    """
    prefix = FastAPICache.get_prefix()
    return platform_redis_key("cache", prefix, key) if prefix else platform_redis_key("cache", key)


def _jitter_expire(expire: int | None) -> int | None:
    """
    是什么：_jitter_expire 给缓存 TTL 加少量随机抖动。
    谁调用：缓存装饰器每次写缓存前会调用它。
    做了什么：降低大量 key 同时过期造成雪崩的概率。
    """
    if expire is None or expire <= 0:
        return expire
    spread = max(1, int(expire * _CACHE_TTL_JITTER_RATIO))
    return max(1, expire + random.randint(-spread, spread))


def _is_session_like(value: Any) -> bool:
    """
    是什么：_is_session_like 判断入参是否是 SQLAlchemy/SQLModel Session。
    谁调用：缓存清理逻辑用它找到当前事务。
    做了什么：避免把 SQLAlchemy 作为严格运行时依赖写死到业务签名里。
    """
    if isinstance(value, Session):
        return True
    cls = value.__class__
    return cls.__name__ == "Session" and cls.__module__ in _SQLALCHEMY_SESSION_MODULES


def _find_session(func: Any, args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Any | None:
    """
    是什么：_find_session 从被装饰函数实参里找到数据库 Session。
    谁调用：clear_cache 在成功写库后注册 after_commit 清理。
    做了什么：优先按函数签名找 session 参数，找不到再扫描实参。
    """
    try:
        bound_args = signature(func).bind_partial(*args, **kwargs)
        bound_args.apply_defaults()
        for name in ("session", "db", "db_session"):
            value = bound_args.arguments.get(name)
            if value is not None and _is_session_like(value):
                return value
        for value in bound_args.arguments.values():
            if _is_session_like(value):
                return value
    except Exception:
        for value in (*args, *kwargs.values()):
            if _is_session_like(value):
                return value
    return None


async def _clear_backend_keys(cache_keys: list[str]) -> None:
    """
    是什么：_clear_backend_keys 删除指定缓存 key。
    谁调用：clear_cache 的直接清理和 after_commit 回调都会调用它。
    做了什么：直接 delete，不再先 get；Redis 异常只记录，避免缓存故障拖垮主流程。
    """
    if not cache_keys:
        return
    try:
        backend = FastAPICache.get_backend()
    except (AssertionError, AttributeError) as exc:
        AppLogUtil.warning(f"缓存后端不可用，跳过缓存清理: {exc}")
        return

    for cache_key in cache_keys:
        try:
            deleted = await backend.clear(key=cache_key)
            if deleted:
                AppLogUtil.debug(f"Cache cleared: {cache_key}")
        except RedisError as exc:
            AppLogUtil.warning(f"Redis cache clear failed for [{cache_key}]: {exc}")
        except Exception as exc:
            AppLogUtil.warning(f"Cache clear failed for [{cache_key}]: {exc}")


async def _read_backend_key(cache_key: str) -> tuple[bool, Any]:
    """
    是什么：_read_backend_key 从缓存后端读取并反序列化一个 key。
    谁调用：cache 装饰器。
    做了什么：缓存异常时降级为 miss，不让 Redis 故障拖垮业务读取。
    """
    try:
        backend = FastAPICache.get_backend()
        cached = await backend.get(cache_key)
        if cached is None:
            return False, None
        return True, FastAPICache.get_coder().decode(cached)
    except RedisError as exc:
        AppLogUtil.warning(f"Redis cache read failed for [{cache_key}]: {exc}")
    except Exception as exc:
        AppLogUtil.warning(f"Cache read failed for [{cache_key}]: {exc}")
    return False, None


async def _write_backend_key(cache_key: str, value: Any, expire: int | None) -> None:
    """
    是什么：_write_backend_key 序列化并写入一个缓存 key。
    谁调用：cache 装饰器在回源成功后调用。
    做了什么：写缓存异常只记录告警，不影响主流程返回。
    """
    try:
        backend = FastAPICache.get_backend()
        payload = FastAPICache.get_coder().encode(value)
        await backend.set(cache_key, payload, _jitter_expire(expire))
    except RedisError as exc:
        AppLogUtil.warning(f"Redis cache write failed for [{cache_key}]: {exc}")
    except Exception as exc:
        AppLogUtil.warning(f"Cache write failed for [{cache_key}]: {exc}")


def _local_rebuild_lock(cache_key: str) -> asyncio.Lock:
    """
    是什么：_local_rebuild_lock 获取进程内缓存重建锁。
    谁调用：内存缓存或非 Redis 缓存的单飞逻辑。
    做了什么：同一进程内同一 key 的并发 miss 只允许一个请求回源。
    """
    lock = _LOCAL_CACHE_REBUILD_LOCKS.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCAL_CACHE_REBUILD_LOCKS[cache_key] = lock
    return lock


async def _load_with_single_flight(
    cache_key: str,
    expire: int | None,
    loader: Any,
) -> Any:
    """
    是什么：_load_with_single_flight 缓存 miss 后用单飞方式回源。
    谁调用：cache 装饰器。
    做了什么：拿锁后再次检查缓存，避免热点 key 过期时所有并发请求同时打 DB。
    """
    async def load_and_cache() -> Any:
        result = await loader()
        await _write_backend_key(cache_key, result, expire)
        return result

    if (settings.CACHE_TYPE or "").lower() == "redis":
        try:
            async with redis_lock(f"app-cache:{cache_key}", timeout=30, blocking_timeout=5):
                hit, cached = await _read_backend_key(cache_key)
                if hit:
                    return cached
                return await load_and_cache()
        except (RedisError, TimeoutError) as exc:
            AppLogUtil.warning(f"Cache rebuild lock failed for [{cache_key}], fallback to direct load: {exc}")
            return await load_and_cache()

    async with _local_rebuild_lock(cache_key):
        hit, cached = await _read_backend_key(cache_key)
        if hit:
            return cached
        return await load_and_cache()


def _run_async_clear(cache_keys: list[str], loop: asyncio.AbstractEventLoop | None = None) -> None:
    """
    是什么：_run_async_clear 在同步 after_commit 事件里触发异步缓存清理。
    谁调用：SQLAlchemy Session after_commit 回调。
    做了什么：优先把任务挂到当前事件循环；没有运行中的事件循环时用 asyncio.run。
    """
    if loop and loop.is_running():
        loop.call_soon_threadsafe(lambda: loop.create_task(_clear_backend_keys(cache_keys)))
        return

    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_clear_backend_keys(cache_keys))
        return
    running_loop.create_task(_clear_backend_keys(cache_keys))


def _register_after_commit_clear(session: Any, cache_keys: list[str]) -> bool:
    """
    是什么：_register_after_commit_clear 注册事务提交后的缓存清理。
    谁调用：clear_cache 包装器在原函数成功后调用。
    做了什么：把清理推迟到 DB commit 之后，减少旧数据回填缓存的竞态窗口。
    """
    if session is None:
        return False
    try:
        if session.in_transaction():
            loop = asyncio.get_running_loop()
            event.listen(
                session,
                "after_commit",
                lambda _session: _run_async_clear(cache_keys, loop),
                once=True,
            )
            return True
    except Exception as exc:
        AppLogUtil.warning(f"注册 after_commit 缓存清理失败，将直接清理缓存: {exc}")
    return False


def custom_key_builder(
    func: Any,
    namespace: str = "",
    *,
    args: Tuple[Any, ...] = (),
    kwargs: Dict[str, Any],
    cacheName: str,
    keyExpression: Optional[str] = None,
) -> str | list[str]:
    """
    是什么：custom_key_builder 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        key_parts = [_cache_part(part) for part in (namespace, cacheName) if part]
        base_key = ":".join(key_parts) + ":"

        if keyExpression:
            sig = signature(func)
            bound_args = sig.bind_partial(*args, **kwargs)
            bound_args.apply_defaults()

            # 支持位置参数 args[0] 格式
            if keyExpression.startswith("args["):
                if match := re.match(r"args\[(\d+)\]", keyExpression):
                    index = int(match.group(1))
                    value = bound_args.args[index]
                    if isinstance(value, list):
                        return [f"{base_key}{v}" for v in value]
                    return f"{base_key}{value}"

            # 支持属性路径格式
            parts = keyExpression.split('.')
            if not bound_args.arguments.get(parts[0]):
                return f"{base_key}{parts[0]}"
            value = bound_args.arguments[parts[0]]
            for part in parts[1:]:
                value = getattr(value, part)
            if isinstance(value, list):
                return [f"{base_key}{v}" for v in value]
            return f"{base_key}{value}"

        # 默认使用第一个参数作为键
        return f"{base_key}{args[0] if args else 'default'}"

    except Exception as e:
        AppLogUtil.error(f"Key builder error: {str(e)}")
        raise ValueError(f"Invalid cache key generation: {e}") from e

def cache(
    expire: int = 60 * 60 * 24,
    namespace: str = "",
    *,
    cacheName: str,  # 必须提供缓存名称
    keyExpression: Optional[str] = None,
):
    """
    是什么：cache 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    def decorator(func):
        # 预先生成键构建器
        """
        是什么：decorator 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
        谁调用：外层函数 cache 跑到对应步骤时会调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        used_key_builder = partial(
            custom_key_builder,
            cacheName=cacheName,
            keyExpression=keyExpression
        )

        @wraps(func)
        async def wrapper(*args, **kwargs):
            """
            是什么：wrapper 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
            谁调用：外层函数 decorator 跑到对应步骤时会调用它。
            做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
            """
            if not settings.CACHE_TYPE or settings.CACHE_TYPE.lower() == "none" or not is_cache_initialized():
                return await func(*args, **kwargs)
            # 生成缓存键
            cache_key = used_key_builder(
                func=func,
                namespace=_cache_namespace(namespace),
                args=args,
                kwargs=kwargs
            )
            if isinstance(cache_key, list):
                raise ValueError("cache decorator requires a single cache key")
            full_cache_key = _prefixed_cache_key(cache_key)

            hit, cached = await _read_backend_key(full_cache_key)
            if hit:
                return cached

            async def load_value():
                return await func(*args, **kwargs)

            return await _load_with_single_flight(full_cache_key, expire, load_value)

        return wrapper
    return decorator

def clear_cache(
    namespace: str = "",
    *,
    cacheName: str,
    keyExpression: Optional[str] = None,
):
    """
    是什么：clear_cache 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力不再需要的数据、缓存或临时内容清理掉。
    """
    def decorator(func):
        """
        是什么：decorator 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
        谁调用：外层函数 clear_cache 跑到对应步骤时会调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        @wraps(func)
        async def wrapper(*args, **kwargs):
            """
            是什么：wrapper 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
            谁调用：外层函数 decorator 跑到对应步骤时会调用它。
            做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
            """
            if not settings.CACHE_TYPE or settings.CACHE_TYPE.lower() == "none" or not is_cache_initialized():
                return await func(*args, **kwargs)
            cache_key = custom_key_builder(
                func=func,
                namespace=_cache_namespace(namespace),
                args=args,
                kwargs=kwargs,
                cacheName=cacheName,
                keyExpression=keyExpression,
            )
            key_list = cache_key if isinstance(cache_key, list) else [cache_key]
            prefixed_key_list = [_prefixed_cache_key(temp_cache_key) for temp_cache_key in key_list]
            result = await func(*args, **kwargs)
            session = _find_session(func, args, kwargs)
            if not _register_after_commit_clear(session, prefixed_key_list):
                await _clear_backend_keys(prefixed_key_list)
            return result

        return wrapper
    return decorator


async def init_app_cache():
    """
    是什么：init_app_cache 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存后端基础能力需要的东西，让后续流程能继续往下走。
    """
    cache_type: str = (settings.CACHE_TYPE or "none").lower()
    FastAPICache.reset()
    if cache_type == "memory":
        FastAPICache.init(InMemoryBackend(), coder=JsonCoder)
        AppLogUtil.info("星通数智使用内存缓存, 仅支持单进程模式")
    elif cache_type == "redis":
        from fastapi_cache.backends.redis import RedisBackend
        redis_client = get_redis_client()
        await ping_redis()
        FastAPICache.init(RedisBackend(redis_client), prefix=settings.CACHE_REDIS_PREFIX, coder=JsonCoder)
        AppLogUtil.info(f"星通数智使用Redis缓存, 可使用多进程模式: {mask_redis_url(build_redis_url())}")
    else:
        AppLogUtil.warning("星通数智未启用缓存, 可使用多进程模式")


async def close_app_cache():
    """
    是什么：close_app_cache 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力这次处理做收尾，记录结果并关掉不再需要的资源。
    """
    if (settings.CACHE_TYPE or "none").lower() == "redis":
        await close_redis_client()


async def cache_health() -> dict:
    """
    是什么：cache_health 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    cache_type: str = (settings.CACHE_TYPE or "none").lower()
    if cache_type == "redis":
        return await redis_health()
    if cache_type == "memory":
        return {
            "status": "ok",
            "type": "memory",
            "message": "内存缓存仅适合单进程开发环境",
        }
    return {
        "status": "disabled",
        "type": cache_type,
    }


def is_cache_initialized() -> bool:
    # 检查必要的属性是否存在
    """
    是什么：is_cache_initialized 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        return FastAPICache.get_backend() is not None and FastAPICache.get_prefix() is not None
    except (AssertionError, AttributeError) as e:
        AppLogUtil.debug(f"缓存初始化检查失败: {str(e)}")
        return False
