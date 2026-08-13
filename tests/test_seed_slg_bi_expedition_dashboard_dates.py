from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
MODULE_PATH = TOOLS_DIR / "seed_slg_bi_expedition_dashboard.py"


def load_module():
    sys.path.insert(0, str(TOOLS_DIR))
    spec = importlib.util.spec_from_file_location("seed_slg_bi_expedition_dashboard", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dashboard_observation_and_generation_end_at_latest_business_day() -> None:
    module = load_module()

    assert module.DATA_START_DAY == date(2026, 6, 29)
    assert module.DATA_END_DAY == date(2026, 8, 4)
    assert module.OBSERVED_DAY == module.DATA_END_DAY


def test_troop_pivot_uses_dynamic_recent_seven_day_columns() -> None:
    module = load_module()

    expected_columns = (
        "2026-07-29(三)",
        "2026-07-30(四)",
        "2026-07-31(五)",
        "2026-08-01(六)",
        "2026-08-02(日)",
        "2026-08-03(一)",
        "2026-08-04(二)",
    )
    for column in expected_columns:
        assert f'AS "{column}"' in module.TROOP_PIVOT_TABLE_SQL

    assert "2026-06-20" not in module.TROOP_PIVOT_TABLE_SQL
    assert "2026-06-26" not in module.TROOP_PIVOT_TABLE_SQL


def test_shifted_generation_profile_preserves_existing_daily_targets() -> None:
    module = load_module()

    assert module.DATA_PROFILE_OBSERVED_DAY == date(2026, 7, 29)
    assert module.FIXED_DAILY_TARGETS[date(2026, 7, 20)]["count"] == 10452
    assert module.FIXED_DAILY_TARGETS[date(2026, 7, 29)]["count"] == 11936


def test_datasource_connection_comes_from_workspace_configuration() -> None:
    module = load_module()

    result = module.psycopg2_config_from_datasource_settings(
        {
            "host": "db.example.internal",
            "port": 5544,
            "database": "configured_slg",
            "username": "configured_user",
            "password": "configured_password",
        }
    )

    assert result == {
        "host": "db.example.internal",
        "port": 5544,
        "dbname": "configured_slg",
        "user": "configured_user",
        "password": "configured_password",
    }


def test_local_secret_key_is_available_before_datasource_decryption(monkeypatch) -> None:
    module = load_module()
    monkeypatch.delenv("SECRET_KEY", raising=False)

    module.ensure_backend_decryption_env()

    assert os.environ["SECRET_KEY"] == module.DEFAULT_LOCAL_SECRET_KEY


class FakeCursor:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.queries = []
        self.current = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params):
        self.queries.append((query, params))
        self.current = next(self.rows)

    def fetchone(self):
        return self.current


class FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = FakeCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self, **_kwargs):
        return self.cursor_instance


def test_dashboard_context_uses_current_workspace_datasource_binding() -> None:
    module = load_module()
    connection = FakeConnection(
        [
            {"tenant_id": 7473600346187632640},
            {"id": 1},
            {"user_id": 7471612174524223488},
        ]
    )

    result = module.resolve_dashboard_context(connection)

    assert result == (7473600346187632640, 1, "7471612174524223488")
    executed_sql = "\n".join(query for query, _params in connection.cursor_instance.queries)
    assert "core_datasource_tenant_binding" in executed_sql
    assert "core_dashboard" in executed_sql


def test_dashboard_context_rejects_missing_workspace_binding() -> None:
    module = load_module()
    connection = FakeConnection([{"tenant_id": 7473600346187632640}, None])

    try:
        module.resolve_dashboard_context(connection)
    except RuntimeError as exc:
        assert "no current SLG BI Mock datasource binding" in str(exc)
    else:
        raise AssertionError("Expected missing workspace binding to fail")


def test_dashboard_context_rejects_missing_canonical_dashboard() -> None:
    module = load_module()
    connection = FakeConnection([None])

    try:
        module.resolve_dashboard_context(connection)
    except RuntimeError as exc:
        assert module.DASHBOARD_ID in str(exc)
    else:
        raise AssertionError("Expected missing canonical dashboard to fail")


def test_existing_dashboard_update_preserves_original_update_by(monkeypatch, tmp_path) -> None:
    module = load_module()
    monkeypatch.setattr(module, "BACKUP_DIR", tmp_path)
    connection = FakeConnection(
        [
            {
                "id": module.DASHBOARD_ID,
                "component_data": "[]",
                "canvas_view_info": "{}",
                "update_by": "original-user",
            },
            None,
        ]
    )
    connection.cursor_instance.rowcount = 1

    module.upsert_dashboard(connection, 10, 20, "new-user", [], {})

    update_sql, update_params = connection.cursor_instance.queries[1]
    assert "update_by" not in update_sql.casefold()
    assert "new-user" not in update_params
