import asyncio
import signal

from apps.system import tasks as system_tasks  # noqa: F401
from common.core.app_cache import close_app_cache, init_app_cache
from common.core.config import settings
from common.core.task_queue import worker_loop
from common.utils.utils import AppLogUtil


async def main() -> None:
    await init_app_cache()
    stop_event = asyncio.Event()

    def stop() -> None:
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
