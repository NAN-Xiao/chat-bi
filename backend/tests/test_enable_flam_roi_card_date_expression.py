from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import enable_flam_roi_card_date_expression as migration


def _view() -> dict:
    return {
        "sql": "SELECT * FROM t WHERE dt >= {{dashboard_start_yyyymmdd}} "
        "AND dt <= {{dashboard_end_yyyymmdd}}",
        "sourceConfig": {
            "sql": {
                "sql": "legacy editor SQL",
                "builder": {"timeRange": "30d", "keep": "value"},
            }
        },
        "pivot": {
            "enabled": False,
            "time_field": "日期",
            "date_parameter_type": "yyyymmdd_number",
            "range_enabled": True,
            "keep": "value",
        },
        "chart": {"title": "ROI总览"},
    }


def test_enable_view_only_adds_date_expression_configuration():
    original = _view()

    migrated = migration.enable_view(original)

    assert original["sourceConfig"]["sql"]["builder"]["timeRange"] == "30d"
    assert migrated["sql"] == original["sql"]
    assert migrated["sourceConfig"]["sql"]["sql"] == "legacy editor SQL"
    assert migrated["sourceConfig"]["sql"]["builder"]["keep"] == "value"
    assert migrated["sourceConfig"]["sql"]["builder"] == {
        "timeRange": "expression",
        "keep": "value",
        "dateExpressionPickerEnabled": True,
        "timeExpression": migration.DEFAULT_EXPRESSION,
    }
    assert migrated["pivot"] == {
        **original["pivot"],
        "date_expression": migration.DEFAULT_EXPRESSION,
    }


def test_migrate_canvas_preserves_each_target_sql(monkeypatch):
    canvas = {"target": _view()}
    original = copy.deepcopy(canvas)
    monkeypatch.setattr(
        migration,
        "EXPECTED",
        {"target": (migration.sha256_text(canvas["target"]["sql"]), "ROI总览")},
    )

    migrated = migration.migrate_canvas(canvas)

    assert canvas == original
    assert migrated["target"]["sql"] == original["target"]["sql"]
    builder = migrated["target"]["sourceConfig"]["sql"]["builder"]
    assert builder["dateExpressionPickerEnabled"] is True


def test_validate_baseline_rejects_changed_canvas_hash(monkeypatch):
    canvas = {"target": _view()}
    monkeypatch.setattr(migration, "EXPECTED_CANVAS_SHA256", "expected")
    monkeypatch.setattr(migration, "EXPECTED", {})

    with pytest.raises(RuntimeError, match="CAS 哈希不匹配"):
        migration.validate_baseline(json.dumps(canvas), canvas)


def test_verify_migrated_canvas_rejects_sql_changes(monkeypatch):
    original = _view()
    sql_hash = migration.sha256_text(original["sql"])
    monkeypatch.setattr(migration, "EXPECTED", {"target": (sql_hash, "ROI总览")})
    migrated = migration.migrate_canvas({"target": original})
    migrated["target"]["sql"] += " -- changed"

    with pytest.raises(RuntimeError, match="SQL 已发生变化"):
        migration.verify_migrated_canvas(migrated)
