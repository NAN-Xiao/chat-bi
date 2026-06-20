import json
import time
from dataclasses import dataclass
from threading import Lock
from typing import Optional

from common.core.chat_generation_limiter import ChatGenerationLease
from common.core.config import settings
from common.core.redis_client import build_redis_url, get_redis_client, redis_key
from common.utils.utils import AppLogUtil

try:
    from redis.exceptions import RedisError
except ModuleNotFoundError:
    RedisError = Exception


@dataclass
class ActiveChatGeneration:
    record_id: int | str
    user_id: int | str | None
    token: str | None
    redis_key: str | None
    lease: Optional[ChatGenerationLease]
    expires_at: float


_active_lock = Lock()
_active_generations: dict[str, ActiveChatGeneration] = {}
_stop_requests: dict[str, float] = {}


def _ttl() -> int:
    return max(
        30,
        int(settings.CHAT_GENERATION_TOTAL_TIMEOUT_SECONDS or 0) + 60,
        int(settings.CHAT_GENERATION_CONCURRENCY_SLOT_TTL_SECONDS or 0),
    )


def _record_key(record_id: int | str | None) -> str | None:
    if record_id is None:
        return None
    value = str(record_id).strip()
    return value or None


def _redis_stop_key(record_id: int | str) -> str:
    return redis_key("chat", "generation", "stop", record_id)


def _redis_active_key(record_id: int | str) -> str:
    return redis_key("chat", "generation", "active", record_id)


def _prune_memory(now: float | None = None) -> None:
    now = time.time() if now is None else now
    expired_active = [key for key, item in _active_generations.items() if item.expires_at <= now]
    for key in expired_active:
        _active_generations.pop(key, None)
    expired_stops = [key for key, expires_at in _stop_requests.items() if expires_at <= now]
    for key in expired_stops:
        _stop_requests.pop(key, None)


def _sync_redis_client():
    import redis as sync_redis

    return sync_redis.Redis.from_url(
        build_redis_url(),
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
    )


def register_chat_generation_sync(record_id: int | str | None, lease: Optional[ChatGenerationLease]) -> None:
    key = _record_key(record_id)
    if key is None:
        return

    ttl = _ttl()
    expires_at = time.time() + ttl
    with _active_lock:
        _prune_memory()
        _active_generations[key] = ActiveChatGeneration(
            record_id=key,
            user_id=getattr(lease, "user_id", None),
            token=getattr(lease, "token", None),
            redis_key=getattr(lease, "redis_key", None),
            lease=lease,
            expires_at=expires_at,
        )
        _stop_requests.pop(key, None)

    if (settings.CACHE_TYPE or "").lower() != "redis":
        return

    client = None
    try:
        payload = {
            "record_id": key,
            "user_id": getattr(lease, "user_id", None),
            "token": getattr(lease, "token", None),
            "redis_key": getattr(lease, "redis_key", None),
        }
        client = _sync_redis_client()
        client.setex(_redis_active_key(key), ttl, json.dumps(payload))
        client.delete(_redis_stop_key(key))
    except RedisError:
        AppLogUtil.exception("Redis chat generation active registration failed")
    finally:
        if client is not None:
            client.close()


def unregister_chat_generation_sync(record_id: int | str | None) -> None:
    key = _record_key(record_id)
    if key is None:
        return

    with _active_lock:
        _active_generations.pop(key, None)

    if (settings.CACHE_TYPE or "").lower() != "redis":
        return

    client = None
    try:
        client = _sync_redis_client()
        client.delete(_redis_active_key(key))
    except RedisError:
        AppLogUtil.exception("Redis chat generation active unregister failed")
    finally:
        if client is not None:
            client.close()


def is_chat_generation_stop_requested_sync(record_id: int | str | None) -> bool:
    key = _record_key(record_id)
    if key is None:
        return False

    with _active_lock:
        _prune_memory()
        if key in _stop_requests:
            return True

    if (settings.CACHE_TYPE or "").lower() != "redis":
        return False

    client = None
    try:
        client = _sync_redis_client()
        return bool(client.exists(_redis_stop_key(key)))
    except RedisError:
        AppLogUtil.exception("Redis chat generation stop check failed")
        return False
    finally:
        if client is not None:
            client.close()


async def request_chat_generation_stop(record_id: int | str | None) -> bool:
    key = _record_key(record_id)
    if key is None:
        return False

    ttl = _ttl()
    with _active_lock:
        _prune_memory()
        _stop_requests[key] = time.time() + ttl
        active = _active_generations.get(key)

    released = False
    if active and active.lease:
        try:
            await active.lease.release()
            released = True
        except Exception:
            AppLogUtil.exception("Chat generation lease release on stop failed")
    elif active and active.token and active.user_id:
        fallback_lease = ChatGenerationLease(
            user_id=active.user_id,
            token=active.token,
            redis_key=active.redis_key,
        )
        try:
            await fallback_lease.release()
            released = True
        except Exception:
            AppLogUtil.exception("Chat generation fallback lease release on stop failed")

    if (settings.CACHE_TYPE or "").lower() != "redis":
        return released

    try:
        client = get_redis_client()
        await client.setex(_redis_stop_key(key), ttl, "1")
        active_payload = await client.get(_redis_active_key(key))
        if active_payload:
            if isinstance(active_payload, bytes):
                active_payload = active_payload.decode()
            active_data = json.loads(active_payload)
            redis_running_key = active_data.get("redis_key")
            token = active_data.get("token")
            if redis_running_key and token:
                await client.zrem(redis_running_key, token)
                released = True
    except RedisError:
        AppLogUtil.exception("Redis chat generation stop request failed")

    return released
