import asyncio
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from common.core import task_queue
from common.core.config import settings
from common.core.task_queue import TaskStatus


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.lists = defaultdict(list)

    async def set(self, key, value, ex=None):
        self.values[key] = value
        return True

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
    monkeypatch.setattr(settings, "TASK_QUEUE_NAME", "test")
    monkeypatch.setattr(settings, "TASK_QUEUE_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "TASK_QUEUE_POLL_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(settings, "TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS", 1)
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
