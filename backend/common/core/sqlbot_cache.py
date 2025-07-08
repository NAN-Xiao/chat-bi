from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache as original_cache
from functools import partial, wraps
from typing import Optional, Set, Any, Dict, Tuple
from inspect import Parameter, signature
import logging

logger = logging.getLogger(__name__)

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
    """
    完全兼容FastAPICache的键生成器
    """
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
                logger.warning(f"Failed to evaluate keyExpression '{keyExpression}': {str(e)}")
        
        return base_key
    # 获取函数签名
    sig = signature(func)
    
    # 自动识别要跳过的参数
    auto_skip_args = {
        name for name, param in sig.parameters.items()
        if should_skip_param(param)
    }
    
    # 合并用户指定的额外跳过参数
    skip_args = auto_skip_args.union(additional_skip_args or set())
    
    # 过滤kwargs
    filtered_kwargs = {
        k: v for k, v in kwargs.items() if k not in skip_args
    }
    
    # 过滤args - 将位置参数映射到它们的参数名
    bound_args = sig.bind_partial(*args, **kwargs)
    bound_args.apply_defaults()
    
    filtered_args = []
    for i, (name, value) in enumerate(bound_args.arguments.items()):
        # 只处理位置参数 (在args中的参数)
        if i < len(args) and name not in skip_args:
            filtered_args.append(value)
    filtered_args = tuple(filtered_args)
    
    # 获取默认键生成器
    default_key_builder = FastAPICache.get_key_builder()
    # 调用默认键生成器（严格按照其要求的参数格式）
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
    """
    完全兼容的缓存装饰器
    """
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
            # 准备键生成器参数
            key_builder_args = {
                "func": func,
                "namespace": namespace,
                "args": args,
                "kwargs": kwargs
            }
            
            # 生成缓存键
            cache_key = used_key_builder(**key_builder_args)
            logger.debug(f"Generated cache key: {cache_key}")
            
            # 使用原始缓存装饰器
            return await original_cache(
                expire=expire,
                namespace=namespace,
                key_builder=lambda *_, **__: cache_key  # 直接使用预生成的key
            )(func)(*args, **kwargs)
        return wrapper
    return decorator

def clear_cache(
    namespace: Optional[str] = None,
    cacheName: Optional[str] = None,
    keyExpression: Optional[str] = None,
):
    """
    清除缓存的装饰器，参数与 @cache 保持一致
    使用方式：
    @clear_cache(namespace="user", cacheName="info", keyExpression="user_id")
    async def update_user(user_id: int):
        ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 1. 生成缓存键（复用 custom_key_builder 逻辑）
            cache_key = custom_key_builder(
                func=func,
                namespace=namespace or "",
                args=args,
                kwargs=kwargs,
                cacheName=cacheName,
                keyExpression=keyExpression,
            )
            
            logger.debug(f"Clearing cache for key: {cache_key}")
            
            # 2. 清除缓存
            await FastAPICache.clear(key=cache_key)
            
            # 3. 执行原函数
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator