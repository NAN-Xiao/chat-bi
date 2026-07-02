from types import SimpleNamespace

import pytest

from apps.db import db as db_module
from apps.db.db import (
    _apply_dbapi_read_only_guard,
    _apply_sqlalchemy_read_only_guard,
    _limited_fetchmany,
    check_sql_read,
    get_dangerous_functions,
    get_sqlglot_dialect,
)


def _ds(ds_type: str):
    return SimpleNamespace(type=ds_type)


def test_pg_dangerous_functions_use_repo_datasource_key():
    dangerous = {name.casefold() for name in get_dangerous_functions("pg")}

    assert "pg_read_file" in dangerous
    assert "lo_import" in dangerous


@pytest.mark.parametrize("ds_type", ["pg", "postgresql", "kingbase", "redshift"])
def test_postgres_compatible_file_functions_are_rejected(ds_type):
    is_safe, reason = check_sql_read(
        "SELECT pg_read_file('/etc/passwd'), t.* FROM public.fact_payments t LIMIT 1",
        _ds(ds_type),
    )

    assert is_safe is False
    assert "dangerous function" in reason


@pytest.mark.parametrize("function_name", ["pg_read_binary_file", "pg_ls_dir", "pg_stat_file", "lo_import"])
def test_postgres_compatible_file_function_variants_are_rejected(function_name):
    is_safe, reason = check_sql_read(
        f"SELECT {function_name}('/etc/passwd'), t.* FROM public.fact_payments t LIMIT 1",
        _ds("pg"),
    )

    assert is_safe is False
    assert "dangerous function" in reason


def test_quoted_postgres_file_function_is_rejected():
    is_safe, reason = check_sql_read(
        'SELECT "pg_read_file"(\'/etc/passwd\'), t.* FROM public.fact_payments t LIMIT 1',
        _ds("pg"),
    )

    assert is_safe is False
    assert "dangerous function" in reason


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM file('/etc/passwd', 'LineAsString', 'line String')",
        "SELECT * FROM url('http://127.0.0.1:8000/', 'CSV', 'x String')",
        "SELECT * FROM s3('https://bucket.example/data.csv', 'CSV', 'x String')",
        "SELECT * FROM executable('cat /etc/passwd', 'TabSeparated', 'x String')",
        "SELECT * FROM postgresql('host:5432', 'db', 'table', 'user', 'password')",
    ],
)
def test_clickhouse_external_access_functions_are_rejected(sql):
    is_safe, reason = check_sql_read(sql, _ds("ck"))

    assert is_safe is False
    assert "dangerous function" in reason


def test_normal_select_still_passes_for_pg():
    is_safe, reason = check_sql_read("SELECT id, amount FROM public.fact_payments LIMIT 1", _ds("pg"))

    assert is_safe is True
    assert reason == ""


def test_multi_statement_sql_is_rejected():
    is_safe, reason = check_sql_read(
        "SELECT id FROM public.fact_payments LIMIT 1; SET ROLE admin",
        _ds("pg"),
    )

    assert is_safe is False
    assert "exactly one statement" in reason


def test_sqlalchemy_read_only_guard_uses_datasource_type_aliases():
    class FakeSession:
        def __init__(self):
            self.sql = []

        def execute(self, statement, params=None):
            self.sql.append(str(statement))

    session = FakeSession()

    _apply_sqlalchemy_read_only_guard(session, "postgresql")
    _apply_sqlalchemy_read_only_guard(session, "ck")

    assert session.sql == ["SET TRANSACTION READ ONLY", "SET readonly = 1"]


def test_dbapi_read_only_guard_sets_kingbase_connection_readonly():
    class FakeConnection:
        def __init__(self):
            self.readonly = None

        def set_session(self, *, readonly):
            self.readonly = readonly

    conn = FakeConnection()

    _apply_dbapi_read_only_guard(conn, object(), "kingbase")

    assert conn.readonly is True


def test_limited_fetch_uses_fetchmany_instead_of_fetchall(monkeypatch):
    monkeypatch.setattr(db_module.settings, "SHUZHI_QUERY_RESULT_MAX_ROWS", 5)

    class FakeCursor:
        def __init__(self):
            self.fetchmany_size = None
            self.fetchall_called = False

        def fetchmany(self, size):
            self.fetchmany_size = size
            return [(1,)]

        def fetchall(self):
            self.fetchall_called = True
            return []

    cursor = FakeCursor()

    assert _limited_fetchmany(cursor) == [(1,)]
    assert cursor.fetchmany_size == 5
    assert cursor.fetchall_called is False


def test_safety_dialect_maps_repo_datasource_types():
    assert get_sqlglot_dialect("pg") == "postgres"
    assert get_sqlglot_dialect("postgresql") == "postgres"
    assert get_sqlglot_dialect("kingbase") == "postgres"
    assert get_sqlglot_dialect("redshift") == "redshift"
    assert get_sqlglot_dialect("ck") == "clickhouse"
