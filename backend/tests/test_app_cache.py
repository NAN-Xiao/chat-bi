"""
脚本说明：验证应用缓存装饰器的 key、清理顺序和故障降级行为。
"""
from __future__ import annotations

import asyncio

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.coder import JsonCoder
from redis.exceptions import RedisError

from common.core import app_cache
from common.core.app_cache import cache, clear_cache
from common.core.config import settings


class _FailingClearBackend(InMemoryBackend):
    """
    类说明：_FailingClearBackend 模拟 Redis 清理失败。
    """

    async def clear(self, namespace=None, key=None):
        raise RedisError("redis down")


class _RecordingBackend(InMemoryBackend):
    """
    类说明：_RecordingBackend 记录写缓存时使用的 TTL。
    """

    def __init__(self):
        self.expires: list[int | None] = []

    async def set(self, key: str, value: bytes, expire: int | None = None) -> None:
        self.expires.append(expire)
        await super().set(key, value, expire)


class _FakeSession:
    """
    类说明：_FakeSession 提供最小事务状态，用于验证 after_commit 注册。
    """

    def in_transaction(self) -> bool:
        return True


def _reset_cache(monkeypatch, backend=None) -> None:
    monkeypatch.setattr(settings, "CACHE_TYPE", "memory")
    monkeypatch.setattr(settings, "CACHE_REDIS_PREFIX", "test-cache")
    FastAPICache.reset()
    InMemoryBackend._store.clear()
    FastAPICache.init(backend or InMemoryBackend(), prefix=settings.CACHE_REDIS_PREFIX, coder=JsonCoder)


def _key(*parts: object) -> str:
    return ":".join(str(part).strip(":") for part in parts)


def test_cache_uses_platform_prefix_and_jitter(monkeypatch) -> None:
    """
    是什么：缓存 key 应使用平台 Redis 前缀，并给 TTL 加抖动。
    """
    backend = _RecordingBackend()
    _reset_cache(monkeypatch, backend)
    monkeypatch.setattr(app_cache.random, "randint", lambda _left, _right: 7)

    calls = {"count": 0}

    @cache(expire=100, namespace="shuzhi:auth", cacheName="user:info", keyExpression="user_id")
    async def load_user(*, user_id: int):
        calls["count"] += 1
        return {"id": user_id}

    first = asyncio.run(load_user(user_id=123))
    second = asyncio.run(load_user(user_id=123))

    expected_key = _key("shuzhi", "platform", "cache", "test-cache", "shuzhi:auth", "user:info", 123)
    assert first == {"id": 123}
    assert second == {"id": 123}
    assert calls["count"] == 1
    assert expected_key in InMemoryBackend._store
    assert backend.expires == [107]


def test_clear_cache_runs_after_function_and_after_commit(monkeypatch) -> None:
    """
    是什么：带 Session 的清理应在业务函数成功后注册 after_commit，而不是先删缓存。
    """
    _reset_cache(monkeypatch)
    events: list[str] = []

    async def fake_clear(keys):
        events.append(f"clear:{keys[0]}")

    def fake_register(session, keys):
        events.append(f"register:{keys[0]}")
        return True

    monkeypatch.setattr(app_cache, "_clear_backend_keys", fake_clear)
    monkeypatch.setattr(app_cache, "_register_after_commit_clear", fake_register)

    @clear_cache(namespace="shuzhi:auth", cacheName="user:info", keyExpression="user_id")
    async def update_user(*, session, user_id: int):
        events.append("write")
        return "ok"

    result = asyncio.run(update_user(session=_FakeSession(), user_id=5))

    expected_key = _key("shuzhi", "platform", "cache", "test-cache", "shuzhi:auth", "user:info", 5)
    assert result == "ok"
    assert events == ["write", f"register:{expected_key}"]


def test_clear_cache_directly_deletes_without_pre_get(monkeypatch) -> None:
    """
    是什么：没有 Session 时清理在函数后直接 delete，不再先 get。
    """
    _reset_cache(monkeypatch)
    events: list[str] = []

    async def fake_clear(keys):
        events.append(f"clear:{keys[0]}")

    monkeypatch.setattr(app_cache, "_clear_backend_keys", fake_clear)
    monkeypatch.setattr(app_cache, "_register_after_commit_clear", lambda _session, _keys: False)

    @clear_cache(namespace="shuzhi:auth", cacheName="ask:info", keyExpression="access_key")
    async def clean_key(access_key: str):
        events.append("write")

    asyncio.run(clean_key("ak"))

    expected_key = _key("shuzhi", "platform", "cache", "test-cache", "shuzhi:auth", "ask:info", "ak")
    assert events == ["write", f"clear:{expected_key}"]


def test_clear_cache_failure_does_not_fail_business_flow(monkeypatch) -> None:
    """
    是什么：缓存清理失败时，写接口主流程仍应返回成功。
    """
    _reset_cache(monkeypatch, _FailingClearBackend())

    @clear_cache(namespace="shuzhi:auth", cacheName="ask:info", keyExpression="access_key")
    async def clean_key(access_key: str):
        return {"access_key": access_key}

    assert asyncio.run(clean_key("ak")) == {"access_key": "ak"}


def test_cache_miss_single_flight_for_concurrent_requests(monkeypatch) -> None:
    """
    是什么：同一 key 并发 miss 时只允许一个请求回源。
    """
    _reset_cache(monkeypatch)
    calls = {"count": 0}

    @cache(expire=100, namespace="shuzhi:auth", cacheName="user:info", keyExpression="user_id")
    async def slow_load(*, user_id: int):
        calls["count"] += 1
        await asyncio.sleep(0.01)
        return {"id": user_id}

    async def run_many():
        return await asyncio.gather(*(slow_load(user_id=1) for _ in range(8)))

    results = asyncio.run(run_many())

    assert results == [{"id": 1}] * 8
    assert calls["count"] == 1
