"""Correlate model rounds and OpenAI HTTP attempts without logging credentials."""
from contextlib import contextmanager
from contextvars import ContextVar
import time

from apps.dashboard.crud.sql_generation_lifecycle import current_generation_run, SqlGenerationTimeout
from common.utils.utils import AppLogUtil


_invocation = ContextVar("dashboard_sql_invocation", default=None)


def check_generation_deadline() -> None:
    run = current_generation_run()
    if run is not None and time.monotonic() >= run.deadline:
        raise SqlGenerationTimeout("SQL generation total time budget exceeded")


def _record_http_attempt(request) -> None:
    run = current_generation_run()
    invocation = _invocation.get()
    if run is None or invocation is None:
        return
    run.http_attempts += 1
    retry = int(request.headers.get("x-stainless-retry-count", "0"))
    run.network_retries += int(retry > 0)
    AppLogUtil.info(
        f"Dashboard SQL model HTTP attempt: request_id={run.request_id}, "
        f"node={invocation[0]}, llm_call={invocation[1]}, http_attempt={run.http_attempts}, sdk_retry={retry}"
    )


async def _record_async_http_attempt(request) -> None:
    _record_http_attempt(request)


def _attach_http_observers(llm) -> None:
    # Observe the SDK's actual HTTP client so network retries are distinguished
    # from graph repair rounds. Cached model clients retain one context-aware hook.
    for name, hook in (("root_client", _record_http_attempt), ("root_async_client", _record_async_http_attempt)):
        root = getattr(llm, name, None)
        client = getattr(root, "_client", None)
        hooks = getattr(client, "event_hooks", None)
        if isinstance(hooks, dict):
            callbacks = hooks.setdefault("request", [])
            if hook not in callbacks:
                callbacks.append(hook)


@contextmanager
def llm_invocation(llm, node):
    check_generation_deadline()
    run = current_generation_run()
    if run is not None:
        run.llm_calls += 1
    invocation = (node or "generate_sql", run.llm_calls if run else 0)
    token = _invocation.set(invocation)
    _attach_http_observers(llm)
    started = time.monotonic()
    status = "failed"
    try:
        yield
        status = "returned"
    finally:
        _invocation.reset(token)
        AppLogUtil.info(
            f"Dashboard SQL model round: request_id={run.request_id if run else '-'}, "
            f"node={invocation[0]}, llm_call={invocation[1]}, status={status}, "
            f"elapsed_ms={int((time.monotonic() - started) * 1000)}"
        )
