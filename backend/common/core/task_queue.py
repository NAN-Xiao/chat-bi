"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import asyncio
import inspect
import json
import socket
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from redis.exceptions import RedisError

from apps.system.crud.tenant_usage import check_tenant_usage_quota_detached, record_tenant_usage_detached
from common.core.config import settings
from common.core.redis_client import get_redis_client, redis_key, tenant_redis_key
from common.utils.utils import AppLogUtil


class TaskStatus(str, Enum):
    """
    类说明：TaskStatus 把后端基础能力相关的数据和行为放在一起，便于其他代码直接复用。
    """
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


TaskHandler = Callable[[dict[str, Any]], Any | Awaitable[Any]]
_task_handlers: dict[str, TaskHandler] = {}
_current_task_context: ContextVar[dict[str, Any] | None] = ContextVar("current_task_context", default=None)
DEFAULT_TASK_TENANT_ID = 1


def utc_now() -> str:
    """
    是什么：utc_now 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    """
    是什么：_json_dumps 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _json_loads(value: bytes | str | None) -> dict[str, Any] | None:
    """
    是什么：_json_loads 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return json.loads(value)


def _queue_key(queue_name: str | None = None) -> str:
    """
    是什么：_queue_key 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return redis_key("task", "queue", queue_name or settings.TASK_QUEUE_NAME)


def _processing_key(queue_name: str | None = None) -> str:
    """
    是什么：_processing_key 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力的主要流程跑起来，一步步调用需要的处理。
    """
    return redis_key("task", "processing", queue_name or settings.TASK_QUEUE_NAME)


def _normalize_tenant_id(tenant_id: int | str | None) -> int:
    """
    是什么：_normalize_tenant_id 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if tenant_id in (None, ""):
        return DEFAULT_TASK_TENANT_ID
    return int(tenant_id)


def _record_task_usage(tenant_id: int | str | None, metric: str, *, success: bool | None = None) -> None:
    """
    是什么：_record_task_usage 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    record_tenant_usage_detached(
        tenant_id=_normalize_tenant_id(tenant_id),
        metric=metric,
        request_count=1,
        success_count=1 if success is True else 0,
        failure_count=1 if success is False else 0,
        task_count=1,
    )


def _tenant_pending_key(tenant_id: int | str | None, queue_name: str | None = None) -> str:
    """
    是什么：_tenant_pending_key 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return tenant_redis_key(
        _normalize_tenant_id(tenant_id),
        "task",
        "queue",
        queue_name or settings.TASK_QUEUE_NAME,
        "pending",
    )


def _tenant_processing_key(tenant_id: int | str | None, queue_name: str | None = None) -> str:
    """
    是什么：_tenant_processing_key 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return tenant_redis_key(
        _normalize_tenant_id(tenant_id),
        "task",
        "queue",
        queue_name or settings.TASK_QUEUE_NAME,
        "processing",
    )


def _task_key(task_id: str, tenant_id: int | str | None = None) -> str:
    """
    是什么：_task_key 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return tenant_redis_key(_normalize_tenant_id(tenant_id), "task", "item", task_id)


def _legacy_task_key(task_id: str) -> str:
    """
    是什么：_legacy_task_key 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return redis_key("task", "item", task_id)


def _task_tenant_index_key(task_id: str) -> str:
    """
    是什么：_task_tenant_index_key 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return redis_key("task", "tenant", task_id)


def _decode_redis_value(value: bytes | str) -> str:
    """
    是什么：_decode_redis_value 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return value.decode("utf-8") if isinstance(value, bytes) else value


def _parse_utc(value: str | None) -> datetime | None:
    """
    是什么：_parse_utc 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def current_task_context() -> dict[str, Any] | None:
    """
    是什么：current_task_context 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    context = _current_task_context.get()
    return dict(context) if context else None


def current_task_tenant_id(default: int | None = DEFAULT_TASK_TENANT_ID) -> int | None:
    """
    是什么：current_task_tenant_id 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    context = _current_task_context.get()
    if not context:
        return default
    tenant_id = context.get("tenant_id")
    if tenant_id in (None, ""):
        return default
    return int(tenant_id)


def task_handler(name: str):
    """
    是什么：task_handler 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    def decorator(func: TaskHandler):
        """
        是什么：decorator 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
        谁调用：外层函数 task_handler 跑到对应步骤时会调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        if name in _task_handlers:
            raise ValueError(f"Task handler already registered: {name}")
        _task_handlers[name] = func
        return func

    return decorator


def registered_task_names() -> list[str]:
    """
    是什么：registered_task_names 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return sorted(_task_handlers)


async def enqueue_task(
    name: str,
    payload: dict[str, Any] | None = None,
    *,
    created_by: int | None = None,
    tenant_id: int | str | None = None,
    queue_name: str | None = None,
    max_attempts: int | None = None,
) -> dict[str, Any]:
    """
    是什么：enqueue_task 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if name not in _task_handlers:
        raise ValueError(f"Unknown task handler: {name}")

    task_id = uuid.uuid4().hex
    now = utc_now()
    resolved_tenant_id = _normalize_tenant_id(tenant_id)
    quota_state = check_tenant_usage_quota_detached(tenant_id=resolved_tenant_id, action="task")
    if not quota_state.allowed:
        if getattr(quota_state, "reason", None) == "subscription_suspended":
            raise RuntimeError(
                f"Tenant {resolved_tenant_id} subscription is {quota_state.subscription_status}; "
                "task enqueue is suspended by SaaS administrator."
            )
        raise RuntimeError(
            f"Tenant {resolved_tenant_id} task quota exceeded "
            f"({quota_state.used}/{quota_state.limit} {quota_state.window})."
        )
    max_pending_per_tenant = int(settings.TASK_QUEUE_MAX_PENDING_PER_TENANT or 0)
    if max_pending_per_tenant > 0:
        current_pending = await tenant_queue_size(resolved_tenant_id, queue_name)
        if current_pending >= max_pending_per_tenant:
            raise RuntimeError(
                f"Tenant {resolved_tenant_id} task queue is full "
                f"({current_pending}/{max_pending_per_tenant} pending)."
            )
    task = {
        "id": task_id,
        "tenant_id": resolved_tenant_id,
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
        _task_key(task_id, resolved_tenant_id),
        _json_dumps(task),
        ex=settings.TASK_QUEUE_RESULT_TTL_SECONDS,
    )
    await client.set(
        _task_tenant_index_key(task_id),
        str(resolved_tenant_id),
        ex=settings.TASK_QUEUE_RESULT_TTL_SECONDS,
    )
    await client.lpush(_queue_key(queue_name), task_id)
    await _push_pending_task(task_id, resolved_tenant_id, queue_name)
    _record_task_usage(resolved_tenant_id, "task.enqueued", success=True)
    return task


async def _enqueue_task_and_log(
    name: str,
    payload: dict[str, Any] | None = None,
    *,
    created_by: int | None = None,
    tenant_id: int | str | None = None,
    queue_name: str | None = None,
    max_attempts: int | None = None,
) -> dict[str, Any] | None:
    """
    是什么：_enqueue_task_and_log 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        return await enqueue_task(
            name,
            payload,
            created_by=created_by,
            tenant_id=tenant_id,
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
    tenant_id: int | str | None = None,
    queue_name: str | None = None,
    max_attempts: int | None = None,
) -> dict[str, Any] | None:
    """
    是什么：enqueue_task_detached 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    coroutine = _enqueue_task_and_log(
        name,
        payload,
        created_by=created_by,
        tenant_id=tenant_id,
        queue_name=queue_name,
        max_attempts=max_attempts,
    )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    loop.create_task(coroutine)
    return None


async def get_task(task_id: str, *, tenant_id: int | str | None = None) -> dict[str, Any] | None:
    """
    是什么：get_task 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力需要的数据找出来，整理成后面好用的样子。
    """
    client = get_redis_client()
    raw_index_tenant_id = await client.get(_task_tenant_index_key(task_id))
    indexed_tenant_id = _decode_redis_value(raw_index_tenant_id) if raw_index_tenant_id is not None else None
    if tenant_id is not None:
        requested_tenant_id = _normalize_tenant_id(tenant_id)
        if indexed_tenant_id is not None and int(indexed_tenant_id) != requested_tenant_id:
            return None
        task = _json_loads(await client.get(_task_key(task_id, requested_tenant_id)))
        if task is not None:
            return task
        if indexed_tenant_id is None and requested_tenant_id == DEFAULT_TASK_TENANT_ID:
            return _json_loads(await client.get(_legacy_task_key(task_id)))
        return None
    if indexed_tenant_id is not None:
        task = _json_loads(await client.get(_task_key(task_id, indexed_tenant_id)))
        if task is not None:
            return task
    return _json_loads(await client.get(_legacy_task_key(task_id)))


async def queue_size(queue_name: str | None = None) -> int:
    """
    是什么：queue_size 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    client = get_redis_client()
    return int(await client.llen(_queue_key(queue_name)))


async def processing_size(queue_name: str | None = None) -> int:
    """
    是什么：processing_size 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力的主要流程跑起来，一步步调用需要的处理。
    """
    client = get_redis_client()
    return int(await client.llen(_processing_key(queue_name)))


async def tenant_queue_size(tenant_id: int | str | None, queue_name: str | None = None) -> int:
    """
    是什么：tenant_queue_size 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    client = get_redis_client()
    return int(await client.llen(_tenant_pending_key(tenant_id, queue_name)))


async def tenant_processing_size(tenant_id: int | str | None, queue_name: str | None = None) -> int:
    """
    是什么：tenant_processing_size 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    client = get_redis_client()
    return int(await client.llen(_tenant_processing_key(tenant_id, queue_name)))


async def _push_pending_task(task_id: str, tenant_id: int | str | None, queue_name: str | None = None) -> None:
    """
    是什么：_push_pending_task 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    client = get_redis_client()
    pending_key = _tenant_pending_key(tenant_id, queue_name)
    await client.lrem(pending_key, 0, task_id)
    await client.lpush(pending_key, task_id)


async def _remove_pending_task(task_id: str, tenant_id: int | str | None, queue_name: str | None = None) -> None:
    """
    是什么：_remove_pending_task 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力不再需要的数据、缓存或临时内容清理掉。
    """
    await get_redis_client().lrem(_tenant_pending_key(tenant_id, queue_name), 0, task_id)


async def _push_processing_task(task_id: str, tenant_id: int | str | None, queue_name: str | None = None) -> None:
    """
    是什么：_push_processing_task 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    client = get_redis_client()
    processing_key = _tenant_processing_key(tenant_id, queue_name)
    await client.lrem(processing_key, 0, task_id)
    await client.lpush(processing_key, task_id)


async def _remove_processing_task(task_id: str, tenant_id: int | str | None, queue_name: str | None = None) -> None:
    """
    是什么：_remove_processing_task 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力不再需要的数据、缓存或临时内容清理掉。
    """
    await get_redis_client().lrem(_tenant_processing_key(tenant_id, queue_name), 0, task_id)


async def _tenant_processing_limit_reached(tenant_id: int | str | None, queue_name: str | None = None) -> bool:
    """
    是什么：_tenant_processing_limit_reached 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    limit = int(settings.TASK_QUEUE_MAX_PROCESSING_PER_TENANT or 0)
    if limit <= 0:
        return False
    return await tenant_processing_size(tenant_id, queue_name) >= limit


async def task_queue_health(queue_name: str | None = None) -> dict[str, Any]:
    """
    是什么：task_queue_health 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        client = get_redis_client()
        await client.ping()
        return {
            "status": "ok",
            "queue": queue_name or settings.TASK_QUEUE_NAME,
            "pending": await queue_size(queue_name),
            "processing": await processing_size(queue_name),
            "tenant_limits": {
                "max_pending_per_tenant": settings.TASK_QUEUE_MAX_PENDING_PER_TENANT,
                "max_processing_per_tenant": settings.TASK_QUEUE_MAX_PROCESSING_PER_TENANT,
            },
            "registered_tasks": registered_task_names(),
        }
    except RedisError as exc:
        return {
            "status": "error",
            "queue": queue_name or settings.TASK_QUEUE_NAME,
            "message": str(exc),
        }


async def _save_task(task: dict[str, Any]) -> None:
    """
    是什么：_save_task 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存后端基础能力需要的东西，让后续流程能继续往下走。
    """
    client = get_redis_client()
    resolved_tenant_id = _normalize_tenant_id(task.get("tenant_id"))
    task["tenant_id"] = resolved_tenant_id
    await client.set(
        _task_key(task["id"], resolved_tenant_id),
        _json_dumps(task),
        ex=settings.TASK_QUEUE_RESULT_TTL_SECONDS,
    )
    await client.set(
        _task_tenant_index_key(task["id"]),
        str(resolved_tenant_id),
        ex=settings.TASK_QUEUE_RESULT_TTL_SECONDS,
    )


async def _claim_task(queue_name: str | None = None, *, timeout: int | None = None) -> str | None:
    """
    是什么：_claim_task 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    client = get_redis_client()
    queue = queue_name or settings.TASK_QUEUE_NAME
    timeout_seconds = settings.TASK_QUEUE_POLL_TIMEOUT_SECONDS if timeout is None else timeout
    max_scan = max(1, await queue_size(queue))
    for attempt in range(max_scan):
        raw_task_id = await client.brpoplpush(
            _queue_key(queue),
            _processing_key(queue),
            timeout=timeout_seconds if attempt == 0 else 0,
        )
        if raw_task_id is None:
            return None
        task_id = _decode_redis_value(raw_task_id)
        task = await get_task(task_id)
        if task is None:
            await _ack_task(task_id, queue)
            continue
        tenant_id = task.get("tenant_id")
        if await _tenant_processing_limit_reached(tenant_id, queue):
            await _ack_task(task_id, queue)
            await client.lpush(_queue_key(queue), task_id)
            continue
        await _remove_pending_task(task_id, tenant_id, queue)
        await _push_processing_task(task_id, tenant_id, queue)
        return task_id
    return None


async def _ack_task(task_id: str, queue_name: str | None = None) -> None:
    """
    是什么：_ack_task 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    task = await get_task(task_id)
    await get_redis_client().lrem(_processing_key(queue_name), 0, task_id)
    if task is not None:
        await _remove_processing_task(task_id, task.get("tenant_id"), task.get("queue") or queue_name)


async def _run_handler(name: str, payload: dict[str, Any], task: dict[str, Any] | None = None) -> Any:
    """
    是什么：_run_handler 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力的主要流程跑起来，一步步调用需要的处理。
    """
    handler = _task_handlers.get(name)
    if handler is None:
        raise ValueError(f"Unknown task handler: {name}")
    token = _current_task_context.set(task)
    try:
        result = handler(payload)
        if inspect.isawaitable(result):
            return await result
        return result
    finally:
        _current_task_context.reset(token)


async def run_task(
    task_id: str,
    *,
    worker_name: str | None = None,
    queue_name: str | None = None,
) -> dict[str, Any] | None:
    """
    是什么：run_task 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力的主要流程跑起来，一步步调用需要的处理。
    """
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
        result = await _run_handler(task["name"], task.get("payload") or {}, task)
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
            await _push_pending_task(task_id, task.get("tenant_id"), task_queue)
            _record_task_usage(task.get("tenant_id"), "task.retried", success=False)
        elif task["status"] == TaskStatus.SUCCEEDED.value:
            _record_task_usage(task.get("tenant_id"), "task.succeeded", success=True)
        elif task["status"] == TaskStatus.FAILED.value:
            _record_task_usage(task.get("tenant_id"), "task.failed", success=False)

    return task


async def recover_stale_tasks(
    *,
    queue_name: str | None = None,
    stale_after_seconds: int | None = None,
) -> dict[str, int]:
    """
    是什么：recover_stale_tasks 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
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
        await _push_pending_task(task_id, task.get("tenant_id"), queue)
        recovered += 1

    return {"recovered": recovered, "removed": removed, "failed": failed}


async def worker_loop(
    *,
    queue_name: str | None = None,
    worker_name: str | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    """
    是什么：worker_loop 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
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
