import asyncio
import inspect
import json
import socket
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from redis.exceptions import RedisError

from common.core.config import settings
from common.core.redis_client import get_redis_client, redis_key
from common.utils.utils import AppLogUtil


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


TaskHandler = Callable[[dict[str, Any]], Any | Awaitable[Any]]
_task_handlers: dict[str, TaskHandler] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _json_loads(value: bytes | str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return json.loads(value)


def _queue_key(queue_name: str | None = None) -> str:
    return redis_key("task", "queue", queue_name or settings.TASK_QUEUE_NAME)


def _task_key(task_id: str) -> str:
    return redis_key("task", "item", task_id)


def task_handler(name: str):
    def decorator(func: TaskHandler):
        if name in _task_handlers:
            raise ValueError(f"Task handler already registered: {name}")
        _task_handlers[name] = func
        return func

    return decorator


def registered_task_names() -> list[str]:
    return sorted(_task_handlers)


async def enqueue_task(
    name: str,
    payload: dict[str, Any] | None = None,
    *,
    created_by: int | None = None,
    queue_name: str | None = None,
    max_attempts: int | None = None,
) -> dict[str, Any]:
    if name not in _task_handlers:
        raise ValueError(f"Unknown task handler: {name}")

    task_id = uuid.uuid4().hex
    now = utc_now()
    task = {
        "id": task_id,
        "name": name,
        "queue": queue_name or settings.TASK_QUEUE_NAME,
        "status": TaskStatus.PENDING.value,
        "payload": payload or {},
        "result": None,
        "error": None,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
        "attempts": 0,
        "max_attempts": max_attempts or settings.TASK_QUEUE_MAX_ATTEMPTS,
        "worker": None,
    }

    client = get_redis_client()
    await client.set(
        _task_key(task_id),
        _json_dumps(task),
        ex=settings.TASK_QUEUE_RESULT_TTL_SECONDS,
    )
    await client.rpush(_queue_key(queue_name), task_id)
    return task


async def get_task(task_id: str) -> dict[str, Any] | None:
    client = get_redis_client()
    return _json_loads(await client.get(_task_key(task_id)))


async def queue_size(queue_name: str | None = None) -> int:
    client = get_redis_client()
    return int(await client.llen(_queue_key(queue_name)))


async def task_queue_health(queue_name: str | None = None) -> dict[str, Any]:
    try:
        client = get_redis_client()
        await client.ping()
        return {
            "status": "ok",
            "queue": queue_name or settings.TASK_QUEUE_NAME,
            "pending": await queue_size(queue_name),
            "registered_tasks": registered_task_names(),
        }
    except RedisError as exc:
        return {
            "status": "error",
            "queue": queue_name or settings.TASK_QUEUE_NAME,
            "message": str(exc),
        }


async def _save_task(task: dict[str, Any]) -> None:
    client = get_redis_client()
    await client.set(
        _task_key(task["id"]),
        _json_dumps(task),
        ex=settings.TASK_QUEUE_RESULT_TTL_SECONDS,
    )


async def _run_handler(name: str, payload: dict[str, Any]) -> Any:
    handler = _task_handlers.get(name)
    if handler is None:
        raise ValueError(f"Unknown task handler: {name}")
    result = handler(payload)
    if inspect.isawaitable(result):
        return await result
    return result


async def run_task(task_id: str, *, worker_name: str | None = None) -> dict[str, Any] | None:
    task = await get_task(task_id)
    if task is None:
        AppLogUtil.warning(f"Skip missing queued task: {task_id}")
        return None
    if task.get("status") != TaskStatus.PENDING.value:
        AppLogUtil.warning(f"Skip non-pending queued task: {task_id} status={task.get('status')}")
        return task

    now = utc_now()
    task["status"] = TaskStatus.RUNNING.value
    task["attempts"] = int(task.get("attempts") or 0) + 1
    task["started_at"] = now
    task["updated_at"] = now
    task["worker"] = worker_name or socket.gethostname()
    await _save_task(task)

    try:
        result = await _run_handler(task["name"], task.get("payload") or {})
        task["status"] = TaskStatus.SUCCEEDED.value
        task["result"] = result
        task["error"] = None
    except Exception as exc:
        task["error"] = str(exc)
        if int(task["attempts"]) < int(task.get("max_attempts") or 1):
            task["status"] = TaskStatus.PENDING.value
            await get_redis_client().rpush(_queue_key(task.get("queue")), task_id)
        else:
            task["status"] = TaskStatus.FAILED.value
        AppLogUtil.exception(f"Task failed: {task_id} {task.get('name')}")
    finally:
        task["finished_at"] = utc_now()
        task["updated_at"] = task["finished_at"]
        await _save_task(task)

    return task


async def worker_loop(
    *,
    queue_name: str | None = None,
    worker_name: str | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    client = get_redis_client()
    queue = queue_name or settings.TASK_QUEUE_NAME
    worker = worker_name or f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
    AppLogUtil.info(f"Task worker started: worker={worker} queue={queue}")

    while stop_event is None or not stop_event.is_set():
        try:
            item = await client.blpop(_queue_key(queue), timeout=settings.TASK_QUEUE_POLL_TIMEOUT_SECONDS)
        except RedisError as exc:
            AppLogUtil.warning(f"Task worker Redis read failed: {exc}")
            await asyncio.sleep(1)
            continue
        if not item:
            continue
        _, raw_task_id = item
        task_id = raw_task_id.decode("utf-8") if isinstance(raw_task_id, bytes) else raw_task_id
        await run_task(task_id, worker_name=worker)

    AppLogUtil.info(f"Task worker stopped: worker={worker} queue={queue}")
