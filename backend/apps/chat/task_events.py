from typing import Any

from common.core.config import settings
from common.core.redis_client import get_redis_client, tenant_redis_key


def _events_key(tenant_id: int | str | None, task_id: str) -> str:
    return tenant_redis_key(tenant_id, "chat", "smart_qa", task_id, "events")


def _record_task_key(tenant_id: int | str | None, record_id: int | str) -> str:
    return tenant_redis_key(tenant_id, "chat", "smart_qa", "record", record_id, "task")


async def append_chat_task_event(tenant_id: int | str | None, task_id: str, chunk: str) -> None:
    client = get_redis_client()
    key = _events_key(tenant_id, task_id)
    pipe = client.pipeline()
    pipe.rpush(key, chunk)
    pipe.expire(key, settings.TASK_QUEUE_RESULT_TTL_SECONDS)
    await pipe.execute()


async def get_chat_task_events(
    tenant_id: int | str | None,
    task_id: str,
    *,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    safe_offset = max(0, int(offset or 0))
    safe_limit = min(max(1, int(limit or 100)), 500)
    client = get_redis_client()
    key = _events_key(tenant_id, task_id)
    raw_events = await client.lrange(key, safe_offset, safe_offset + safe_limit - 1)
    events = [
        event.decode("utf-8") if isinstance(event, bytes) else str(event)
        for event in raw_events
    ]
    return {
        "events": events,
        "offset": safe_offset,
        "next_offset": safe_offset + len(events),
    }


async def bind_chat_record_task(tenant_id: int | str | None, record_id: int | str, task_id: str) -> None:
    client = get_redis_client()
    await client.set(
        _record_task_key(tenant_id, record_id),
        task_id,
        ex=settings.TASK_QUEUE_RESULT_TTL_SECONDS,
    )


async def get_chat_record_task_id(tenant_id: int | str | None, record_id: int | str) -> str | None:
    raw = await get_redis_client().get(_record_task_key(tenant_id, record_id))
    if raw is None:
        return None
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
