from __future__ import annotations

import importlib
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

module = importlib.import_module("sync_xiuxian_realtime_tracking_dictionary")


def _snapshot() -> dict:
    return {
        "config": {
            "field_role_mappings": [
                {"role": "snapshot_date", "table": "user", "field": "dt"},
                {"role": "event_name", "table": "event", "field": "legacy_event"},
            ],
            "sql_rules": "已有规则",
            "notes": "已有说明",
        },
        "historical_fields": [
            {
                "field_name": "uid",
                "field_comment": "用户 ID",
                "field_role": None,
                "semantic_type": "text",
                "aliases": ["UID"],
                "value_mappings": None,
                "expression": None,
                "required": False,
                "example_values": [],
                "ai_notes": None,
            },
            {
                "field_name": "event",
                "field_comment": "事件名",
                "field_role": None,
                "semantic_type": "text",
                "aliases": [],
                "value_mappings": [{"event_name": "UserRegister", "properties": []}],
                "expression": None,
                "required": False,
                "example_values": [],
                "ai_notes": None,
            },
            {
                "field_name": "personal",
                "field_comment": "事件属性 JSON",
                "field_role": None,
                "semantic_type": "text",
                "aliases": [],
                "value_mappings": None,
                "expression": None,
                "required": False,
                "example_values": [],
                "ai_notes": None,
            },
        ],
        "physical_fields": [
            {"field_name": "uid", "field_type": "varchar"},
            {"field_name": "time", "field_type": "bigint"},
            {"field_name": "personal", "field_type": "varchar"},
            {"field_name": "dt", "field_type": "bigint"},
            {"field_name": "prod", "field_type": "bigint"},
            {"field_name": "event", "field_type": "varchar"},
        ],
        "target_table": None,
        "target_fields": [],
    }


def test_build_desired_dictionary_exposes_realtime_table_and_key_roles() -> None:
    desired = module.build_desired_dictionary(_snapshot())

    assert desired["table"] == {
        "table_name": "event_realtime",
        "table_comment": "当天实时事件明细表。每行是一条尚未归档到完整历史分区的用户行为或系统事件。",
        "table_role": "realtime_event_fact",
        "aliases": ["实时事件表", "当天埋点表", "实时行为明细"],
        "ai_notes": "仅用于今天、当天、截至目前和实时分钟/小时查询；完整历史日继续使用 event。",
    }
    fields = {item["field_name"]: item for item in desired["fields"]}
    assert set(fields) == {"uid", "time", "personal", "dt", "prod", "event"}
    assert fields["uid"]["field_role"] == "subject_id"
    assert fields["event"]["field_role"] == "event_name"
    assert fields["time"]["field_role"] == "event_time"
    assert fields["dt"]["field_role"] == "partition_date"
    assert fields["prod"]["field_role"] == "product_id"
    assert fields["personal"]["semantic_type"] == "json"
    assert fields["event"]["value_mappings"] == [
        {"event_name": "UserRegister", "properties": []}
    ]


def test_build_desired_dictionary_merges_roles_and_rules_idempotently() -> None:
    desired = module.build_desired_dictionary(_snapshot())
    second = module.build_desired_dictionary(
        {
            **_snapshot(),
            "config": {
                "field_role_mappings": desired["field_role_mappings"],
                "sql_rules": desired["sql_rules"],
                "notes": desired["notes"],
            },
        }
    )

    mappings = desired["field_role_mappings"]
    assert {item["table"] for item in mappings if item["role"] == "event_name"} == {
        "event",
        "event_realtime",
    }
    assert {item["role"] for item in mappings if item["table"] == "event_realtime"} == {
        "subject_id",
        "event_name",
        "event_time",
        "partition_date",
    }
    assert {item["role"] for item in mappings if item["table"] == "user"} == {
        "snapshot_date"
    }
    assert desired["sql_rules"].count(module.REALTIME_SQL_RULE) == 1
    assert desired["notes"].count(module.REALTIME_NOTE) == 1
    assert second["field_role_mappings"] == mappings
    assert second["sql_rules"] == desired["sql_rules"]
    assert second["notes"] == desired["notes"]


class FakeBackend:
    def __init__(self, snapshots: list[dict] | None = None):
        self.snapshots = list(snapshots or [_snapshot(), _snapshot()])
        self.events: list[str] = []
        self.applied: dict | None = None

    def load_snapshot(self) -> dict:
        self.events.append("load_snapshot")
        return deepcopy(self.snapshots.pop(0))

    def write_backup(self, snapshot: dict) -> Path:
        self.events.append("write_backup")
        return Path("backup.json")

    def acquire_lock(self) -> None:
        self.events.append("acquire_lock")

    def apply_desired(self, desired: dict) -> None:
        self.events.append("apply_desired")
        self.applied = deepcopy(desired)

    def verify_desired(self, desired: dict) -> None:
        self.events.append("verify_desired")
        assert self.applied == desired

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")

    def release_lock(self) -> None:
        self.events.append("release_lock")


def test_sync_dry_run_never_writes_dictionary() -> None:
    backend = FakeBackend(snapshots=[_snapshot()])

    report = module.sync_realtime_dictionary(backend, apply=False)

    assert report["updated"] is False
    assert backend.applied is None
    assert backend.events == ["load_snapshot", "write_backup"]


def test_sync_apply_updates_and_verifies_in_one_locked_transaction() -> None:
    backend = FakeBackend()

    report = module.sync_realtime_dictionary(backend, apply=True)

    assert report["updated"] is True
    assert backend.applied is not None
    assert backend.events == [
        "load_snapshot",
        "write_backup",
        "acquire_lock",
        "load_snapshot",
        "apply_desired",
        "verify_desired",
        "commit",
        "release_lock",
    ]


def test_sync_rejects_source_change_before_write() -> None:
    changed = _snapshot()
    changed["physical_fields"].append(
        {"field_name": "new_column", "field_type": "varchar"}
    )
    backend = FakeBackend(snapshots=[_snapshot(), changed])

    with pytest.raises(module.SourceChangedError, match="发生变化"):
        module.sync_realtime_dictionary(backend, apply=True)

    assert backend.applied is None
    assert backend.events[-2:] == ["rollback", "release_lock"]


def test_psycopg_apply_bumps_tracking_epoch_with_same_cursor(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class FakeCursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, parameters):
            calls.append((str(statement), parameters))

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    backend = module.PsycopgBackend()
    backend._write_connection = FakeConnection()
    monkeypatch.setattr(module, "_snowflake_id", lambda: 123)

    backend.apply_desired(module.build_desired_dictionary(_snapshot()))

    epoch_calls = [call for call in calls if "INSERT INTO semantic_scope_epoch" in call[0]]
    assert len(epoch_calls) == 1
    assert epoch_calls[0][1] == (
        "TRACKING",
        module.TENANT_ID,
        module.DATASOURCE_ID,
        None,
    )
    assert calls[-1] == epoch_calls[0]
