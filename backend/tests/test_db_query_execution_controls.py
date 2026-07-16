"""底层查询执行的行数上限与超时覆盖回归测试。"""

import json
from types import SimpleNamespace

from apps.db import db as db_module


class FakeKeys:
    def __init__(self, values: list[str]) -> None:
        self._keys = values


class FakeResult:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows
        self.fetchmany_sizes: list[int] = []
        self.fetchall_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def keys(self) -> FakeKeys:
        return FakeKeys(["value"])

    def fetchmany(self, size: int):
        self.fetchmany_sizes.append(size)
        return self.rows[:size]

    def fetchall(self):
        self.fetchall_calls += 1
        return list(self.rows)


class FakeSqlAlchemySession:
    def __init__(self, result: FakeResult) -> None:
        self.result = result

    def execute(self, statement, _params=None):
        sql = str(statement)
        if sql.lstrip().upper().startswith("SELECT"):
            return self.result
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_low_level_default_still_limits_rows_but_explicit_none_fetches_all(
    monkeypatch,
) -> None:
    rows = [(1,), (2,), (3,), (4,)]
    datasource = SimpleNamespace(type="pg", configuration="{}")
    monkeypatch.setattr(db_module.settings, "SHUZHI_QUERY_RESULT_MAX_ROWS", 2)

    ordinary_result = FakeResult(rows)
    monkeypatch.setattr(
        db_module,
        "get_session",
        lambda *_args, **_kwargs: FakeSqlAlchemySession(ordinary_result),
    )
    ordinary = db_module._unsafe_exec_sql_after_validation(
        datasource,
        "SELECT value FROM metrics",
        query_timeout=5,
    )

    roi_result = FakeResult(rows)
    monkeypatch.setattr(
        db_module,
        "get_session",
        lambda *_args, **_kwargs: FakeSqlAlchemySession(roi_result),
    )
    roi = db_module._unsafe_exec_sql_after_validation(
        datasource,
        "SELECT value FROM metrics",
        query_timeout=5,
        max_result_rows=None,
    )

    assert ordinary["data"] == [{"value": 1}, {"value": 2}]
    assert ordinary_result.fetchmany_sizes == [2]
    assert roi["data"] == [
        {"value": 1},
        {"value": 2},
        {"value": 3},
        {"value": 4},
    ]
    assert roi_result.fetchall_calls == 1


class FakeDmCursor:
    description = [("value",)]

    def __init__(self) -> None:
        self.execute_timeouts: list[int] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, _sql: str, *, timeout: int) -> None:
        self.execute_timeouts.append(timeout)

    def fetchmany(self, _size: int):
        return [(1,)]


class FakeDmConnection:
    def __init__(self, cursor: FakeDmCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def cursor(self) -> FakeDmCursor:
        return self._cursor


def test_dm_branch_uses_query_timeout_override(monkeypatch) -> None:
    cursor = FakeDmCursor()
    datasource = SimpleNamespace(type="dm", configuration="encrypted")
    configuration = json.dumps(
        {
            "host": "db",
            "port": 5236,
            "username": "user",
            "password": "secret",
            "database": "analytics",
            "timeout": 90,
        }
    )
    monkeypatch.setattr(db_module, "aes_decrypt", lambda _value: configuration)
    monkeypatch.setattr(
        db_module.dmPython,
        "connect",
        lambda **_kwargs: FakeDmConnection(cursor),
    )

    db_module._unsafe_exec_sql_after_validation(
        datasource,
        "SELECT 1 AS value",
        query_timeout=7,
    )

    assert cursor.execute_timeouts == [7]


def test_es_keeps_ordinary_30_second_default_and_accepts_explicit_override(
    monkeypatch,
) -> None:
    datasource = SimpleNamespace(type="es", configuration="encrypted")
    configuration = json.dumps(
        {
            "host": "https://es",
            "username": "user",
            "password": "secret",
            "timeout": 90,
        }
    )
    observed_timeouts: list[int] = []
    monkeypatch.setattr(db_module, "aes_decrypt", lambda _value: configuration)
    monkeypatch.setattr(
        db_module,
        "get_es_data_by_http",
        lambda _conf, _sql, *, timeout: (
            observed_timeouts.append(timeout) or [[1]],
            [{"name": "value"}],
        ),
    )

    db_module._unsafe_exec_sql_after_validation(datasource, "SELECT 1")
    db_module._unsafe_exec_sql_after_validation(
        datasource,
        "SELECT 1",
        query_timeout=7,
    )

    assert observed_timeouts == [30, 7]
