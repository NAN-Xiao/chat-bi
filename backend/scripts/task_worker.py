"""
脚本说明：这个脚本放后端脚本相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import asyncio
import signal

from common.core.app_cache import close_app_cache, init_app_cache
from common.core.config import settings
from common.core.task_queue import worker_loop
from common.core.task_registry import register_builtin_tasks
from common.utils.utils import AppLogUtil


async def main() -> None:
    """
    是什么：main 是一个可以复用的小步骤，负责后端脚本相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端脚本的主要流程跑起来，一步步调用需要的处理。
    """
    register_builtin_tasks()
    await init_app_cache()
    stop_event = asyncio.Event()

    def stop() -> None:
        """
        是什么：stop 是一个可以复用的小步骤，负责后端脚本相关的一件事。
        谁调用：外层函数 main 跑到对应步骤时会调用它。
        做了什么：把后端脚本这次处理做收尾，记录结果并关掉不再需要的资源。
        """
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop())

    try:
        await worker_loop(queue_name=settings.TASK_QUEUE_NAME, stop_event=stop_event)
    finally:
        await close_app_cache()
        AppLogUtil.info("Task worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
