import re
from functools import partial, wraps
from inspect import signature
from typing import Any, Dict, Optional, Tuple

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache as original_cache

from common.core.config import settings
from common.core.redis_client import (
    build_redis_url,
    close_redis_client,
    get_redis_client,
    mask_redis_url,
    ping_redis,
    redis_health,
)
from common.utils.utils import AppLogUtil

def custom_key_builder(
    func: Any,
    namespace: str = "",
    *,
    args: Tuple[Any, ...] = (),
    kwargs: Dict[str, Any],
    cacheName: str,
    keyExpression: Optional[str] = None,
) -> str | list[str]:
    try:
        base_key = f"{namespace}:{cacheName}:"
        
        if keyExpression:
            sig = signature(func)
            bound_args = sig.bind_partial(*args, **kwargs)
            bound_args.apply_defaults()
            
            # 支持args[0]格式
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
        
        # 默认使用第一个参数作为key
        return f"{base_key}{args[0] if args else 'default'}"
        
    except Exception as e:
        AppLogUtil.error(f"Key builder error: {str(e)}")
        raise ValueError(f"Invalid cache key generation: {e}") from e

def cache(
    expire: int = 60 * 60 * 24,
    namespace: str = "",
    *,
    cacheName: str,  # 必须提供cacheName
    keyExpression: Optional[str] = None,
):
    def decorator(func):
        # 预先生成key builder
        used_key_builder = partial(
            custom_key_builder,
            cacheName=cacheName,
            keyExpression=keyExpression
        )
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not settings.CACHE_TYPE or settings.CACHE_TYPE.lower() == "none" or not is_cache_initialized():
                return await func(*args, **kwargs)
            # 生成缓存键
            cache_key = used_key_builder(
                func=func,
                namespace=str(namespace) if namespace else "",
                args=args,
                kwargs=kwargs
            )
            
            return await original_cache(
                expire=expire,
                namespace=str(namespace) if namespace else "",
                key_builder=lambda *_, **__: cache_key 
            )(func)(*args, **kwargs)
            
        return wrapper
    return decorator

def clear_cache(
    namespace: str = "",
    *,
    cacheName: str,
    keyExpression: Optional[str] = None,
):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not settings.CACHE_TYPE or settings.CACHE_TYPE.lower() == "none" or not is_cache_initialized():
                return await func(*args, **kwargs)
            cache_key = custom_key_builder(
                func=func,
                namespace=str(namespace) if namespace else "",
                args=args,
                kwargs=kwargs,
                cacheName=cacheName,
                keyExpression=keyExpression,
            )
            key_list = cache_key if isinstance(cache_key, list) else [cache_key]
            backend = FastAPICache.get_backend()
            for temp_cache_key in key_list:
                if await backend.get(temp_cache_key):
                    await backend.clear(key=temp_cache_key)
                    AppLogUtil.debug(f"Cache cleared: {temp_cache_key}")
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


async def init_app_cache():
    cache_type: str = (settings.CACHE_TYPE or "none").lower()
    FastAPICache.reset()
    if cache_type == "memory":
        FastAPICache.init(InMemoryBackend())
        AppLogUtil.info("星通数智使用内存缓存, 仅支持单进程模式")
    elif cache_type == "redis":
        from fastapi_cache.backends.redis import RedisBackend
        redis_client = get_redis_client()
        await ping_redis()
        FastAPICache.init(RedisBackend(redis_client), prefix=settings.CACHE_REDIS_PREFIX)
        AppLogUtil.info(f"星通数智使用Redis缓存, 可使用多进程模式: {mask_redis_url(build_redis_url())}")
    else:
        AppLogUtil.warning("星通数智未启用缓存, 可使用多进程模式")
    

async def close_app_cache():
    if (settings.CACHE_TYPE or "none").lower() == "redis":
        await close_redis_client()


async def cache_health() -> dict:
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
    if not hasattr(FastAPICache, "_backend") or not hasattr(FastAPICache, "_prefix"):
        return False
    
    # 检查属性值是否为 None
    if FastAPICache._backend is None or FastAPICache._prefix is None:
        return False
    
    # 尝试获取后端确认
    try:
        backend = FastAPICache.get_backend()
        return backend is not None
    except (AssertionError, AttributeError, Exception) as e:
        AppLogUtil.debug(f"缓存初始化检查失败: {str(e)}")
        return False
