import contextvars
from fastapi_cache import FastAPICache
from functools import partial, wraps
from typing import Optional, Any, Dict, Tuple
from inspect import signature
from contextlib import asynccontextmanager
import asyncio
import random
from collections import defaultdict

from common.utils.utils import SQLBotLogUtil

# 使用contextvar来跟踪当前线程已持有的锁
_held_locks = contextvars.ContextVar('held_locks', default=set())
# 高效锁管理器
class LockManager:
    _locks = defaultdict(asyncio.Lock)
    
    @classmethod
    def get_lock(cls, key: str) -> asyncio.Lock:
        return cls._locks[key]

@asynccontextmanager
async def _get_cache_lock(key: str):
    # 获取当前已持有的锁集合
    current_locks = _held_locks.get()
    
    # 如果已经持有这个锁，直接yield（锁传递）
    if key in current_locks:
        yield
        return
    
    # 否则获取锁并添加到当前上下文中
    lock = LockManager.get_lock(key)
    try:
        await lock.acquire()
        # 更新当前持有的锁集合
        new_locks = current_locks | {key}
        token = _held_locks.set(new_locks)
        
        yield
        
    finally:
        # 恢复之前的锁集合
        _held_locks.reset(token)
        if lock.locked():
            lock.release()

def custom_key_builder(
    func: Any,
    namespace: str = "",
    *,
    args: Tuple[Any, ...] = (),
    kwargs: Dict[str, Any],
    cacheName: str,
    keyExpression: Optional[str] = None,
) -> str:
    try:
        base_key = f"{namespace}:{cacheName}:"
        
        if keyExpression:
            sig = signature(func)
            bound_args = sig.bind_partial(*args, **kwargs)
            bound_args.apply_defaults()
            
            # 支持args[0]格式
            if keyExpression.startswith("args["):
                import re
                if match := re.match(r"args\[(\d+)\]", keyExpression):
                    index = int(match.group(1))
                    value = bound_args.args[index]
                    return f"{base_key}{value}"
            
            # 支持属性路径格式
            parts = keyExpression.split('.')
            value = bound_args.arguments[parts[0]]
            for part in parts[1:]:
                value = getattr(value, part)
            return f"{base_key}{value}"
        
        # 默认使用第一个参数作为key
        return f"{base_key}{args[0] if args else 'default'}"
        
    except Exception as e:
        SQLBotLogUtil.error(f"Key builder error: {str(e)}")
        raise ValueError(f"Invalid cache key generation: {e}") from e

def cache(
    expire: int = 60 * 60 * 24,
    namespace: str = "",
    *,
    cacheName: str,  # 必须提供cacheName
    keyExpression: Optional[str] = None,
    jitter: int = 60,  # 默认抖动60秒
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
            # 生成缓存键
            cache_key = used_key_builder(
                func=func,
                namespace=namespace,
                args=args,
                kwargs=kwargs
            )
            
            # 防击穿锁
            async with _get_cache_lock(cache_key):
                backend = FastAPICache.get_backend()
                
                # 双重检查
                if (cached := await backend.get(cache_key)) is not None:
                    SQLBotLogUtil.debug(f"Cache hit: {cache_key}")
                    return cached
                
                # 执行函数并缓存结果
                result = await func(*args, **kwargs)
                
                actual_expire = expire + random.randint(-jitter, jitter)
                if await backend.get(cache_key):
                    await backend.clear(cache_key)
                await backend.set(cache_key, result, actual_expire)
                
                SQLBotLogUtil.debug(f"Cache set: {cache_key} (expire: {actual_expire}s)")
                return result
                
        return wrapper
    return decorator

def clear_cache(
    namespace: str = "",
    *,
    cacheName: str,
    keyExpression: Optional[str] = None,
):
    """精确清除单个缓存项的装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = custom_key_builder(
                func=func,
                namespace=namespace,
                args=args,
                kwargs=kwargs,
                cacheName=cacheName,
                keyExpression=keyExpression,
            )
            
            # 加锁防止竞争
            async with _get_cache_lock(cache_key):
                backend = FastAPICache.get_backend()
                result = None
                if await backend.get(cache_key):
                    await backend.clear(cache_key)
                    result = await func(*args, **kwargs)
                    if await backend.get(cache_key):
                        await backend.clear(cache_key)
                    SQLBotLogUtil.info(f"Cache cleared: {cache_key}")
                return result
        
        return wrapper
    return decorator