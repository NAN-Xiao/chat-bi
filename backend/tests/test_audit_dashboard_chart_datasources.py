"""看板图表数据源单一来源审计工具测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import audit_dashboard_chart_datasources as audit  # noqa: E402


def _view(outer=None, inner_marker=False, inner=None):
    view = {"sql": "select 1"}
    if outer is not None:
        view["datasource"] = outer
    if inner_marker:
        view["sourceConfig"] = {"sql": {"datasource": inner, "sql": "select 1"}}
    return view


def test_classify_view_states():
    assert audit.classify_view(_view(outer=1)) == ("clean", 1, None)
    assert audit.classify_view(_view(outer=1, inner_marker=True, inner=1)) == ("duplicate", 1, 1)
    assert audit.classify_view(_view(inner_marker=True, inner=1)) == ("legacy_only", None, 1)
    assert audit.classify_view(_view(outer=1, inner_marker=True, inner=2)) == ("conflict", 1, 2)
    assert audit.classify_view(_view()) == ("missing", None, None)


def test_normalize_duplicate_canvas_only_changes_equal_duplicates():
    original = {
        "duplicate": _view(outer=1, inner_marker=True, inner=1),
        "conflict": _view(outer=1, inner_marker=True, inner=2),
        "legacy": _view(inner_marker=True, inner=3),
        "missing": _view(),
    }

    raw, changed = audit.normalize_duplicate_canvas(json.dumps(original))

    result = json.loads(raw)
    assert changed == ["duplicate"]
    assert "datasource" not in result["duplicate"]["sourceConfig"]["sql"]
    assert result["conflict"]["sourceConfig"]["sql"]["datasource"] == 2
    assert result["legacy"]["sourceConfig"]["sql"]["datasource"] == 3
    assert result["missing"] == original["missing"]


def test_restore_rejects_unrelated_backup(tmp_path):
    backup = tmp_path / "backup.json"
    backup.write_text(json.dumps({"kind": "other", "rows": []}), encoding="utf-8")

    try:
        audit.restore(backup)
    except RuntimeError as exc:
        assert str(exc) == "备份文件类型无效"
    else:
        raise AssertionError("无关备份必须被拒绝")
