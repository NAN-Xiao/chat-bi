"""
脚本说明：这个脚本放进程主事件循环注册相关的代码，供同步线程把协程安全投递回主循环执行。
"""
import asyncio
from collections.abc import Coroutine
from typing import Any

_main_event_loop: asyncio.AbstractEventLoop | None = None


def register_main_event_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """
    是什么：register_main_event_loop 注册或注销当前进程的主事件循环。
    谁调用：main.py 的 lifespan 和 scripts/task_worker.py 在启动、关闭时调用。
    做了什么：记录主循环引用，供没有运行中事件循环的同步线程把协程投递回主循环。
    """
    global _main_event_loop
    _main_event_loop = loop


def submit_to_main_loop(coroutine: Coroutine[Any, Any, Any]) -> bool:
    """
    是什么：submit_to_main_loop 把协程线程安全地投递到已注册的主事件循环。
    谁调用：同步线程里需要执行异步逻辑（如 Redis 调用）的兜底路径。
    做了什么：主循环可用时用 run_coroutine_threadsafe 投递并返回 True；
    不可用时返回 False 且不消耗协程，调用方可自行兜底（如 asyncio.run）。
    """
    loop = _main_event_loop
    if loop is None or not loop.is_running():
        return False
    asyncio.run_coroutine_threadsafe(coroutine, loop)
    return True
