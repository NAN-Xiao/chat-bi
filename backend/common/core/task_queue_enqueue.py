"""Atomic Redis transport for confirmed task enqueue and repair."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from redis.exceptions import RedisError

from apps.system.crud.tenant_usage import (
    check_tenant_usage_quota_detached,
    record_tenant_usage_detached,
)
from common.core.config import settings
from common.core.redis_client import (
    get_redis_client,
    platform_redis_key,
    tenant_redis_key,
)
from common.utils.utils import AppLogUtil

DEFAULT_TASK_TENANT_ID = 1


def normalize_tenant_id(tenant_id: int | str | None) -> int:
    if tenant_id in (None, ""):
        return DEFAULT_TASK_TENANT_ID
    return int(tenant_id)


def queue_key(queue_name: str | None = None) -> str:
    return platform_redis_key("task", "queue", queue_name or settings.TASK_QUEUE_NAME)


def tenant_pending_key(
    tenant_id: int | str | None,
    queue_name: str | None = None,
) -> str:
    return tenant_redis_key(
        normalize_tenant_id(tenant_id),
        "task",
        "queue",
        queue_name or settings.TASK_QUEUE_NAME,
        "pending",
    )


def task_key(task_id: str, tenant_id: int | str | None = None) -> str:
    return tenant_redis_key(
        normalize_tenant_id(tenant_id),
        "task",
        "item",
        task_id,
    )


def task_tenant_index_key(task_id: str) -> str:
    return platform_redis_key("task", "tenant", task_id)


def task_dedupe_key(
    tenant_id: int | str | None,
    queue_name: str | None,
    dedupe_key: str,
) -> str:
    return tenant_redis_key(
        normalize_tenant_id(tenant_id),
        "task",
        "dedupe",
        queue_name or settings.TASK_QUEUE_NAME,
        dedupe_key,
    )

class EnqueueOutcome(str, Enum):
    ENQUEUED = "ENQUEUED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EnqueueResult:
    outcome: EnqueueOutcome
    task: dict[str, Any] | None
    error_code: str | None = None


class AtomicEnqueueState(str, Enum):
    ENQUEUED = "ENQUEUED"
    DEDUPED = "DEDUPED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class AtomicEnqueueReply:
    state: AtomicEnqueueState
    reference: str
    task_json: str | None = None


ATOMIC_ENQUEUE_SCRIPT = """
-- task-queue:enqueue-v1
local task_key = KEYS[1]
local tenant_index_key = KEYS[2]
local dedupe_key = KEYS[3]
local queue_key = KEYS[4]
local pending_key = KEYS[5]

local task_json = ARGV[1]
local task_id = ARGV[2]
local tenant_id = ARGV[3]
local ttl = tonumber(ARGV[4])
local max_pending = tonumber(ARGV[6])

if dedupe_key ~= '' then
    local existing_id = redis.call('GET', dedupe_key)
    if existing_id then
        local existing_json = redis.call('GET', ARGV[5] .. existing_id)
        if existing_json then
            local ok, existing = pcall(cjson.decode, existing_json)
            if ok and (existing.status == 'pending' or existing.status == 'running') then
                return {'DEDUPED', existing_id, existing_json}
            end
        end
        redis.call('LREM', queue_key, 0, existing_id)
        redis.call('LREM', pending_key, 0, existing_id)
        if not existing_json then
            redis.call('DEL', ARGV[7] .. existing_id)
        end
        redis.call('DEL', dedupe_key)
    end
end

if max_pending > 0 and redis.call('LLEN', pending_key) >= max_pending then
    return {'REJECTED', 'TASK_QUEUE_FULL', ''}
end

redis.call('SET', task_key, task_json, 'EX', ttl)
redis.call('SET', tenant_index_key, tenant_id, 'EX', ttl)
if dedupe_key ~= '' then
    redis.call('SET', dedupe_key, task_id, 'EX', ttl)
end
redis.call('LREM', queue_key, 0, task_id)
redis.call('LPUSH', queue_key, task_id)
redis.call('EXPIRE', queue_key, ttl)
redis.call('LREM', pending_key, 0, task_id)
redis.call('LPUSH', pending_key, task_id)
redis.call('EXPIRE', pending_key, ttl)
return {'ENQUEUED', task_id, task_json}
"""


REPAIR_ENQUEUE_SCRIPT = """
-- task-queue:repair-v1
local task_key = KEYS[1]
local tenant_index_key = KEYS[2]
local queue_key = KEYS[3]
local pending_key = KEYS[4]

local task_id = ARGV[1]
local tenant_id = ARGV[2]
local ttl = tonumber(ARGV[3])
local queue_name = ARGV[4]
local task_json = redis.call('GET', task_key)
if not task_json then
    return {'REJECTED', 'TASK_NOT_FOUND', ''}
end

local decoded = cjson.decode(task_json)
if tostring(decoded.tenant_id) ~= tenant_id or tostring(decoded.queue) ~= queue_name then
    return {'REJECTED', 'TASK_CONTEXT_MISMATCH', ''}
end

redis.call('SET', tenant_index_key, tenant_id, 'EX', ttl)
redis.call('EXPIRE', task_key, ttl)
if decoded.status == 'pending' then
    redis.call('LREM', queue_key, 0, task_id)
    redis.call('LPUSH', queue_key, task_id)
    redis.call('EXPIRE', queue_key, ttl)
    redis.call('LREM', pending_key, 0, task_id)
    redis.call('LPUSH', pending_key, task_id)
    redis.call('EXPIRE', pending_key, ttl)
end
return {'ENQUEUED', task_id, task_json}
"""


def _text(value: bytes | str | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _parse_reply(raw: Any) -> AtomicEnqueueReply:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        raise RuntimeError("Task queue Lua script returned an invalid response")
    state = AtomicEnqueueState(_text(raw[0]))
    task_json = _text(raw[2]) if len(raw) > 2 and raw[2] not in (None, b"", "") else None
    return AtomicEnqueueReply(
        state=state,
        reference=_text(raw[1]),
        task_json=task_json,
    )


async def execute_atomic_enqueue(
    client: Any,
    *,
    task_key: str,
    tenant_index_key: str,
    dedupe_key: str,
    queue_key: str,
    pending_key: str,
    task_json: str,
    task_id: str,
    tenant_id: int,
    ttl_seconds: int,
    task_key_prefix: str,
    max_pending: int,
    tenant_index_key_prefix: str,
) -> AtomicEnqueueReply:
    raw = await client.eval(
        ATOMIC_ENQUEUE_SCRIPT,
        5,
        task_key,
        tenant_index_key,
        dedupe_key,
        queue_key,
        pending_key,
        task_json,
        task_id,
        str(tenant_id),
        str(ttl_seconds),
        task_key_prefix,
        str(max_pending),
        tenant_index_key_prefix,
    )
    return _parse_reply(raw)


async def execute_enqueue_repair(
    client: Any,
    *,
    task_key: str,
    tenant_index_key: str,
    queue_key: str,
    pending_key: str,
    task_id: str,
    tenant_id: int,
    ttl_seconds: int,
    queue_name: str,
) -> AtomicEnqueueReply:
    raw = await client.eval(
        REPAIR_ENQUEUE_SCRIPT,
        4,
        task_key,
        tenant_index_key,
        queue_key,
        pending_key,
        task_id,
        str(tenant_id),
        str(ttl_seconds),
        queue_name,
    )
    return _parse_reply(raw)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _json_loads(value: bytes | str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return json.loads(value)


def _new_task(
    name: str,
    payload: dict[str, Any] | None,
    *,
    created_by: int | None,
    tenant_id: int,
    queue_name: str,
    max_attempts: int | None,
    dedupe_key: str | None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": uuid.uuid4().hex,
        "tenant_id": tenant_id,
        "name": name,
        "queue": queue_name,
        "status": "pending",
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
        "dedupe_key": str(dedupe_key) if dedupe_key else None,
    }


async def confirm_or_repair_task(
    task_id: str,
    *,
    tenant_id: int | str | None,
    queue_name: str | None = None,
) -> EnqueueResult:
    resolved_tenant_id = normalize_tenant_id(tenant_id)
    resolved_queue_name = queue_name or settings.TASK_QUEUE_NAME
    try:
        client = get_redis_client()
    except Exception:
        return EnqueueResult(
            outcome=EnqueueOutcome.UNKNOWN,
            task=None,
            error_code="TASK_QUEUE_CONFIRMATION_REQUIRED",
        )
    try:
        raw_task = await client.get(task_key(task_id, resolved_tenant_id))
    except RedisError:
        return EnqueueResult(
            outcome=EnqueueOutcome.UNKNOWN,
            task=None,
            error_code="TASK_QUEUE_CONFIRMATION_REQUIRED",
        )
    try:
        task = _json_loads(raw_task)
    except (TypeError, ValueError):
        return EnqueueResult(
            outcome=EnqueueOutcome.REJECTED,
            task=None,
            error_code="TASK_INVALID",
        )
    if task is None:
        return EnqueueResult(
            outcome=EnqueueOutcome.REJECTED,
            task=None,
            error_code="TASK_NOT_FOUND",
        )
    if (
        task.get("id") != task_id
        or int(task.get("tenant_id") or DEFAULT_TASK_TENANT_ID) != resolved_tenant_id
        or task.get("queue") != resolved_queue_name
    ):
        return EnqueueResult(
            outcome=EnqueueOutcome.REJECTED,
            task=None,
            error_code="TASK_CONTEXT_MISMATCH",
        )
    try:
        reply = await execute_enqueue_repair(
            client,
            task_key=task_key(task_id, resolved_tenant_id),
            tenant_index_key=task_tenant_index_key(task_id),
            queue_key=queue_key(resolved_queue_name),
            pending_key=tenant_pending_key(resolved_tenant_id, resolved_queue_name),
            task_id=task_id,
            tenant_id=resolved_tenant_id,
            ttl_seconds=settings.TASK_QUEUE_RESULT_TTL_SECONDS,
            queue_name=resolved_queue_name,
        )
    except (RedisError, RuntimeError, ValueError):
        return EnqueueResult(
            outcome=EnqueueOutcome.UNKNOWN,
            task=task,
            error_code="TASK_QUEUE_CONFIRMATION_REQUIRED",
        )
    if reply.state is AtomicEnqueueState.REJECTED:
        return EnqueueResult(
            outcome=EnqueueOutcome.REJECTED,
            task=None,
            error_code=reply.reference,
        )
    latest_task = _json_loads(reply.task_json) if reply.task_json else task
    return EnqueueResult(outcome=EnqueueOutcome.ENQUEUED, task=latest_task)


async def enqueue_task_confirmed(
    name: str,
    payload: dict[str, Any] | None = None,
    *,
    handler_registered: bool,
    created_by: int | None = None,
    tenant_id: int | str | None = None,
    queue_name: str | None = None,
    max_attempts: int | None = None,
    dedupe_key: str | None = None,
) -> EnqueueResult:
    if not handler_registered:
        return EnqueueResult(
            outcome=EnqueueOutcome.REJECTED,
            task=None,
            error_code="TASK_HANDLER_NOT_REGISTERED",
        )

    resolved_tenant_id = normalize_tenant_id(tenant_id)
    resolved_queue_name = queue_name or settings.TASK_QUEUE_NAME
    try:
        quota_state = check_tenant_usage_quota_detached(
            tenant_id=resolved_tenant_id,
            action="task",
        )
    except Exception:
        return EnqueueResult(
            outcome=EnqueueOutcome.REJECTED,
            task=None,
            error_code="TASK_QUOTA_CHECK_FAILED",
        )
    if not quota_state.allowed:
        code = (
            "TENANT_SUBSCRIPTION_SUSPENDED"
            if getattr(quota_state, "reason", None) == "subscription_suspended"
            else "TENANT_TASK_QUOTA_EXCEEDED"
        )
        return EnqueueResult(
            outcome=EnqueueOutcome.REJECTED,
            task=None,
            error_code=code,
        )

    try:
        client = get_redis_client()
    except Exception:
        return EnqueueResult(
            outcome=EnqueueOutcome.REJECTED,
            task=None,
            error_code="TASK_QUEUE_UNAVAILABLE",
        )
    try:
        await client.ping()
    except RedisError:
        return EnqueueResult(
            outcome=EnqueueOutcome.REJECTED,
            task=None,
            error_code="TASK_QUEUE_UNAVAILABLE",
        )

    task = _new_task(
        name,
        payload,
        created_by=created_by,
        tenant_id=resolved_tenant_id,
        queue_name=resolved_queue_name,
        max_attempts=max_attempts,
        dedupe_key=dedupe_key,
    )
    resolved_dedupe_key = (
        task_dedupe_key(
            resolved_tenant_id,
            resolved_queue_name,
            str(dedupe_key),
        )
        if dedupe_key
        else ""
    )
    try:
        reply = await execute_atomic_enqueue(
            client,
            task_key=task_key(task["id"], resolved_tenant_id),
            tenant_index_key=task_tenant_index_key(task["id"]),
            dedupe_key=resolved_dedupe_key,
            queue_key=queue_key(resolved_queue_name),
            pending_key=tenant_pending_key(resolved_tenant_id, resolved_queue_name),
            task_json=_json_dumps(task),
            task_id=task["id"],
            tenant_id=resolved_tenant_id,
            ttl_seconds=settings.TASK_QUEUE_RESULT_TTL_SECONDS,
            task_key_prefix=f"{task_key('', resolved_tenant_id)}:",
            max_pending=int(settings.TASK_QUEUE_MAX_PENDING_PER_TENANT or 0),
            tenant_index_key_prefix=f"{platform_redis_key('task', 'tenant')}:",
        )
    except (RedisError, RuntimeError, ValueError):
        if resolved_dedupe_key:
            try:
                resolved_task_id = _text(await client.get(resolved_dedupe_key))
            except RedisError:
                resolved_task_id = ""
            if resolved_task_id == task["id"]:
                return EnqueueResult(
                    outcome=EnqueueOutcome.UNKNOWN,
                    task=task,
                    error_code="TASK_QUEUE_CONFIRMATION_REQUIRED",
                )
            if resolved_task_id:
                reconciled = await confirm_or_repair_task(
                    resolved_task_id,
                    tenant_id=resolved_tenant_id,
                    queue_name=resolved_queue_name,
                )
                if reconciled.outcome is EnqueueOutcome.ENQUEUED:
                    return reconciled
            return EnqueueResult(
                outcome=EnqueueOutcome.UNKNOWN,
                task=None,
                error_code="TASK_QUEUE_CONFIRMATION_REQUIRED",
            )
        return EnqueueResult(
            outcome=EnqueueOutcome.UNKNOWN,
            task=task,
            error_code="TASK_QUEUE_CONFIRMATION_REQUIRED",
        )

    if reply.state is AtomicEnqueueState.REJECTED:
        return EnqueueResult(
            outcome=EnqueueOutcome.REJECTED,
            task=None,
            error_code=reply.reference,
        )
    if reply.state is AtomicEnqueueState.DEDUPED:
        return await confirm_or_repair_task(
            reply.reference,
            tenant_id=resolved_tenant_id,
            queue_name=resolved_queue_name,
        )

    try:
        record_tenant_usage_detached(
            tenant_id=resolved_tenant_id,
            metric="task.enqueued",
            request_count=1,
            success_count=1,
            failure_count=0,
            task_count=1,
        )
    except Exception:
        AppLogUtil.exception(f"Failed to record enqueued task usage: {task['id']}")
    return EnqueueResult(outcome=EnqueueOutcome.ENQUEUED, task=task)
