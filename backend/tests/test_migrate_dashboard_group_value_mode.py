from copy import deepcopy
from pathlib import Path
import sys


TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import migrate_dashboard_group_value_mode as migration  # noqa: E402


def grouped_view(pivot: dict) -> dict:
    return {
        "chart": {"type": "area", "xAxis": [{"value": "dt"}]},
        "sql": "SELECT dt, channel, amount FROM report",
        "pivot": {
            "enabled": True,
            "group_enabled": True,
            "group_field": "channel",
            **pivot,
        },
    }


def test_migrate_canvas_only_changes_group_value_selection() -> None:
    original = {
        "chart-1": grouped_view({"group_values": ["Organic", "Facebook"]}),
        "chart-2": {"chart": {"type": "table"}, "pivot": {"enabled": False}},
    }
    expected_unchanged = deepcopy(original["chart-1"])
    expected_unchanged["pivot"].pop("group_values")

    migrated, changes = migration.migrate_canvas(original)

    assert changes == [
        {
            "view_id": "chart-1",
            "chart_type": "area",
            "group_field": "channel",
            "old_mode": None,
            "old_group_values": ["Organic", "Facebook"],
        }
    ]
    assert migrated["chart-1"]["pivot"]["group_value_mode"] == "all"
    assert migrated["chart-1"]["pivot"]["group_values"] == []
    actual_unchanged = deepcopy(migrated["chart-1"])
    actual_unchanged["pivot"].pop("group_value_mode")
    actual_unchanged["pivot"].pop("group_values")
    assert actual_unchanged == expected_unchanged
    assert migrated["chart-2"] == original["chart-2"]
    assert original["chart-1"]["pivot"]["group_values"] == ["Organic", "Facebook"]


def test_migrate_canvas_is_idempotent() -> None:
    original = {"chart-1": grouped_view({"group_value_mode": "all", "group_values": []})}

    migrated, changes = migration.migrate_canvas(original)

    assert migrated == original
    assert changes == []


def test_migrate_canvas_converts_explicit_custom_to_all() -> None:
    original = {
        "chart-1": grouped_view(
            {"group_value_mode": "custom", "group_values": ["Organic"]}
        )
    }

    migrated, changes = migration.migrate_canvas(original)

    assert len(changes) == 1
    assert migrated["chart-1"]["pivot"]["group_value_mode"] == "all"
    assert migrated["chart-1"]["pivot"]["group_values"] == []


def test_migrate_canvas_skips_disabled_or_ungrouped_pivots() -> None:
    original = {
        "disabled": grouped_view({"group_enabled": False, "group_values": ["Organic"]}),
        "no-field": grouped_view({"group_field": "", "group_values": ["Organic"]}),
    }

    migrated, changes = migration.migrate_canvas(original)

    assert migrated == original
    assert changes == []
