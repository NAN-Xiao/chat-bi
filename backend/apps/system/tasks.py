from typing import Any

from common.core.task_queue import task_handler, utc_now


@task_handler("system.ping")
async def ping_task(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "message": payload.get("message") or "pong",
        "echo": payload,
        "finished_at": utc_now(),
    }
