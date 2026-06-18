import asyncio
import inspect
import json
import socket
import time
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


def _processing_key(queue_name: str | None = None) -> str:
    return redis_key("task", "processing", queue_name or settings.TASK_QUEUE_NAME)


def _task_key(task_id: str) -> str:
    return redis_key("task", "item", task_id)


def _decode_redis_value(value: bytes | str) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else value


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


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
    await client.lpush(_queue_key(queue_name), task_id)
    return task


async def _enqueue_task_and_log(
    name: str,
    payload: dict[str, Any] | None = None,
    *,
    created_by: int | None = None,
    queue_name: str | None = None,
    max_attempts: int | None = None,
) -> dict[str, Any] | None:
    try:
        return await enqueue_task(
            name,
            payload,
            created_by=created_by,
            queue_name=queue_name,
            max_attempts=max_attempts,
        )
    except Exception:
        AppLogUtil.exception(f"Failed to enqueue task: {name}")
        return None


def enqueue_task_detached(
    name: str,
    payload: dict[str, Any] | None = None,
    *,
    created_by: int | None = None,
    queue_name: str | None = None,
    max_attempts: int | None = None,
) -> dict[str, Any] | None:
    coroutine = _enqueue_task_and_log(
        name,
        payload,
        created_by=created_by,
        queue_name=queue_name,
        max_attempts=max_attempts,
    )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    loop.create_task(coroutine)
    return None


async def get_task(task_id: str) -> dict[str, Any] | None:
    client = get_redis_client()
    return _json_loads(await client.get(_task_key(task_id)))


async def queue_size(queue_name: str | None = None) -> int:
    client = get_redis_client()
    return int(await client.llen(_queue_key(queue_name)))


async def processing_size(queue_name: str | None = None) -> int:
    client = get_redis_client()
    return int(await client.llen(_processing_key(queue_name)))


async def task_queue_health(queue_name: str | None = None) -> dict[str, Any]:
    try:
        client = get_redis_client()
        await client.ping()
        return {
            "status": "ok",
            "queue": queue_name or settings.TASK_QUEUE_NAME,
            "pending": await queue_size(queue_name),
            "processing": await processing_size(queue_name),
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


async def _claim_task(queue_name: str | None = None, *, timeout: int | None = None) -> str | None:
    client = get_redis_client()
    raw_task_id = await client.brpoplpush(
        _queue_key(queue_name),
        _processing_key(queue_name),
        timeout=settings.TASK_QUEUE_POLL_TIMEOUT_SECONDS if timeout is None else timeout,
    )
    if raw_task_id is None:
        return None
    return _decode_redis_value(raw_task_id)


async def _ack_task(task_id: str, queue_name: str | None = None) -> None:
    await get_redis_client().lrem(_processing_key(queue_name), 0, task_id)


async def _run_handler(name: str, payload: dict[str, Any]) -> Any:
    handler = _task_handlers.get(name)
    if handler is None:
        raise ValueError(f"Unknown task handler: {name}")
    result = handler(payload)
    if inspect.isawaitable(result):
        return await result
    return result


async def run_task(
    task_id: str,
    *,
    worker_name: str | None = None,
    queue_name: str | None = None,
) -> dict[str, Any] | None:
    task = await get_task(task_id)
    if task is None:
        AppLogUtil.warning(f"Skip missing queued task: {task_id}")
        await _ack_task(task_id, queue_name)
        return None
    if task.get("status") != TaskStatus.PENDING.value:
        AppLogUtil.warning(f"Skip non-pending queued task: {task_id} status={task.get('status')}")
        await _ack_task(task_id, task.get("queue") or queue_name)
        return task

    should_requeue = False
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
            task["started_at"] = None
            task["finished_at"] = None
            task["worker"] = None
            should_requeue = True
        else:
            task["status"] = TaskStatus.FAILED.value
        AppLogUtil.exception(f"Task failed: {task_id} {task.get('name')}")
    finally:
        finished_at = utc_now()
        if task["status"] in {TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value}:
            task["finished_at"] = finished_at
        task["updated_at"] = finished_at
        await _save_task(task)
        task_queue = task.get("queue") or queue_name
        await _ack_task(task_id, task_queue)
        if should_requeue:
            await get_redis_client().lpush(_queue_key(task_queue), task_id)

    return task


async def recover_stale_tasks(
    *,
    queue_name: str | None = None,
    stale_after_seconds: int | None = None,
) -> dict[str, int]:
    client = get_redis_client()
    queue = queue_name or settings.TASK_QUEUE_NAME
    timeout_seconds = (
        settings.TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS
        if stale_after_seconds is None
        else stale_after_seconds
    )
    now = datetime.now(timezone.utc)
    recovered = 0
    removed = 0
    failed = 0

    raw_ids = await client.lrange(_processing_key(queue), 0, -1)
    for raw_task_id in raw_ids:
        task_id = _decode_redis_value(raw_task_id)
        task = await get_task(task_id)
        if task is None:
            await _ack_task(task_id, queue)
            removed += 1
            continue

        status = task.get("status")
        if status in {TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value}:
            await _ack_task(task_id, queue)
            removed += 1
            continue

        should_recover = status == TaskStatus.PENDING.value
        if status == TaskStatus.RUNNING.value:
            started_at = _parse_utc(task.get("started_at"))
            should_recover = started_at is None or (now - started_at).total_seconds() >= timeout_seconds

        if not should_recover:
            continue

        attempts = int(task.get("attempts") or 0)
        max_attempts = int(task.get("max_attempts") or 1)
        if attempts >= max_attempts:
            task["status"] = TaskStatus.FAILED.value
            task["error"] = task.get("error") or "Task exceeded max attempts before recovery."
            task["finished_at"] = utc_now()
            task["updated_at"] = task["finished_at"]
            task["worker"] = None
            await _save_task(task)
            await _ack_task(task_id, queue)
            failed += 1
            continue

        task["status"] = TaskStatus.PENDING.value
        task["started_at"] = None
        task["finished_at"] = None
        task["worker"] = None
        task["updated_at"] = utc_now()
        task["error"] = task.get("error") or "Task recovered after worker interruption."
        await _save_task(task)
        await _ack_task(task_id, queue)
        await client.lpush(_queue_key(queue), task_id)
        recovered += 1

    return {"recovered": recovered, "removed": removed, "failed": failed}


async def worker_loop(
    *,
    queue_name: str | None = None,
    worker_name: str | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    queue = queue_name or settings.TASK_QUEUE_NAME
    worker = worker_name or f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
    AppLogUtil.info(f"Task worker started: worker={worker} queue={queue}")
    await recover_stale_tasks(queue_name=queue)
    last_recovery = time.monotonic()

    while stop_event is None or not stop_event.is_set():
        if time.monotonic() - last_recovery >= settings.TASK_QUEUE_REQUEUE_INTERVAL_SECONDS:
            await recover_stale_tasks(queue_name=queue)
            last_recovery = time.monotonic()
        try:
            task_id = await _claim_task(queue)
        except RedisError as exc:
            AppLogUtil.warning(f"Task worker Redis read failed: {exc}")
            await asyncio.sleep(1)
            continue
        if not task_id:
            continue
        await run_task(task_id, worker_name=worker, queue_name=queue)

    AppLogUtil.info(f"Task worker stopped: worker={worker} queue={queue}")
