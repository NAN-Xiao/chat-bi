import copy
import hashlib
import json

import pytest
import tools.xiuxian_serverpaylog_core_dashboard_repair as repair_module

from tools.xiuxian_serverpaylog_core_dashboard_repair import (
    DATA_SKILL_SOURCE_SHA256,
    REPAIRS,
    SourcePromptChangedError,
    SourceSqlChangedError,
    ViewRepair,
    apply_repairs_to_data_skill_prompt,
    apply_repairs_to_canvas,
)


def _view(sql: str) -> dict:
    return {
        "sql": sql,
        "sourceConfig": {
            "sql": {
                "sql": sql,
            }
        },
    }


def test_apply_repairs_updates_only_targets_and_keeps_sql_copies_in_sync():
    repairs = {
        "view-a": ViewRepair(
            view_id="view-a",
            source_sha256=hashlib.sha256(b"legacy-a").hexdigest(),
            sql="SELECT 'ServerPayLog' AS source, '$.money' AS amount",
        ),
        "view-b": ViewRepair(
            view_id="view-b",
            source_sha256=hashlib.sha256(b"legacy-b").hexdigest(),
            sql="SELECT 'UserRegister' AS cohort, '$.pay1' AS amount",
        ),
    }
    canvas = {
        "view-a": _view("legacy-a"),
        "view-b": _view("legacy-b"),
        "untouched": _view("SELECT 'PayBuyRet' AS process_event"),
    }

    repaired = apply_repairs_to_canvas(canvas, repairs=repairs)

    assert repaired is not canvas
    for view_id, repair in repairs.items():
        assert repaired[view_id]["sql"] == repair.sql
        assert repaired[view_id]["sourceConfig"]["sql"]["sql"] == repair.sql
    assert repaired["untouched"] == canvas["untouched"]


def test_apply_repairs_rejects_changed_source_sql():
    repairs = {
        "view-a": ViewRepair(
            view_id="view-a",
            source_sha256=hashlib.sha256(b"expected-source").hexdigest(),
            sql="SELECT 'ServerPayLog'",
        )
    }

    with pytest.raises(SourceSqlChangedError, match="view-a"):
        apply_repairs_to_canvas({"view-a": _view("unexpected-source")}, repairs=repairs)


def test_production_repairs_use_authoritative_transaction_sources():
    revenue_sql = REPAIRS["22d89d4a69224e53994d21fb44b376aa"].sql
    new_user_sql = REPAIRS["2192510609759838208"].sql

    assert "ServerPayLog" in revenue_sql
    assert "$.money" in revenue_sql
    assert "UserActive" in revenue_sql
    assert "PayBuyRet" not in revenue_sql
    assert "ed_money" not in revenue_sql
    assert "paytotal" not in revenue_sql

    assert "UserRegister" in new_user_sql
    assert "$.pay1" in new_user_sql
    assert "PayBuyRet" not in new_user_sql
    assert "ed_money" not in new_user_sql
    assert "paytotal" not in new_user_sql


def test_apply_repairs_does_not_mutate_input_canvas():
    repairs = {
        "view-a": ViewRepair(
            view_id="view-a",
            source_sha256=hashlib.sha256(b"legacy-a").hexdigest(),
            sql="SELECT 'ServerPayLog' AS source, '$.money' AS amount",
        )
    }
    canvas = {
        "view-a": _view("legacy-a"),
    }
    original = copy.deepcopy(canvas)

    apply_repairs_to_canvas(canvas, repairs=repairs)

    assert canvas == original


def test_apply_repairs_to_data_skill_prompt_replaces_only_marked_sql_blocks():
    legacy_prompt = "\n\n".join(
        [
            "保留的 Skill 规则：PayBuyRet 不能作为真实收入来源。",
            "<!-- dashboard-sql:view-a -->\n```sql\nlegacy-a\n```",
            "<!-- dashboard-sql:view-b -->\n```sql\nlegacy-b\n```",
        ]
    )
    repairs = {
        "view-a": ViewRepair(
            view_id="view-a",
            source_sha256="unused",
            sql="SELECT 'ServerPayLog' AS source, '$.money' AS amount",
        ),
        "view-b": ViewRepair(
            view_id="view-b",
            source_sha256="unused",
            sql="SELECT 'UserRegister' AS cohort, '$.pay1' AS amount",
        ),
    }

    repaired = apply_repairs_to_data_skill_prompt(
        legacy_prompt,
        repairs=repairs,
        expected_source_sha256=hashlib.sha256(legacy_prompt.encode()).hexdigest(),
    )

    assert "PayBuyRet 不能作为真实收入来源" in repaired
    assert "<!-- dashboard-sql:view-a -->\n```sql\n" + repairs["view-a"].sql in repaired
    assert "<!-- dashboard-sql:view-b -->\n```sql\n" + repairs["view-b"].sql in repaired
    assert "legacy-a" not in repaired
    assert "legacy-b" not in repaired


def test_apply_repairs_to_data_skill_prompt_rejects_changed_source():
    with pytest.raises(SourcePromptChangedError):
        apply_repairs_to_data_skill_prompt("unexpected", repairs={})


def test_repair_data_skill_update_compares_original_prompt():
    source_prompt = "<!-- dashboard-sql:view-a -->\n```sql\nlegacy-a\n```"
    repair = ViewRepair(
        view_id="view-a",
        source_sha256="unused",
        sql="SELECT 'ServerPayLog' AS source, '$.money' AS amount",
    )
    connection = _FakeConnection((257, source_prompt))

    report = repair_module.repair_data_skill(
        connection,
        apply=True,
        repairs={"view-a": repair},
        source_sha256=hashlib.sha256(source_prompt.encode()).hexdigest(),
    )

    update_sql, update_params = connection.cursor_instance.calls[1]
    assert report.skill_id == 257
    assert report.updated is True
    assert connection.committed is True
    assert "datasource_ids = %s::jsonb" in update_sql
    assert update_params[-1] == source_prompt


class _FakeCursor:
    def __init__(self, row):
        self.row = row
        self.calls = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchone(self):
        return self.row


class _FakeConnection:
    def __init__(self, row):
        self.cursor_instance = _FakeCursor(row)
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True


def _database_fixture(monkeypatch):
    repairs = {
        "view-a": ViewRepair(
            view_id="view-a",
            source_sha256=hashlib.sha256(b"legacy-a").hexdigest(),
            sql="SELECT 'ServerPayLog' AS source, '$.money' AS amount",
        ),
    }
    monkeypatch.setattr(repair_module, "REPAIRS", repairs)
    canvas = {"view-a": _view("legacy-a")}
    return _FakeConnection(("dashboard-1", json.dumps(canvas, separators=(",", ":"))))


def test_repair_dashboard_dry_run_does_not_write(monkeypatch):
    connection = _database_fixture(monkeypatch)

    report = repair_module.repair_dashboard(connection, apply=False)

    assert report.updated is False
    assert len(connection.cursor_instance.calls) == 1
    assert connection.committed is False


def test_repair_dashboard_update_compares_original_canvas(monkeypatch):
    connection = _database_fixture(monkeypatch)

    report = repair_module.repair_dashboard(connection, apply=True)

    update_sql, update_params = connection.cursor_instance.calls[1]
    assert report.updated is True
    assert connection.committed is True
    assert "canvas_view_info = %s" in update_sql
    assert update_params[-1] == connection.cursor_instance.row[1]
