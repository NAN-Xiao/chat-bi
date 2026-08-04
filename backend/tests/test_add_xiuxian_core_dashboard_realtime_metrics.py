"""验证修仙核心看板实时指标卡的 SQL 与布局契约。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import add_xiuxian_core_dashboard_realtime_metrics as repair  # noqa: E402


YESTERDAY_EXPRESSION = {"version": 1, "mode": "preset", "preset": "yesterday"}


def test_metric_specs_use_authoritative_event_tables() -> None:
    specs = {spec.title: spec for spec in repair.METRIC_SPECS}

    assert list(specs) == ["活跃用户", "新增用户", "充值人数", "充值总额"]
    for spec in specs.values():
        assert "prod = 110000047" in spec.sql
        assert "{{dashboard_start_yyyymmdd}}" in spec.sql
        assert "{{dashboard_end_yyyymmdd}}" in spec.sql
        assert "`日期`" in spec.sql

    assert "FROM event\n" in specs["活跃用户"].sql
    assert "event_realtime" not in specs["活跃用户"].sql
    assert "event = 'UserActive'" in specs["活跃用户"].sql
    assert "COUNT(DISTINCT uid)" in specs["活跃用户"].sql
    assert "FROM event\n" in specs["新增用户"].sql
    assert "event_realtime" not in specs["新增用户"].sql
    assert "event = 'UserRegister'" in specs["新增用户"].sql
    assert "COUNT(DISTINCT uid)" in specs["新增用户"].sql
    assert "FROM event\n" in specs["充值人数"].sql
    assert "event_realtime" not in specs["充值人数"].sql
    assert "event = 'ServerPayLog'" in specs["充值人数"].sql
    assert "COUNT(DISTINCT uid)" in specs["充值人数"].sql
    assert "FROM event\n" in specs["充值总额"].sql
    assert "event_realtime" not in specs["充值总额"].sql
    assert "event = 'ServerPayLog'" in specs["充值总额"].sql
    assert "$.money" in specs["充值总额"].sql
    assert "/ 10000" in specs["充值总额"].sql


def test_rewrite_skill_prompt_replaces_only_the_target_dashboard_sql() -> None:
    sync_spec = next(item for item in repair.SKILL_SYNC_SPECS if item.skill_id == 270)
    prompt = """<!-- data-skill-source:xiuxian:dashboard:new-users-platform -->
# 修仙新增用户总量与系统归因

<!-- dashboard-sql:existing-view -->
```sql
SELECT * FROM event
```

<!-- dashboard-sql:2ca07023c33d514eaa07977425ee7f53 -->
```sql
SELECT COUNT(DISTINCT uid) FROM event_realtime
```
"""

    rewritten = repair.rewrite_skill_prompt(prompt, sync_spec)

    assert "SELECT * FROM event" in rewritten
    assert sync_spec.metric.sql in rewritten
    assert "event_realtime" not in rewritten
    assert rewritten.count(f"<!-- dashboard-sql:{sync_spec.metric.view_id} -->") == 1


def test_rewrite_skill_prompt_rejects_duplicate_target_blocks() -> None:
    sync_spec = next(item for item in repair.SKILL_SYNC_SPECS if item.skill_id == 272)
    block = (
        f"<!-- dashboard-sql:{sync_spec.metric.view_id} -->\n"
        "```sql\nSELECT 1 FROM event_realtime\n```"
    )

    try:
        repair.rewrite_skill_prompt(f"{sync_spec.marker}\n{block}\n{block}", sync_spec)
    except ValueError as exc:
        assert "恰好一个" in str(exc)
    else:
        raise AssertionError("重复目标 SQL 块必须被拒绝")


def test_apply_entrypoint_syncs_skill_prompts_after_dashboard(monkeypatch, tmp_path) -> None:
    events = []
    rows = {
        spec.view_id: {"日期": "2026-07-22", spec.field: 0}
        for spec in repair.METRIC_SPECS
    }
    backup_dir = tmp_path / "backup"

    monkeypatch.setattr(repair, "query_metric_rows", lambda: rows)
    monkeypatch.setattr(
        repair,
        "apply_dashboard",
        lambda metric_rows: events.append(("dashboard", metric_rows)) or backup_dir,
    )
    monkeypatch.setattr(
        repair,
        "apply_skill_prompts",
        lambda path: events.append(("skills", path)) or (270, 272),
        raising=False,
    )

    assert repair.main(["--apply"]) == 0
    assert events == [("dashboard", rows), ("skills", backup_dir)]


def test_apply_entrypoint_can_update_dashboard_layout_without_touching_skills(
    monkeypatch, tmp_path
) -> None:
    events = []
    rows = {
        spec.view_id: {"日期": "2026-08-02", spec.field: 0}
        for spec in repair.METRIC_SPECS
    }
    backup_dir = tmp_path / "backup"

    monkeypatch.setattr(repair, "query_metric_rows", lambda: rows)
    monkeypatch.setattr(
        repair,
        "apply_dashboard",
        lambda metric_rows: events.append(("dashboard", metric_rows)) or backup_dir,
    )
    monkeypatch.setattr(
        repair,
        "apply_skill_prompts",
        lambda path: events.append(("skills", path)) or (270, 272),
    )

    assert repair.main(["--apply", "--skip-skill-sync"]) == 0
    assert events == [("dashboard", rows)]


def test_rewrite_dashboard_adds_four_top_metrics_and_shifts_existing_components() -> None:
    components = [
        {"id": "old-a", "x": 1, "y": 1, "sizeX": 36, "sizeY": 13},
        {"id": "old-b", "x": 37, "y": 14, "sizeX": 36, "sizeY": 13},
    ]
    canvas = {"old-a": {"id": "old-a"}, "old-b": {"id": "old-b"}}
    rows = {
        spec.view_id: {"日期": "2026-07-20", spec.field: index}
        for index, spec in enumerate(repair.METRIC_SPECS, start=1)
    }

    new_components, new_canvas = repair.rewrite_dashboard(components, canvas, rows)

    old_components = {item["id"]: item for item in new_components if item["id"].startswith("old-")}
    assert old_components["old-a"]["y"] == 11
    assert old_components["old-b"]["y"] == 24

    metric_components = [
        item for item in new_components if item["id"] in repair.METRIC_VIEW_IDS
    ]
    assert [(item["x"], item["y"], item["sizeX"], item["sizeY"]) for item in metric_components] == [
        (1, 1, 18, 10),
        (19, 1, 18, 10),
        (37, 1, 18, 10),
        (55, 1, 18, 10),
    ]
    assert set(canvas).issubset(new_canvas)
    for spec in repair.METRIC_SPECS:
        view = new_canvas[spec.view_id]
        assert view["chart"]["type"] == "metric"
        assert view["chart"]["title"] == spec.title
        assert view["chart"]["xAxis"] == [{"value": "日期", "type": "other-info"}]
        assert view["chart"]["yAxis"] == [{"value": spec.field, "type": "y"}]
        assert view["data"]["data"] == [rows[spec.view_id]]
        assert view["sourceConfig"]["sql"]["sql"] == spec.sql
        builder = view["sourceConfig"]["sql"]["builder"]
        assert builder["metricDateExpressionEnabled"] is True
        assert builder["dateExpressionPickerEnabled"] is True
        assert builder["timeField"] == "event.dt"
        assert builder["timeRange"] == "expression"
        assert builder["timeExpression"] == YESTERDAY_EXPRESSION
        assert view["configVersion"] == 2
        assert view["dateFilter"] == {
            "enabled": True,
            "parameterType": "yyyymmdd_number",
            "expression": YESTERDAY_EXPRESSION,
        }
        assert view["pivot"]["date_expression"] == YESTERDAY_EXPRESSION
        assert "{{dashboard_start_yyyymmdd}}" in view["sql"]
        assert "{{dashboard_end_yyyymmdd}}" in view["sql"]


def test_rewrite_dashboard_expands_existing_metrics_and_shifts_following_components_once() -> None:
    rows = {
        spec.view_id: {"日期": "2026-08-02", spec.field: index}
        for index, spec in enumerate(repair.METRIC_SPECS, start=1)
    }
    components = [repair._metric_component(spec) for spec in repair.METRIC_SPECS]
    for component in components:
        component["sizeY"] = 8
    components.append({"id": "old-a", "x": 1, "y": 9, "sizeX": 36, "sizeY": 13})
    canvas = {
        **{
            spec.view_id: repair._metric_view(spec, rows[spec.view_id], 0)
            for spec in repair.METRIC_SPECS
        },
        "old-a": {"id": "old-a"},
    }

    expanded_components, expanded_canvas = repair.rewrite_dashboard(components, canvas, rows)
    expanded_by_id = {item["id"]: item for item in expanded_components}

    assert expanded_by_id["old-a"]["y"] == 11
    assert all(expanded_by_id[view_id]["sizeY"] == 10 for view_id in repair.METRIC_VIEW_IDS)

    repeated_components, _ = repair.rewrite_dashboard(
        expanded_components,
        expanded_canvas,
        rows,
    )
    repeated_by_id = {item["id"]: item for item in repeated_components}
    assert repeated_by_id["old-a"]["y"] == 11


def test_validate_dashboard_rejects_stale_nested_sql() -> None:
    components = []
    canvas = {}
    rows = {
        spec.view_id: {"日期": "2026-07-20", spec.field: 0}
        for spec in repair.METRIC_SPECS
    }
    components, canvas = repair.rewrite_dashboard(components, canvas, rows)
    canvas[repair.METRIC_SPECS[0].view_id]["sourceConfig"]["sql"]["sql"] = "SELECT 1"

    try:
        repair.validate_dashboard(components, canvas, rows)
    except ValueError as exc:
        assert "嵌套 SQL" in str(exc)
    else:
        raise AssertionError("嵌套 SQL 与顶层 SQL 不一致时必须拒绝")


def test_rewrite_dashboard_is_idempotent() -> None:
    components = [{"id": "old", "x": 1, "y": 1, "sizeX": 72, "sizeY": 13}]
    canvas = {"old": {"id": "old"}}
    rows = {
        spec.view_id: {"日期": "2026-07-20", spec.field: 0}
        for spec in repair.METRIC_SPECS
    }

    first_components, first_canvas = repair.rewrite_dashboard(components, canvas, rows)
    second_components, second_canvas = repair.rewrite_dashboard(
        first_components, first_canvas, rows
    )

    old_component = next(item for item in second_components if item["id"] == "old")
    assert old_component["y"] == 11
    assert second_components == first_components
    assert second_canvas == first_canvas
