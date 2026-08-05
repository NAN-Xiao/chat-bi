from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import repair_flam_first_zombie_event_sources as repair_tool
from repair_flam_first_zombie_event_sources import (
    repair_summary,
    source_distribution,
    validate_target_mappings,
)


def _target_mappings(source_field: str = "personal") -> list[dict]:
    return [
        {
            "event_name": "ServerPayLog",
            "properties": [
                {
                    "property_name": f"{source_field}.money",
                    "source_field": source_field,
                    "json_path": "$.money",
                },
                {
                    "property_name": f"{source_field}.orderId",
                    "source_field": source_field,
                    "json_path": "$.orderId",
                },
                {
                    "property_name": f"{source_field}.productid",
                    "source_field": source_field,
                    "json_path": "$.productid",
                },
            ],
        }
    ]


def test_source_distribution_counts_event_properties() -> None:
    mappings = _target_mappings()
    mappings.append(
        {
            "event_name": "BattleEnd",
            "properties": [
                {
                    "property_name": "ext.result",
                    "source_field": "ext",
                    "json_path": "$.result",
                }
            ],
        }
    )

    assert source_distribution(mappings) == {"personal": 3, "ext": 1}


def test_validate_target_mappings_requires_verified_payment_sources() -> None:
    with pytest.raises(ValueError, match="ServerPayLog.money.*personal"):
        validate_target_mappings(
            _target_mappings(source_field="ext"),
            expected_total=3,
            expected_distribution={"ext": 3},
        )


def test_validate_target_mappings_accepts_expected_distribution() -> None:
    result = validate_target_mappings(
        _target_mappings(),
        expected_total=3,
        expected_distribution={"personal": 3},
    )

    assert result == {"personal": 3}


def test_repair_summary_reports_idempotent_state() -> None:
    mappings = _target_mappings()

    assert repair_summary(mappings, mappings)["changed"] is False
    assert repair_summary([], mappings)["changed"] is True


def test_apply_bumps_tracking_epoch_before_commit(monkeypatch, tmp_path: Path) -> None:
    events: list[object] = []

    class FakeCursor:
        rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, parameters):
            sql = str(statement)
            events.append(("execute", sql, parameters))
            self.rowcount = 1 if "UPDATE public.sys_tenant_tracking_config" in sql else 0

        def fetchone(self):
            return ([],)

    class FakeConnection:
        cursor_instance = FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            events.append("commit")

    monkeypatch.setattr(repair_tool, "load_repaired_mappings", lambda _path: _target_mappings())
    monkeypatch.setattr(repair_tool, "core_system_db_config", lambda: {})
    monkeypatch.setattr(repair_tool.psycopg, "connect", lambda **_kwargs: FakeConnection())
    monkeypatch.setattr(repair_tool, "_write_backup", lambda *_args: tmp_path / "backup.json")

    result = repair_tool.repair_event_sources(Path("unused.xlsx"), apply=True)

    epoch_calls = [
        item for item in events
        if isinstance(item, tuple) and "INSERT INTO semantic_scope_epoch" in item[1]
    ]
    assert result["applied"] is True
    assert len(epoch_calls) == 1
    assert epoch_calls[0][2] == (
        "TRACKING",
        repair_tool.TENANT_ID,
        repair_tool.DATASOURCE_ID,
        None,
    )
    assert events.index(epoch_calls[0]) < events.index("commit")
