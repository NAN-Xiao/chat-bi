import asyncio
import os
from collections import defaultdict

import pytest

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from sqlmodel import Session, create_engine

from apps.system.models.tenant import TenantModel
from common.core import tenant_rate_limiter
from common.core.config import settings


class FakeRedis:
    def __init__(self):
        self.values = defaultdict(int)
        self.expirations = {}

    async def incr(self, key):
        self.values[key] += 1
        return self.values[key]

    async def expire(self, key, seconds):
        self.expirations[key] = seconds
        return True


def _enable_memory_limiter(monkeypatch, limit=2):
    tenant_rate_limiter.reset_memory_tenant_rate_limiter()
    monkeypatch.setattr(settings, "TENANT_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_TYPE", "memory")
    monkeypatch.setattr(settings, "TENANT_CHAT_REQUESTS_PER_MINUTE", limit)


def test_tenant_rate_limit_isolated_by_tenant(monkeypatch):
    _enable_memory_limiter(monkeypatch, limit=2)

    async def scenario():
        first = await tenant_rate_limiter.consume_tenant_rate_limit(10, "chat")
        second = await tenant_rate_limiter.consume_tenant_rate_limit(10, "chat")
        third = await tenant_rate_limiter.consume_tenant_rate_limit(10, "chat")
        other_tenant = await tenant_rate_limiter.consume_tenant_rate_limit(11, "chat")

        assert first.allowed
        assert second.allowed
        assert not third.allowed
        assert third.retry_after_seconds > 0
        assert other_tenant.allowed

    asyncio.run(scenario())


def test_tenant_rate_limit_uses_redis_key_and_ttl(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(tenant_rate_limiter, "get_redis_client", lambda: fake)
    monkeypatch.setattr(settings, "TENANT_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_TYPE", "redis")
    monkeypatch.setattr(settings, "TENANT_ANALYSIS_REQUESTS_PER_MINUTE", 1)
    monkeypatch.setattr(settings, "REDIS_KEY_PREFIX", "test-prefix")

    async def scenario():
        first = await tenant_rate_limiter.consume_tenant_rate_limit(42, "analysis")
        second = await tenant_rate_limiter.consume_tenant_rate_limit(42, "analysis")

        assert first.allowed
        assert not second.allowed
        key = next(iter(fake.values))
        assert key.startswith("test-prefix:tenant:42:rate_limit:analysis:")
        assert fake.expirations[key] > 0

    asyncio.run(scenario())


def test_enabled_tenant_rate_limit_requires_tenant_context(monkeypatch):
    _enable_memory_limiter(monkeypatch, limit=2)

    async def scenario():
        with pytest.raises(ValueError):
            await tenant_rate_limiter.consume_tenant_rate_limit(None, "chat")

    asyncio.run(scenario())


def test_disabled_tenant_rate_limit_allows_requests(monkeypatch):
    tenant_rate_limiter.reset_memory_tenant_rate_limiter()
    monkeypatch.setattr(settings, "TENANT_RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "CACHE_TYPE", "memory")
    monkeypatch.setattr(settings, "TENANT_CHAT_REQUESTS_PER_MINUTE", 1)

    async def scenario():
        first = await tenant_rate_limiter.consume_tenant_rate_limit(10, "chat")
        second = await tenant_rate_limiter.consume_tenant_rate_limit(10, "chat")

        assert first.allowed
        assert second.allowed

    asyncio.run(scenario())


def test_resolve_tenant_rate_limit_uses_tenant_plan_override(monkeypatch):
    engine = create_engine("sqlite://")
    TenantModel.__table__.create(engine)
    monkeypatch.setattr(settings, "TENANT_ANALYSIS_REQUESTS_PER_MINUTE", 1)
    monkeypatch.setattr(
        settings,
        "TENANT_RATE_LIMIT_PLAN_OVERRIDES",
        '{"enterprise":{"analysis_requests_per_minute":7}}',
    )

    with Session(engine) as session:
        session.add(TenantModel(id=42, name="Tenant 42", status=1, plan="enterprise"))
        session.commit()

        limit = tenant_rate_limiter.resolve_tenant_rate_limit(session, 42, "analysis")

    assert limit == 7


def test_resolve_tenant_rate_limit_falls_back_to_global_limit(monkeypatch):
    engine = create_engine("sqlite://")
    TenantModel.__table__.create(engine)
    monkeypatch.setattr(settings, "TENANT_CHAT_REQUESTS_PER_MINUTE", 5)
    monkeypatch.setattr(settings, "TENANT_RATE_LIMIT_PLAN_OVERRIDES", "")

    with Session(engine) as session:
        session.add(TenantModel(id=43, name="Tenant 43", status=1, plan="unknown"))
        session.commit()

        limit = tenant_rate_limiter.resolve_tenant_rate_limit(session, 43, "chat")

    assert limit == 5

