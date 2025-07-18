import logging
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache as original_cache
from functools import partial, wraps
from typing import Optional, Set, Any, Dict, Tuple, Callable
from inspect import Parameter, signature
from contextlib import asynccontextmanager
import asyncio


# 锁管理
_cache_locks = {}

@asynccontextmanager
async def _get_cache_lock(key: str):
    lock = _cache_locks.setdefault(key, asyncio.Lock())
    async with lock:
        try:
            yield
        finally:
            if key in _cache_locks and not lock.locked():
                del _cache_locks[key]

def should_skip_param(param: Parameter) -> bool:
    """判断参数是否应该被忽略(依赖注入参数)"""
    return (
        param.kind == Parameter.VAR_KEYWORD or  # **kwargs
        param.kind == Parameter.VAR_POSITIONAL or  # *args
        hasattr(param.annotation, "__module__") and 
        param.annotation.__module__.startswith(('fastapi', 'starlette', "sqlmodel.orm.session"))
    )

def custom_key_builder(
    func: Any,
    namespace: str = "",
    *,
    args: Tuple[Any, ...] = (),
    kwargs: Dict[str, Any],
    additional_skip_args: Optional[Set[str]] = None,
    cacheName: Optional[str] = None,
    keyExpression: Optional[str] = None,
) -> str:
    """完全兼容FastAPICache的键生成器"""
    if cacheName: 
        base_key = f"{namespace}:{cacheName}:"
        
        if keyExpression:
            try:
                sig = signature(func)
                bound_args = sig.bind_partial(*args, **kwargs)
                bound_args.apply_defaults()
                
                if keyExpression.startswith("args["):
                    import re
                    match = re.match(r"args\[(\d+)\]", keyExpression)
                    if match:
                        index = int(match.group(1))
                        value = bound_args.args[index]
                        base_key += f"{value}:"
                else:
                    parts = keyExpression.split('.')
                    value = bound_args.arguments[parts[0]]
                    for part in parts[1:]:
                        value = getattr(value, part)
                    base_key += f"{value}:"
                
            except (IndexError, KeyError, AttributeError) as e:
                logging.warning(f"Failed to evaluate keyExpression '{keyExpression}': {str(e)}")
        
        return base_key
    
    sig = signature(func)
    auto_skip_args = {
        name for name, param in sig.parameters.items()
        if should_skip_param(param)
    }
    skip_args = auto_skip_args.union(additional_skip_args or set())
    filtered_kwargs = {
        k: v for k, v in kwargs.items() if k not in skip_args
    }
    
    bound_args = sig.bind_partial(*args, **kwargs)
    bound_args.apply_defaults()
    
    filtered_args = []
    for i, (name, value) in enumerate(bound_args.arguments.items()):
        if i < len(args) and name not in skip_args:
            filtered_args.append(value)
    filtered_args = tuple(filtered_args)
    
    default_key_builder = FastAPICache.get_key_builder()
    return default_key_builder(
        func=func,
        namespace=namespace,
        args=filtered_args,
        kwargs=filtered_kwargs,
    )

def cache(
    expire: Optional[int] = 60 * 60 * 24,
    namespace: Optional[str] = None,
    key_builder: Optional[Any] = None,
    *,
    additional_skip_args: Optional[Set[str]] = None,
    cacheName: Optional[str] = None,
    keyExpression: Optional[str] = None,
):
    """完全兼容的缓存装饰器"""
    def decorator(func):
        if key_builder is None:
            used_key_builder = partial(
                custom_key_builder,
                additional_skip_args=additional_skip_args,
                cacheName=cacheName,
                keyExpression=keyExpression
            )
        else:
            used_key_builder = key_builder
            
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = used_key_builder(
                func=func,
                namespace=namespace or "",
                args=args,
                kwargs=kwargs
            )
            
            async with _get_cache_lock(cache_key):
                logging.info(f"Using cache key: {cache_key}")
                print(f"Using cache key: {cache_key}")
                backend = FastAPICache.get_backend()
                cached_value = await backend.get(cache_key)
                if cached_value is not None:
                    logging.info(f"Cache hit for key: {cache_key}, the value is: {cached_value}")
                    print(f"Cache hit for key: {cache_key}, the value is: {cached_value}")
                    return cached_value
                
                result = await func(*args, **kwargs)
                await backend.set(cache_key, result, expire)
                logging.info(f"Cache miss for key: {cache_key}, result cached.")
                print(f"Cache miss for key: {cache_key}, result cached.")
                return result
                
        return wrapper
    return decorator

def clear_cache(
    namespace: Optional[str] = None,
    cacheName: Optional[str] = None,
    keyExpression: Optional[str] = None,
):
    """清除缓存的装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = custom_key_builder(
                func=func,
                namespace=namespace or "",
                args=args,
                kwargs=kwargs,
                cacheName=cacheName,
                keyExpression=keyExpression,
            )
            
            async with _get_cache_lock(cache_key):
                await FastAPICache.clear(key=cache_key)
                result = await func(*args, **kwargs)
                logging.info(f"Clearing cache for key: {cache_key}")
                print(f"Clearing cache for key: {cache_key}")
                return result
        
        return wrapper
    return decorator