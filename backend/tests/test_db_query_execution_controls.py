"""底层查询执行的行数上限与超时覆盖回归测试。"""

import json
from types import SimpleNamespace

import pytest

from apps.datasource.crud import sql_engine_executor
from apps.datasource.models.datasource import DatasourceConf
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
        self.statements: list[tuple[str, object]] = []

    def execute(self, statement, _params=None):
        sql = str(statement)
        self.statements.append((sql, _params))
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


@pytest.mark.parametrize(
    ("datasource_type", "expected_timeout_statement"),
    [
        ("pg", "SET LOCAL statement_timeout"),
        ("mysql", "SET SESSION MAX_EXECUTION_TIME"),
    ],
)
def test_sqlalchemy_branches_apply_query_timeout_to_session_and_statement(
    monkeypatch,
    datasource_type: str,
    expected_timeout_statement: str,
) -> None:
    session = FakeSqlAlchemySession(FakeResult([(1,)]))
    session_timeouts: list[int] = []

    def get_session(_datasource, *, timeout: int):
        session_timeouts.append(timeout)
        return session

    monkeypatch.setattr(db_module, "get_session", get_session)

    db_module._unsafe_exec_sql_after_validation(
        SimpleNamespace(type=datasource_type, configuration="{}"),
        "SELECT 1 AS value",
        query_timeout=7,
        require_controlled_timeout=True,
    )

    assert session_timeouts == [7]
    assert any(
        expected_timeout_statement in sql and params == {"timeout_ms": 7000}
        for sql, params in session.statements
    )


def test_sqlserver_branch_passes_query_timeout_to_pymssql_driver(monkeypatch) -> None:
    session = FakeSqlAlchemySession(FakeResult([(1,)]))
    connect_kwargs: list[dict] = []

    def connect(**kwargs):
        connect_kwargs.append(kwargs)
        return object()

    def get_session(_datasource, *, timeout: int):
        db_module.get_origin_connect(
            "sqlServer",
            DatasourceConf(
                host="db",
                port=1433,
                username="user",
                password="secret",
                database="analytics",
                timeout=timeout,
            ),
        )
        return session

    monkeypatch.setattr(db_module.pymssql, "connect", connect)
    monkeypatch.setattr(db_module, "get_session", get_session)

    db_module._unsafe_exec_sql_after_validation(
        SimpleNamespace(type="sqlServer", configuration="{}"),
        "SELECT 1 AS value",
        query_timeout=7,
        require_controlled_timeout=True,
    )

    assert connect_kwargs[0]["timeout"] == 7


class FakeDriverCursor:
    description = [("value",)]

    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, sql: str, *_args, **_kwargs) -> None:
        self.executed_sql.append(sql)

    def fetchmany(self, _size: int):
        return [(1,)]


class FakeDriverConnection:
    def __init__(self, cursor: FakeDriverCursor) -> None:
        self._cursor = cursor
        self.readonly_values: list[bool] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def cursor(self) -> FakeDriverCursor:
        return self._cursor

    def set_session(self, *, readonly: bool) -> None:
        self.readonly_values.append(readonly)


@pytest.mark.parametrize("datasource_type", ["doris", "starrocks"])
def test_mysql_driver_branches_apply_read_timeout_override(
    monkeypatch,
    datasource_type: str,
) -> None:
    cursor = FakeDriverCursor()
    connection = FakeDriverConnection(cursor)
    connect_kwargs: list[dict] = []
    configuration = json.dumps(
        {
            "host": "db",
            "port": 9030,
            "username": "user",
            "password": "secret",
            "database": "analytics",
            "timeout": 90,
        }
    )
    monkeypatch.setattr(db_module, "aes_decrypt", lambda _value: configuration)

    def connect(**kwargs):
        connect_kwargs.append(kwargs)
        return connection

    monkeypatch.setattr(db_module.pymysql, "connect", connect)

    db_module._unsafe_exec_sql_after_validation(
        SimpleNamespace(type=datasource_type, configuration="encrypted"),
        "SELECT 1 AS value",
        query_timeout=7,
        require_controlled_timeout=True,
    )

    assert connect_kwargs[0]["connect_timeout"] == 7
    assert connect_kwargs[0]["read_timeout"] == 7
    assert cursor.executed_sql[-1] == "SELECT 1 AS value"


def test_kingbase_branch_applies_statement_timeout_override(monkeypatch) -> None:
    cursor = FakeDriverCursor()
    connection = FakeDriverConnection(cursor)
    connect_kwargs: list[dict] = []
    configuration = json.dumps(
        {
            "host": "db",
            "port": 54321,
            "username": "user",
            "password": "secret",
            "database": "analytics",
            "timeout": 90,
        }
    )
    monkeypatch.setattr(db_module, "aes_decrypt", lambda _value: configuration)

    def connect(**kwargs):
        connect_kwargs.append(kwargs)
        return connection

    monkeypatch.setattr(db_module.psycopg2, "connect", connect)

    db_module._unsafe_exec_sql_after_validation(
        SimpleNamespace(type="kingbase", configuration="encrypted"),
        "SELECT 1 AS value",
        query_timeout=7,
        require_controlled_timeout=True,
    )

    assert connect_kwargs[0]["options"] == "-c statement_timeout=7000"
    assert connection.readonly_values == [True]
    assert cursor.executed_sql == ["SELECT 1 AS value"]


def test_execute_adapter_omits_new_keywords_for_legacy_callable(monkeypatch) -> None:
    calls: list[tuple[object, str, bool]] = []

    def legacy_execute(ds, sql, origin_column=False):
        calls.append((ds, sql, origin_column))
        return {"status": "success"}

    datasource = SimpleNamespace(type="pg")
    monkeypatch.setattr(
        sql_engine_executor,
        "_unsafe_exec_sql_after_validation",
        legacy_execute,
    )

    result = sql_engine_executor._execute_after_validation(
        datasource,
        "SELECT 1",
        origin_column=True,
        query_timeout=7,
        max_result_rows=None,
        require_controlled_timeout=True,
    )

    assert result == {"status": "success"}
    assert calls == [(datasource, "SELECT 1", True)]


def test_execute_adapter_passes_roi_controls_to_modern_callable(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def modern_execute(
        ds,
        sql,
        origin_column=False,
        query_timeout=None,
        max_result_rows=...,
        require_controlled_timeout=False,
    ):
        captured.update(
            ds=ds,
            sql=sql,
            origin_column=origin_column,
            query_timeout=query_timeout,
            max_result_rows=max_result_rows,
            require_controlled_timeout=require_controlled_timeout,
        )
        return {"status": "success"}

    datasource = SimpleNamespace(type="pg")
    monkeypatch.setattr(
        sql_engine_executor,
        "_unsafe_exec_sql_after_validation",
        modern_execute,
    )

    sql_engine_executor._execute_after_validation(
        datasource,
        "SELECT 1",
        origin_column=True,
        query_timeout=7,
        max_result_rows=None,
        require_controlled_timeout=True,
    )

    assert captured == {
        "ds": datasource,
        "sql": "SELECT 1",
        "origin_column": True,
        "query_timeout": 7,
        "max_result_rows": None,
        "require_controlled_timeout": True,
    }
