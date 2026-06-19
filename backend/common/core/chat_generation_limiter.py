import time
import uuid
from dataclasses import dataclass
from threading import Lock

from common.core.config import settings
from common.core.redis_client import build_redis_url, get_redis_client, redis_key
from common.utils.utils import AppLogUtil

try:
    from redis.exceptions import RedisError
except ModuleNotFoundError:
    RedisError = Exception


class ChatGenerationConcurrencyError(Exception):
    def __init__(self, limit: int, retry_after_seconds: int = 0):
        self.limit = limit
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"当前账号已有智能报表正在生成，请等待当前生成完成后再发起新的问题。"
        )


@dataclass
class ChatGenerationLease:
    user_id: int | str
    token: str
    redis_key: str | None = None

    async def release(self) -> None:
        if self.redis_key:
            try:
                await get_redis_client().zrem(self.redis_key, self.token)
                return
            except RedisError:
                AppLogUtil.exception("Redis chat generation concurrency release failed")
        _memory_release(str(self.user_id), self.token)

    def release_sync(self) -> None:
        if self.redis_key:
            import redis as sync_redis

            client = None
            try:
                client = sync_redis.Redis.from_url(
                    build_redis_url(),
                    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                    socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
                )
                client.zrem(self.redis_key, self.token)
                return
            except RedisError:
                AppLogUtil.exception("Redis chat generation concurrency sync release failed")
            finally:
                if client is not None:
                    client.close()
        _memory_release(str(self.user_id), self.token)


_memory_lock = Lock()
_memory_slots: dict[str, dict[str, float]] = {}


def _limit(value: int | None = None) -> int:
    configured = settings.CHAT_MAX_CONCURRENT_GENERATIONS_PER_USER if value is None else value
    return max(1, int(configured or 1))


def _ttl(value: int | None = None) -> int:
    configured = settings.CHAT_GENERATION_CONCURRENCY_SLOT_TTL_SECONDS if value is None else value
    return max(30, int(configured or 600))


def _memory_prune(user_key: str, now: float, ttl: int) -> dict[str, float]:
    slots = _memory_slots.setdefault(user_key, {})
    expired = [token for token, started_at in slots.items() if now - started_at >= ttl]
    for token in expired:
        slots.pop(token, None)
    return slots


def _memory_acquire(user_id: int | str, token: str, limit: int, ttl: int) -> ChatGenerationLease:
    user_key = str(user_id)
    now = time.time()
    with _memory_lock:
        slots = _memory_prune(user_key, now, ttl)
        if len(slots) >= limit:
            oldest = min(slots.values()) if slots else now
            retry_after = max(1, int(ttl - (now - oldest)))
            raise ChatGenerationConcurrencyError(limit=limit, retry_after_seconds=retry_after)
        slots[token] = now
    return ChatGenerationLease(user_id=user_id, token=token)


def _memory_release(user_id: str, token: str) -> None:
    with _memory_lock:
        slots = _memory_slots.get(user_id)
        if not slots:
            return
        slots.pop(token, None)
        if not slots:
            _memory_slots.pop(user_id, None)


async def _redis_acquire(user_id: int | str, token: str, limit: int, ttl: int) -> ChatGenerationLease:
    key = redis_key("chat", "generation", "running", user_id)
    now = time.time()
    script = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local token = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - ttl)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry_after = ttl
  if oldest[2] then
    retry_after = math.max(1, math.ceil(ttl - (now - tonumber(oldest[2]))))
  end
  redis.call('EXPIRE', key, ttl)
  return {0, count, retry_after}
end
redis.call('ZADD', key, now, token)
redis.call('EXPIRE', key, ttl)
return {1, count + 1, 0}
"""
    result = await get_redis_client().eval(script, 1, key, now, ttl, limit, token)
    acquired = int(result[0]) == 1
    if not acquired:
        raise ChatGenerationConcurrencyError(
            limit=limit,
            retry_after_seconds=int(result[2] or 0),
        )
    return ChatGenerationLease(user_id=user_id, token=token, redis_key=key)


async def acquire_chat_generation_lease(
    user_id: int | str,
    *,
    enabled: bool | None = None,
    limit: int | None = None,
    ttl_seconds: int | None = None,
) -> ChatGenerationLease | None:
    limit_enabled = (
        settings.CHAT_GENERATION_CONCURRENCY_LIMIT_ENABLED if enabled is None else enabled
    )
    if not limit_enabled:
        return None

    limit = _limit(limit)
    ttl = _ttl(ttl_seconds)
    token = uuid.uuid4().hex
    if (settings.CACHE_TYPE or "").lower() == "redis":
        try:
            return await _redis_acquire(user_id, token, limit, ttl)
        except ChatGenerationConcurrencyError:
            raise
        except RedisError:
            AppLogUtil.exception(
                "Redis chat generation concurrency limiter unavailable, falling back to process memory"
            )
    return _memory_acquire(user_id, token, limit, ttl)


def reset_memory_chat_generation_limiter() -> None:
    with _memory_lock:
        _memory_slots.clear()
