"""
脚本说明：验证任务队列 worker 的有界并发和优雅停机行为。
"""
from __future__ import annotations

import asyncio

from common.core import task_queue
from common.core.config import settings


def _patch_worker_dependencies(monkeypatch, *, task_ids: list[str], task_seconds: float):
    """
    是什么：_patch_worker_dependencies 把 worker_loop 的 Redis 依赖换成内存假实现。
    谁调用：本文件的测试用例。
    做了什么：返回记录并发峰值和完成顺序的状态字典。
    """
    pending = list(task_ids)
    state = {"current": 0, "peak": 0, "completed": []}

    async def fake_claim(queue):
        if pending:
            return pending.pop(0)
        await asyncio.sleep(0.01)
        return None

    async def fake_run(task_id, *, worker_name=None, queue_name=None):
        state["current"] += 1
        state["peak"] = max(state["peak"], state["current"])
        await asyncio.sleep(task_seconds)
        state["current"] -= 1
        state["completed"].append(task_id)

    async def fake_recover(**kwargs):
        return {"recovered": 0, "removed": 0, "failed": 0}

    monkeypatch.setattr(task_queue, "_claim_task", fake_claim)
    monkeypatch.setattr(task_queue, "run_task", fake_run)
    monkeypatch.setattr(task_queue, "recover_stale_tasks", fake_recover)
    return state


def test_worker_loop_runs_tasks_concurrently(monkeypatch) -> None:
    """
    是什么：并发额度充足时，多个任务应并行执行而不是串行排队。
    """
    monkeypatch.setattr(settings, "TASK_WORKER_CONCURRENCY", 3)
    state = _patch_worker_dependencies(monkeypatch, task_ids=["t1", "t2", "t3"], task_seconds=0.2)

    async def scenario():
        stop_event = asyncio.Event()
        loop_task = asyncio.create_task(task_queue.worker_loop(queue_name="test-queue", stop_event=stop_event))
        await asyncio.sleep(0.5)
        stop_event.set()
        await asyncio.wait_for(loop_task, timeout=5)

    asyncio.run(scenario())
    assert state["peak"] == 3
    assert sorted(state["completed"]) == ["t1", "t2", "t3"]


def test_worker_loop_respects_concurrency_limit(monkeypatch) -> None:
    """
    是什么：在途任务数不得超过 TASK_WORKER_CONCURRENCY。
    """
    monkeypatch.setattr(settings, "TASK_WORKER_CONCURRENCY", 2)
    state = _patch_worker_dependencies(
        monkeypatch, task_ids=["t1", "t2", "t3", "t4"], task_seconds=0.15
    )

    async def scenario():
        stop_event = asyncio.Event()
        loop_task = asyncio.create_task(task_queue.worker_loop(queue_name="test-queue", stop_event=stop_event))
        await asyncio.sleep(0.8)
        stop_event.set()
        await asyncio.wait_for(loop_task, timeout=5)

    asyncio.run(scenario())
    assert state["peak"] == 2
    assert sorted(state["completed"]) == ["t1", "t2", "t3", "t4"]


def test_worker_loop_drains_in_flight_tasks_on_stop(monkeypatch) -> None:
    """
    是什么：停机时必须等在途任务执行完再退出，不能丢任务。
    """
    monkeypatch.setattr(settings, "TASK_WORKER_CONCURRENCY", 2)
    state = _patch_worker_dependencies(monkeypatch, task_ids=["t1", "t2"], task_seconds=0.4)

    async def scenario():
        stop_event = asyncio.Event()
        loop_task = asyncio.create_task(task_queue.worker_loop(queue_name="test-queue", stop_event=stop_event))
        await asyncio.sleep(0.1)
        stop_event.set()
        await asyncio.wait_for(loop_task, timeout=5)

    asyncio.run(scenario())
    assert sorted(state["completed"]) == ["t1", "t2"]
