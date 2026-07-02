import asyncio
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from apps.system.api.task_queue import _can_read_task
from common.core import task_queue
from common.core.config import settings
from common.core.task_queue import TaskStatus


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.lists = defaultdict(list)

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def delete(self, key):
        existed = key in self.values
        self.values.pop(key, None)
        return 1 if existed else 0

    async def get(self, key):
        return self.values.get(key)

    async def lpush(self, key, *values):
        for value in values:
            self.lists[key].insert(0, value)
        return len(self.lists[key])

    async def brpoplpush(self, source, destination, timeout=0):
        if not self.lists[source]:
            return None
        value = self.lists[source].pop()
        self.lists[destination].insert(0, value)
        return value

    async def lrem(self, key, count, value):
        values = self.lists[key]
        original_len = len(values)
        self.lists[key] = [item for item in values if item != value]
        return original_len - len(self.lists[key])

    async def llen(self, key):
        return len(self.lists[key])

    async def lrange(self, key, start, end):
        values = self.lists[key]
        if end == -1:
            return values[start:]
        return values[start:end + 1]

    async def ping(self):
        return True


def _install_fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(task_queue, "get_redis_client", lambda: fake)
    monkeypatch.setattr(task_queue, "record_tenant_usage_detached", lambda **kwargs: True)
    monkeypatch.setattr(
        task_queue,
        "check_tenant_usage_quota_detached",
        lambda **kwargs: SimpleNamespace(allowed=True),
    )
    monkeypatch.setattr(settings, "TASK_QUEUE_NAME", "test")
    monkeypatch.setattr(settings, "TASK_QUEUE_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "TASK_QUEUE_POLL_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(settings, "TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(settings, "TASK_QUEUE_MAX_PENDING_PER_TENANT", 0)
    monkeypatch.setattr(settings, "TASK_QUEUE_MAX_PROCESSING_PER_TENANT", 0)
    return fake


def test_task_moves_through_processing_queue_and_acks(monkeypatch):
    _install_fake_redis(monkeypatch)
    task_queue._task_handlers["test.echo"] = lambda payload: {"echo": payload}

    async def scenario():
        task = await task_queue.enqueue_task("test.echo", {"value": 1}, max_attempts=2)
        assert await task_queue.queue_size() == 1

        claimed = await task_queue._claim_task()
        assert claimed == task["id"]
        assert await task_queue.queue_size() == 0
        assert await task_queue.processing_size() == 1

        result = await task_queue.run_task(claimed, worker_name="worker-1")
        assert result["status"] == TaskStatus.SUCCEEDED.value
        assert result["result"] == {"echo": {"value": 1}}
        assert await task_queue.processing_size() == 0

    asyncio.run(scenario())


def test_failed_task_is_requeued_until_max_attempts(monkeypatch):
    _install_fake_redis(monkeypatch)
    calls = {"count": 0}

    def flaky_handler(payload):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary")
        return {"ok": True}

    task_queue._task_handlers["test.flaky"] = flaky_handler

    async def scenario():
        task = await task_queue.enqueue_task("test.flaky", max_attempts=2)
        first_claim = await task_queue._claim_task()
        first_result = await task_queue.run_task(first_claim, worker_name="worker-1")
        assert first_result["status"] == TaskStatus.PENDING.value
        assert first_result["attempts"] == 1
        assert await task_queue.queue_size() == 1
        assert await task_queue.processing_size() == 0

        second_claim = await task_queue._claim_task()
        assert second_claim == task["id"]
        second_result = await task_queue.run_task(second_claim, worker_name="worker-1")
        assert second_result["status"] == TaskStatus.SUCCEEDED.value
        assert second_result["attempts"] == 2

    asyncio.run(scenario())


def test_recover_stale_running_task_returns_it_to_pending(monkeypatch):
    _install_fake_redis(monkeypatch)
    task_queue._task_handlers["test.echo"] = lambda payload: payload

    async def scenario():
        task = await task_queue.enqueue_task("test.echo", max_attempts=2)
        claimed = await task_queue._claim_task()
        stored = await task_queue.get_task(claimed)
        stored["status"] = TaskStatus.RUNNING.value
        stored["attempts"] = 1
        stored["started_at"] = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        stored["worker"] = "lost-worker"
        await task_queue._save_task(stored)

        recovered = await task_queue.recover_stale_tasks(stale_after_seconds=1)
        refreshed = await task_queue.get_task(task["id"])

        assert recovered == {"recovered": 1, "removed": 0, "failed": 0}
        assert refreshed["status"] == TaskStatus.PENDING.value
        assert refreshed["worker"] is None
        assert await task_queue.queue_size() == 1
        assert await task_queue.processing_size() == 0

    asyncio.run(scenario())


def test_recover_stale_task_fails_after_max_attempts(monkeypatch):
    _install_fake_redis(monkeypatch)
    task_queue._task_handlers["test.echo"] = lambda payload: payload

    async def scenario():
        task = await task_queue.enqueue_task("test.echo", max_attempts=1)
        claimed = await task_queue._claim_task()
        stored = await task_queue.get_task(claimed)
        stored["status"] = TaskStatus.RUNNING.value
        stored["attempts"] = 1
        stored["started_at"] = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        await task_queue._save_task(stored)

        recovered = await task_queue.recover_stale_tasks(stale_after_seconds=1)
        refreshed = await task_queue.get_task(task["id"])

        assert recovered == {"recovered": 0, "removed": 0, "failed": 1}
        assert refreshed["status"] == TaskStatus.FAILED.value
        assert await task_queue.queue_size() == 0
        assert await task_queue.processing_size() == 0

    asyncio.run(scenario())


def test_task_state_is_scoped_by_tenant(monkeypatch):
    fake = _install_fake_redis(monkeypatch)
    task_queue._task_handlers["test.tenant_scope"] = lambda payload: payload

    async def scenario():
        task = await task_queue.enqueue_task("test.tenant_scope", {"value": 1}, tenant_id=42)

        assert task["tenant_id"] == 42
        assert await task_queue.get_task(task["id"], tenant_id=42) is not None
        assert await task_queue.get_task(task["id"], tenant_id=43) is None
        assert f"{settings.REDIS_KEY_PREFIX}:tenant:42:task:item:{task['id']}" in fake.values

    asyncio.run(scenario())


def test_worker_exposes_current_task_tenant_context(monkeypatch):
    _install_fake_redis(monkeypatch)

    def handler(_payload):
        return {"tenant_id": task_queue.current_task_tenant_id()}

    task_queue._task_handlers["test.tenant_context"] = handler

    async def scenario():
        task = await task_queue.enqueue_task("test.tenant_context", tenant_id=77)
        claimed = await task_queue._claim_task()
        result = await task_queue.run_task(claimed, worker_name="worker-1")

        assert claimed == task["id"]
        assert result["status"] == TaskStatus.SUCCEEDED.value
        assert result["result"] == {"tenant_id": 77}

    asyncio.run(scenario())


def test_enqueue_rejects_when_tenant_pending_limit_is_reached(monkeypatch):
    _install_fake_redis(monkeypatch)
    monkeypatch.setattr(settings, "TASK_QUEUE_MAX_PENDING_PER_TENANT", 1)
    task_queue._task_handlers["test.limited"] = lambda payload: payload

    async def scenario():
        await task_queue.enqueue_task("test.limited", tenant_id=10)
        assert await task_queue.tenant_queue_size(10) == 1
        try:
            await task_queue.enqueue_task("test.limited", tenant_id=10)
        except RuntimeError as exc:
            assert "Tenant 10 task queue is full" in str(exc)
        else:
            raise AssertionError("tenant pending limit should reject the second task")

        await task_queue.enqueue_task("test.limited", tenant_id=11)
        assert await task_queue.tenant_queue_size(11) == 1

    asyncio.run(scenario())


def test_enqueue_rejects_when_tenant_task_quota_is_exceeded(monkeypatch):
    _install_fake_redis(monkeypatch)
    monkeypatch.setattr(
        task_queue,
        "check_tenant_usage_quota_detached",
        lambda **kwargs: SimpleNamespace(allowed=False, used=10, limit=10, window="daily"),
    )
    task_queue._task_handlers["test.quota"] = lambda payload: payload

    async def scenario():
        try:
            await task_queue.enqueue_task("test.quota", tenant_id=10)
        except RuntimeError as exc:
            assert "Tenant 10 task quota exceeded" in str(exc)
        else:
            raise AssertionError("tenant task quota should reject enqueue")

    asyncio.run(scenario())


def test_enqueue_task_deduplicates_pending_task_by_key(monkeypatch):
    _install_fake_redis(monkeypatch)
    task_queue._task_handlers["test.dedupe"] = lambda payload: payload

    async def scenario():
        first = await task_queue.enqueue_task("test.dedupe", {"ids": [1]}, tenant_id=10, dedupe_key="same")
        second = await task_queue.enqueue_task("test.dedupe", {"ids": [1]}, tenant_id=10, dedupe_key="same")

        assert second["id"] == first["id"]
        assert await task_queue.queue_size() == 1
        assert await task_queue.tenant_queue_size(10) == 1

        claimed = await task_queue._claim_task()
        finished = await task_queue.run_task(claimed, worker_name="worker-1")
        assert finished["status"] == TaskStatus.SUCCEEDED.value

        third = await task_queue.enqueue_task("test.dedupe", {"ids": [1]}, tenant_id=10, dedupe_key="same")
        assert third["id"] != first["id"]
        assert await task_queue.queue_size() == 1

    asyncio.run(scenario())


def test_claim_skips_tenant_when_processing_limit_is_reached(monkeypatch):
    _install_fake_redis(monkeypatch)
    monkeypatch.setattr(settings, "TASK_QUEUE_MAX_PROCESSING_PER_TENANT", 1)
    task_queue._task_handlers["test.fair"] = lambda payload: payload

    async def scenario():
        tenant_one_first = await task_queue.enqueue_task("test.fair", {"item": "t1-first"}, tenant_id=1)
        tenant_one_second = await task_queue.enqueue_task("test.fair", {"item": "t1-second"}, tenant_id=1)
        tenant_two = await task_queue.enqueue_task("test.fair", {"item": "t2"}, tenant_id=2)

        first_claim = await task_queue._claim_task()
        assert first_claim == tenant_one_first["id"]
        assert await task_queue.tenant_processing_size(1) == 1

        second_claim = await task_queue._claim_task()
        assert second_claim == tenant_two["id"]
        assert await task_queue.tenant_processing_size(2) == 1
        assert await task_queue.tenant_queue_size(1) == 1

        first_result = await task_queue.run_task(first_claim, worker_name="worker-1")
        assert first_result["status"] == TaskStatus.SUCCEEDED.value
        assert await task_queue.tenant_processing_size(1) == 0

        third_claim = await task_queue._claim_task()
        assert third_claim == tenant_one_second["id"]

    asyncio.run(scenario())


def test_task_read_permission_requires_current_tenant():
    tenant_one_admin = SimpleNamespace(id=1, system_role="system_admin", tenant_id=1)
    tenant_one_user = SimpleNamespace(id=2, system_role="", tenant_id=1)

    assert _can_read_task({"created_by": 2, "tenant_id": 1}, tenant_one_admin) is True
    assert _can_read_task({"created_by": 2, "tenant_id": 2}, tenant_one_admin) is False
    assert _can_read_task({"created_by": 2, "tenant_id": 1}, tenant_one_user) is True
    assert _can_read_task({"created_by": 3, "tenant_id": 1}, tenant_one_user) is False
