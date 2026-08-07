"""Verify cutover readiness queries use scalar database results."""

from __future__ import annotations

from apps.knowledge_base.cutover_readiness import _count


class _Session:
    def __init__(self, value: int | None) -> None:
        self.value = value
        self.statement = None

    def scalar(self, statement):
        self.statement = statement
        return self.value


def test_count_reads_scalar_result() -> None:
    statement = object()
    session = _Session(7)

    assert _count(session, statement) == 7
    assert session.statement is statement


def test_count_treats_null_as_zero() -> None:
    assert _count(_Session(None), object()) == 0
