"""SQL generation must stop work when its request lifetime ends."""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import time
from types import SimpleNamespace

import pytest


def lifecycle():
    name = "apps.dashboard.crud.sql_generation_lifecycle"
    assert importlib.util.find_spec(name) is not None, "SQL generation has no request lifetime boundary"
    return importlib.import_module(name)


def test_generation_context_is_propagated_and_reset():
    module = lifecycle()

    async def scenario():
        async def operation():
            run = module.current_generation_run()
            assert run is not None
            assert run.request_id
            assert run.started_at <= time.monotonic() < run.deadline
            assert run.deadline - run.started_at == pytest.approx(1)
            assert await asyncio.to_thread(module.current_generation_run) is run
            run.llm_calls += 1
            return run

        run = await module.run_sql_generation(operation(), timeout_seconds=1)
        assert run.llm_calls == 1
        assert module.current_generation_run() is None

    asyncio.run(scenario())


def test_concurrent_requests_do_not_share_generation_context():
    module = lifecycle()

    async def scenario():
        async def operation():
            await asyncio.sleep(0)
            return module.current_generation_run()

        first, second = await asyncio.gather(
            module.run_sql_generation(operation()),
            module.run_sql_generation(operation()),
        )
        assert first is not second
        assert first.request_id != second.request_id

    asyncio.run(scenario())


@pytest.mark.parametrize("ending", ["timeout", "disconnect", "caller_cancel"])
def test_request_ending_cancels_generation_and_cleans_watchers(ending):
    module = lifecycle()

    async def scenario():
        started = asyncio.Event()
        stopped = asyncio.Event()
        disconnected = asyncio.Event()
        baseline = asyncio.all_tasks()

        async def operation():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        async def is_disconnected():
            return disconnected.is_set()

        task = asyncio.create_task(module.run_sql_generation(
            operation(), is_disconnected=is_disconnected,
            timeout_seconds=0.02 if ending == "timeout" else 1,
        ))
        await started.wait()
        if ending == "disconnect":
            disconnected.set()
            expected = module.SqlGenerationDisconnected
        elif ending == "caller_cancel":
            task.cancel()
            expected = asyncio.CancelledError
        else:
            expected = module.SqlGenerationTimeout
        with pytest.raises(expected):
            await task
        assert stopped.is_set(), "LLM work must be cancelled before returning"
        assert asyncio.all_tasks() == baseline, "disconnect watcher must not outlive the request"
        assert module.current_generation_run() is None

    asyncio.run(scenario())


def test_operation_timeout_is_not_misclassified_as_total_budget_timeout():
    module = lifecycle()
    original = TimeoutError("LLM request timeout")

    async def operation():
        raise original

    with pytest.raises(TimeoutError) as failure:
        asyncio.run(module.run_sql_generation(operation()))
    assert failure.value is original


def test_default_deadline_uses_configured_total_budget(monkeypatch):
    module = lifecycle()
    monkeypatch.setattr(module.settings, "LLM_TASK_MAX_WAIT_SECONDS", 37)

    async def operation():
        run = module.current_generation_run()
        return run.deadline - run.started_at

    assert asyncio.run(module.run_sql_generation(operation())) == pytest.approx(37)


def test_success_cleans_disconnect_watcher():
    module = lifecycle()

    async def scenario():
        baseline = asyncio.all_tasks()

        async def operation():
            await asyncio.sleep(0)
            return "SELECT 1"

        async def is_disconnected():
            return False

        assert await module.run_sql_generation(operation(), is_disconnected=is_disconnected) == "SELECT 1"
        assert asyncio.all_tasks() == baseline

    asyncio.run(scenario())


@pytest.mark.parametrize("result, status", [(SimpleNamespace(success=False), "validation_failed"), ({"success": False}, "validation_failed"), (SimpleNamespace(success=True), "success")])
def test_completion_logs_outcome_and_actual_network_attempts(monkeypatch, result, status):
    module = lifecycle()
    records = []
    monkeypatch.setattr(module.AppLogUtil, "info", lambda message, *args: records.append(message % args))

    async def operation():
        run = module.current_generation_run()
        assert run.http_attempts == 0
        assert run.network_retries == 0
        run.http_attempts = 3
        run.network_retries = 1
        run.llm_calls = 2
        return result

    assert asyncio.run(module.run_sql_generation(operation())) is result
    assert len(records) == 1
    assert f"status={status}" in records[0]
    assert "http_attempts=3" in records[0]
    assert "network_retries=1" in records[0]
    assert "llm_calls=2" in records[0]


def test_node_budget_timeout_is_logged_as_timeout(monkeypatch):
    module = lifecycle()
    records = []
    monkeypatch.setattr(module.AppLogUtil, "info", lambda message, *args: records.append(message % args))

    async def operation():
        raise module.SqlGenerationTimeout("node budget exhausted")

    with pytest.raises(module.SqlGenerationTimeout):
        asyncio.run(module.run_sql_generation(operation()))
    assert "status=timeout" in records[0]
