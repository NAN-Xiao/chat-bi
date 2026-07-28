from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import migrate_roi_dashboard_date_expression as migration


def _legacy_sql() -> str:
    return "\n".join(
        f"WHERE {alias}.dt >= {migration.LEGACY_START}\n"
        f"AND {alias}.dt <= {migration.LEGACY_END}"
        for alias in ("r", "r", "v", "s")
    )


def _view(sql: str | None = None) -> dict:
    return {
        "sql": sql or _legacy_sql(),
        "chart": {"type": "table"},
        "datasource": 7,
        "sourceConfig": {"sql": {"keep": "value"}},
        "pivot": {"enabled": False, "keep": "value"},
    }


def _raw_canvas(canvas: dict) -> str:
    return json.dumps(canvas, ensure_ascii=False, separators=(",", ":"))


def test_migrate_sql_replaces_exactly_four_pairs():
    migrated = migration.migrate_sql(_legacy_sql())

    assert migrated.count(migration.START_TOKEN) == 4
    assert migrated.count(migration.END_TOKEN) == 4
    assert "CURDATE()" not in migrated


def test_migrate_sql_rejects_changed_occurrence_count():
    with pytest.raises(ValueError, match="固定日期条件数量不是 4 对"):
        migration.migrate_sql(
            f"WHERE r.dt >= {migration.LEGACY_START} AND r.dt <= {migration.LEGACY_END}"
        )


def test_migrate_view_preserves_unrelated_config():
    original = _view()

    migrated = migration.migrate_view(original)

    assert migrated is not original
    assert migrated["chart"] == original["chart"]
    assert migrated["sourceConfig"]["sql"]["keep"] == "value"
    assert migrated["pivot"]["keep"] == "value"
    assert migrated["pivot"]["enabled"] is False
    assert migrated["pivot"]["date_expression"] == migration.DEFAULT_EXPRESSION
    assert migrated["sourceConfig"]["sql"]["builder"]["dateExpressionPickerEnabled"] is True


def test_validate_baseline_rejects_unknown_dashboard_hash(monkeypatch):
    canvas = {"chart": _view()}
    monkeypatch.setattr(migration, "EXPECTED_CANVAS_SHA256", "expected")
    monkeypatch.setattr(migration, "EXPECTED", {})

    with pytest.raises(RuntimeError, match="CAS 哈希不匹配"):
        migration.validate_baseline("bad", canvas)


def test_validate_baseline_rejects_unknown_chart_hash(monkeypatch):
    canvas = {"chart": _view()}
    raw = _raw_canvas(canvas)
    monkeypatch.setattr(migration, "EXPECTED_CANVAS_SHA256", migration.sha256_text(raw))
    monkeypatch.setattr(migration, "EXPECTED", {"chart": ("bad", "bad")})
    monkeypatch.setattr(migration, "EXPECTED_TITLES", {"chart": "图表"})

    with pytest.raises(RuntimeError, match="CAS 哈希不匹配"):
        migration.validate_baseline(raw, canvas)


def test_validate_baseline_rejects_changed_chart_identity(monkeypatch):
    view = _view()
    view["chart"] = {"id": "chart", "title": "错误标题"}
    canvas = {"chart": view}
    raw = _raw_canvas(canvas)
    monkeypatch.setattr(migration, "EXPECTED_CANVAS_SHA256", migration.sha256_text(raw))
    monkeypatch.setattr(
        migration,
        "EXPECTED",
        {"chart": (migration.sha256_text(view["sql"]), migration.config_fingerprint(view))},
    )
    monkeypatch.setattr(migration, "EXPECTED_TITLES", {"chart": "正确标题"})

    with pytest.raises(RuntimeError, match="目标图表身份不一致"):
        migration.validate_baseline(raw, canvas)


def test_migrate_canvas_changes_only_target_views(monkeypatch):
    canvas = {"target": _view(), "untouched": {"sql": "select 1", "chart": {"type": "bar"}}}
    original = copy.deepcopy(canvas)
    monkeypatch.setattr(migration, "EXPECTED", {"target": ("sql", "config")})

    migrated, unchanged_hashes = migration.migrate_canvas(canvas)

    assert canvas == original
    assert migrated["untouched"] == original["untouched"]
    assert unchanged_hashes == {
        "untouched": hashlib.sha256(
            json.dumps(original["untouched"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    }


def test_verify_migrated_canvas_checks_tokens_config_and_non_targets(monkeypatch):
    original = {"target": _view(), "untouched": {"sql": "select 1"}}
    monkeypatch.setattr(migration, "EXPECTED", {"target": ("sql", "config")})
    migrated, unchanged_hashes = migration.migrate_canvas(original)

    result = migration.verify_migrated_canvas(migrated, unchanged_hashes=unchanged_hashes)

    assert result["target"]["start_tokens"] == 4
    assert result["target"]["end_tokens"] == 4
    assert result["target"]["expression"] == migration.DEFAULT_EXPRESSION


def test_verify_migrated_canvas_rejects_builder_pivot_drift(monkeypatch):
    original = {"target": _view()}
    monkeypatch.setattr(migration, "EXPECTED", {"target": ("sql", "config")})
    migrated, _ = migration.migrate_canvas(original)
    migrated["target"]["pivot"]["date_expression"]["preset"] = "today"

    with pytest.raises(RuntimeError, match="日期表达式配置不一致"):
        migration.verify_migrated_canvas(migrated)


def test_restore_rejects_backup_outside_locked_baseline(tmp_path):
    old_raw = "{}"
    backup = tmp_path / "backup.json"
    backup.write_text(
        json.dumps(
            {
                "dashboard_id": migration.DASHBOARD_ID,
                "tenant_id": migration.TENANT_ID,
                "create_by": migration.CREATE_BY,
                "old_canvas_sha256": migration.sha256_text(old_raw),
                "new_canvas_sha256": "new",
                "row": {"canvas_view_info": old_raw},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="备份内容哈希不匹配"):
        migration.restore_dashboard(backup)
