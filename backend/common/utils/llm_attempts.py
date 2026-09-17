"""Request-local SDK retry observation without changing retry behavior."""
from contextlib import contextmanager
from contextvars import ContextVar

_retry_observer = ContextVar('llm_retry_observer', default=None)


def record_llm_retry():
    observer = _retry_observer.get()
    if observer:
        observer(1)


@contextmanager
def observe_llm_retries(observer):
    token = _retry_observer.set(observer)
    try:
        yield
    finally:
        _retry_observer.reset(token)
