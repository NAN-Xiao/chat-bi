"""Request-scoped deadline, cancellation and telemetry for dashboard SQL generation."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TypeVar
from uuid import uuid4

from common.core.config import settings
from common.utils.utils import AppLogUtil

T = TypeVar("T")


@dataclass
class GenerationRun:
    request_id: str
    started_at: float
    deadline: float
    llm_calls: int = 0
    http_attempts: int = 0
    network_retries: int = 0


_generation_run: ContextVar[GenerationRun | None] = ContextVar("dashboard_sql_generation_run", default=None)


class SqlGenerationTimeout(TimeoutError):
    """The overall generation budget has expired."""


class SqlGenerationDisconnected(Exception):
    """The client disconnected before generation completed."""


def current_generation_run() -> GenerationRun | None:
    return _generation_run.get()


async def _wait_for_disconnect(is_disconnected: Callable[[], Awaitable[bool]]) -> None:
    while not await is_disconnected():
        await asyncio.sleep(0.1)


async def run_sql_generation(
    operation: Awaitable[T],
    *,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    wait_for_disconnect: Callable[[], Awaitable[None]] | None = None,
    timeout_seconds: float | None = None,
) -> T:
    """Run a fresh coroutine within the request budget, cancelling owned work on exit."""
    budget = settings.LLM_TASK_MAX_WAIT_SECONDS if timeout_seconds is None else timeout_seconds
    started_at = time.monotonic()
    run = GenerationRun(uuid4().hex, started_at, started_at + budget)
    token = _generation_run.set(run)
    operation_task = asyncio.ensure_future(operation)
    tasks = {operation_task}
    disconnect_task = None
    status = "error"
    try:
        if wait_for_disconnect is not None:
            disconnect_task = asyncio.create_task(wait_for_disconnect())
            tasks.add(disconnect_task)
        elif is_disconnected is not None:
            disconnect_task = asyncio.create_task(_wait_for_disconnect(is_disconnected))
            tasks.add(disconnect_task)
        done, _ = await asyncio.wait(
            tasks, timeout=max(0, run.deadline - time.monotonic()),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if disconnect_task in done:
            disconnect_task.result()
            status = "disconnected"
            raise SqlGenerationDisconnected("SQL generation client disconnected")
        if operation_task not in done:
            status = "timeout"
            raise SqlGenerationTimeout("SQL generation total time budget exceeded")
        result = operation_task.result()
        success = result.get("success") if isinstance(result, dict) else getattr(result, "success", None)
        status = "validation_failed" if success is False else "success"
        return result
    except SqlGenerationTimeout:
        status = "timeout"
        raise
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        _generation_run.reset(token)
        AppLogUtil.info(
            "Dashboard SQL generation finished: request_id=%s, status=%s, elapsed_ms=%s, llm_calls=%s, http_attempts=%s, network_retries=%s, budget_seconds=%s",
            run.request_id, status, int((time.monotonic() - run.started_at) * 1000),
            run.llm_calls, run.http_attempts, run.network_retries, budget,
        )
