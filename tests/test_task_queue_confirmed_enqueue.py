import asyncio

import pytest

from common.core import task_queue, task_queue_enqueue
from test_task_queue_reliability import _install_fake_redis


def test_confirmed_enqueue_replaces_missing_deduped_task_without_orphan(monkeypatch):
    fake = _install_fake_redis(monkeypatch)
    task_queue._task_handlers["test.confirmed"] = lambda payload: payload

    async def scenario():
        first = await task_queue.enqueue_task_confirmed(
            "test.confirmed",
            {},
            tenant_id=7,
            queue_name="local-test",
            dedupe_key="job:missing",
        )
        first_id = first.task["id"]
        fake.values.pop(task_queue._task_key(first_id, 7), None)

        second = await task_queue.enqueue_task_confirmed(
            "test.confirmed",
            {},
            tenant_id=7,
            queue_name="local-test",
            dedupe_key="job:missing",
        )

        assert second.outcome is task_queue.EnqueueOutcome.ENQUEUED
        assert second.task["id"] != first_id
        assert fake.lists[task_queue._queue_key("local-test")] == [second.task["id"]]
        assert fake.lists[task_queue._tenant_pending_key(7, "local-test")] == [second.task["id"]]
        assert task_queue._task_tenant_index_key(first_id) not in fake.values

    asyncio.run(scenario())


def test_confirmed_enqueue_returns_unknown_after_post_commit_disconnect(monkeypatch):
    fake = _install_fake_redis(monkeypatch)
    fake.disconnect_after_eval = True
    task_queue._task_handlers["test.confirmed"] = lambda payload: payload

    async def scenario():
        result = await task_queue.enqueue_task_confirmed(
            "test.confirmed",
            {"value": 1},
            tenant_id=7,
            queue_name="local-test",
            dedupe_key="job:1",
        )

        assert result.outcome is task_queue.EnqueueOutcome.UNKNOWN
        assert result.task is not None
        task_id = result.task["id"]

        repaired = await task_queue.confirm_or_repair_task(
            task_id,
            tenant_id=7,
            queue_name="local-test",
        )
        assert repaired.outcome is task_queue.EnqueueOutcome.ENQUEUED
        assert repaired.task["id"] == task_id
        assert await task_queue.queue_size("local-test") == 1
        assert await task_queue.tenant_queue_size(7, "local-test") == 1

    asyncio.run(scenario())


def test_confirmed_enqueue_reconciles_deduped_task_after_post_commit_disconnect(monkeypatch):
    fake = _install_fake_redis(monkeypatch)
    task_queue._task_handlers["test.confirmed"] = lambda payload: payload

    async def scenario():
        first = await task_queue.enqueue_task_confirmed(
            "test.confirmed",
            {"value": 1},
            tenant_id=7,
            queue_name="local-test",
            dedupe_key="job:deduped-disconnect",
        )
        fake.disconnect_after_eval = True

        second = await task_queue.enqueue_task_confirmed(
            "test.confirmed",
            {"value": 2},
            tenant_id=7,
            queue_name="local-test",
            dedupe_key="job:deduped-disconnect",
        )

        assert second.outcome is task_queue.EnqueueOutcome.ENQUEUED
        assert second.task["id"] == first.task["id"]
        repaired = await task_queue.confirm_or_repair_task(
            second.task["id"],
            tenant_id=7,
            queue_name="local-test",
        )
        assert repaired.outcome is task_queue.EnqueueOutcome.ENQUEUED
        assert repaired.task["id"] == first.task["id"]

    asyncio.run(scenario())


def test_task_queue_platform_transport_keys_use_platform_scope(monkeypatch):
    monkeypatch.setattr(task_queue.settings, "REDIS_KEY_PREFIX", "test")

    assert task_queue._queue_key("local-test") == "test:platform:task:queue:local-test"
    assert task_queue._processing_key("local-test") == "test:platform:task:processing:local-test"
    assert task_queue._task_tenant_index_key("task-1") == "test:platform:task:tenant:task-1"


@pytest.mark.parametrize(
    ("result", "expected_code", "expected_message"),
    [
        (
            task_queue.EnqueueResult(
                outcome=task_queue.EnqueueOutcome.REJECTED,
                task=None,
                error_code="TENANT_SUBSCRIPTION_SUSPENDED",
            ),
            "TENANT_SUBSCRIPTION_SUSPENDED",
            "当前租户的任务提交已暂停，请联系管理员。",
        ),
        (
            task_queue.EnqueueResult(
                outcome=task_queue.EnqueueOutcome.REJECTED,
                task=None,
                error_code="TENANT_TASK_QUOTA_EXCEEDED",
            ),
            "TENANT_TASK_QUOTA_EXCEEDED",
            "当前租户的任务额度已用完，请稍后重试或联系管理员。",
        ),
        (
            task_queue.EnqueueResult(
                outcome=task_queue.EnqueueOutcome.REJECTED,
                task=None,
                error_code="TASK_QUEUE_FULL",
            ),
            "TASK_QUEUE_FULL",
            "当前任务队列繁忙，请稍后重试。",
        ),
        (
            task_queue.EnqueueResult(
                outcome=task_queue.EnqueueOutcome.UNKNOWN,
                task={"id": "task-unknown"},
                error_code="TASK_QUEUE_CONFIRMATION_REQUIRED",
            ),
            "TASK_QUEUE_CONFIRMATION_REQUIRED",
            "任务提交结果暂时无法确认，请稍后查询任务状态。",
        ),
        (
            task_queue.EnqueueResult(
                outcome=task_queue.EnqueueOutcome.REJECTED,
                task=None,
                error_code="TASK_QUEUE_UNAVAILABLE",
            ),
            "TASK_QUEUE_UNAVAILABLE",
            "任务提交失败，请稍后重试。",
        ),
    ],
)
def test_enqueue_task_adapter_raises_safe_chinese_message_with_error_code(
    monkeypatch,
    result,
    expected_code,
    expected_message,
):
    async def fake_enqueue_task_confirmed(*_args, **_kwargs):
        return result

    monkeypatch.setattr(task_queue, "enqueue_task_confirmed", fake_enqueue_task_confirmed)

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(task_queue.enqueue_task("test.confirmed", tenant_id=7))

    assert str(exc_info.value) == expected_message
    assert exc_info.value.error_code == expected_code


def test_confirmed_enqueue_rejects_before_lua_without_partial_state(monkeypatch):
    fake = _install_fake_redis(monkeypatch)
    fake.fail_ping = True
    task_queue._task_handlers["test.confirmed"] = lambda payload: payload

    async def scenario():
        result = await task_queue.enqueue_task_confirmed(
            "test.confirmed",
            {},
            tenant_id=7,
            queue_name="local-test",
        )

        assert result.outcome is task_queue.EnqueueOutcome.REJECTED
        assert result.task is None
        assert result.error_code == "TASK_QUEUE_UNAVAILABLE"
        assert fake.values == {}
        assert fake.lists == {}

    asyncio.run(scenario())


def test_confirmed_enqueue_rejects_when_redis_client_cannot_be_created(monkeypatch):
    _install_fake_redis(monkeypatch)
    task_queue._task_handlers["test.confirmed"] = lambda payload: payload

    def fail_client_creation():
        raise ValueError("invalid Redis configuration")

    monkeypatch.setattr(task_queue_enqueue, "get_redis_client", fail_client_creation)

    async def scenario():
        result = await task_queue.enqueue_task_confirmed(
            "test.confirmed",
            {},
            tenant_id=7,
            queue_name="local-test",
        )

        assert result.outcome is task_queue.EnqueueOutcome.REJECTED
        assert result.task is None
        assert result.error_code == "TASK_QUEUE_UNAVAILABLE"

    asyncio.run(scenario())


def test_confirmed_enqueue_stays_enqueued_when_usage_recording_fails(monkeypatch):
    _install_fake_redis(monkeypatch)
    task_queue._task_handlers["test.confirmed"] = lambda payload: payload

    def fail_usage_recording(**_kwargs):
        raise RuntimeError("usage backend unavailable")

    monkeypatch.setattr(
        task_queue_enqueue,
        "record_tenant_usage_detached",
        fail_usage_recording,
    )

    async def scenario():
        result = await task_queue.enqueue_task_confirmed(
            "test.confirmed",
            {},
            tenant_id=7,
            queue_name="local-test",
        )

        assert result.outcome is task_queue.EnqueueOutcome.ENQUEUED
        assert result.task is not None
        assert await task_queue.queue_size("local-test") == 1

    asyncio.run(scenario())


def test_confirm_or_repair_restores_exact_pending_task_once(monkeypatch):
    fake = _install_fake_redis(monkeypatch)
    task_queue._task_handlers["test.confirmed"] = lambda payload: payload

    async def scenario():
        result = await task_queue.enqueue_task_confirmed(
            "test.confirmed",
            {},
            tenant_id=7,
            queue_name="local-test",
        )
        task_id = result.task["id"]
        fake.lists[task_queue._queue_key("local-test")] = []
        fake.lists[task_queue._tenant_pending_key(7, "local-test")] = []
        fake.values.pop(task_queue._task_tenant_index_key(task_id), None)

        first = await task_queue.confirm_or_repair_task(
            task_id,
            tenant_id=7,
            queue_name="local-test",
        )
        second = await task_queue.confirm_or_repair_task(
            task_id,
            tenant_id=7,
            queue_name="local-test",
        )

        assert first.outcome is task_queue.EnqueueOutcome.ENQUEUED
        assert second.outcome is task_queue.EnqueueOutcome.ENQUEUED
        assert first.task["id"] == second.task["id"] == task_id
        assert fake.lists[task_queue._queue_key("local-test")] == [task_id]
        assert fake.lists[task_queue._tenant_pending_key(7, "local-test")] == [task_id]
        assert await task_queue.get_task(task_id, tenant_id=7) is not None

    asyncio.run(scenario())


def test_confirm_or_repair_returns_status_read_inside_repair_transaction(monkeypatch):
    fake = _install_fake_redis(monkeypatch)
    task_queue._task_handlers["test.confirmed"] = lambda payload: payload

    async def scenario():
        result = await task_queue.enqueue_task_confirmed(
            "test.confirmed",
            {},
            tenant_id=7,
            queue_name="local-test",
        )
        fake.repair_status_before_eval = "running"

        repaired = await task_queue.confirm_or_repair_task(
            result.task["id"],
            tenant_id=7,
            queue_name="local-test",
        )

        assert repaired.outcome is task_queue.EnqueueOutcome.ENQUEUED
        assert repaired.task["status"] == "running"

    asyncio.run(scenario())
