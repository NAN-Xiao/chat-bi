import asyncio
import signal

from common.core.app_cache import close_app_cache, init_app_cache
from common.core.config import settings
from common.core.task_queue import worker_loop
from common.core.task_registry import register_builtin_tasks
from common.utils.utils import AppLogUtil


async def main() -> None:
    """
    是什么：main 是 backend/scripts/task_worker.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：执行脚本任务主流程，协调下游服务并处理结果或异常。
    """
    register_builtin_tasks()
    await init_app_cache()
    stop_event = asyncio.Event()

    def stop() -> None:
        """
        是什么：stop 是 backend/scripts/task_worker.py 中的同步函数。
        谁调用：由外层函数 main 在执行内部流程时调用。
        做了什么：完成或关闭脚本任务流程，释放资源并记录最终状态。
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
