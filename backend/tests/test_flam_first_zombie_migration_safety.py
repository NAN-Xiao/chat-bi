"""First Zombie 严格迁移与旧脚本安全回归测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def test_legacy_broad_repair_entry_points_fail_closed() -> None:
    import repair_flam_first_zombie_dashboard_date_windows as date_windows
    import repair_flam_first_zombie_remaining_dashboards as remaining

    with pytest.raises(RuntimeError, match="repair_flam_first_zombie_semantic_dashboards.py"):
        date_windows.repair_dashboards(None)
    with pytest.raises(RuntimeError, match="repair_flam_first_zombie_semantic_dashboards.py"):
        remaining.repair_dashboards(None, {})
    with pytest.raises(RuntimeError, match="repair_flam_first_zombie_semantic_dashboards.py"):
        date_windows.main()
    with pytest.raises(RuntimeError, match="repair_flam_first_zombie_semantic_dashboards.py"):
        remaining.main()


class _Cursor:
    def __init__(self, row, update_rowcount: int = 1):
        self.row = row
        self.executed: list[str] = []
        self.parameters: list[object | None] = []
        self.update_rowcount = update_rowcount
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, sql, params=None) -> None:
        self.executed.append(sql)
        self.parameters.append(params)
        if "UPDATE public.core_dashboard" in sql:
            self.rowcount = self.update_rowcount

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row, update_rowcount: int = 1):
        self.cursor_value = _Cursor(row, update_rowcount)

    def cursor(self):
        return self.cursor_value


def test_legacy_realtime_skill_lookup_requires_exact_datasource_scope() -> None:
    import repair_flam_first_zombie_remaining_dashboards as remaining

    cursor = _Cursor(None)

    with pytest.raises(RuntimeError, match="Data Skill not found"):
        remaining.load_realtime_sql_blocks(cursor)

    query = cursor.executed[0]
    params = cursor.parameters[0]
    assert "datasource_ids = %s::jsonb" in query
    assert "datasource_ids @> %s::jsonb" not in query
    assert params == (remaining.TENANT_ID, json.dumps([remaining.DATASOURCE_ID]))


def test_realtime_repair_skips_backup_and_update_when_generated_content_is_unchanged(monkeypatch) -> None:
    import repair_flam_first_zombie_realtime_dashboard as realtime

    view_id = "4fc570b4be7d406c9f648d9088f760bb"
    sql = "SELECT stable"
    fields = ["hour_label", "pay_count"]
    rows = [{"hour_label": "10:00", "pay_count": 1}]
    field_meta = realtime.REALTIME_VIEW_FIELDS[view_id]
    view = {
        "chart": {
            "title": field_meta["y_name"],
            "type": "line",
            "xAxis": [{"name": field_meta["x_name"], "value": field_meta["x_value"], "type": "x"}],
            "yAxis": [{"name": field_meta["y_name"], "value": field_meta["y_value"], "type": "y"}],
            "columns": [
                {"name": field_meta["x_name"], "value": field_meta["x_value"]},
                {"name": field_meta["y_name"], "value": field_meta["y_value"]},
            ],
        },
        "datasource": realtime.DATASOURCE_ID,
        "sql": sql,
        "data": {"fields": fields, "data": rows},
        "fields": fields,
        "status": "success",
        "message": "",
        "dataState": "ready",
        "loadingProgress": 100,
        "snapshotRefreshedAt": 1,
    }
    row = (
        realtime.DASHBOARD_ID,
        "实时看板",
        realtime.DATASOURCE_ID,
        realtime.TENANT_ID,
        json.dumps({view_id: view}),
        0,
    )
    connection = _Connection(row)

    monkeypatch.setattr(realtime, "run_chart_sql", lambda conf, query: (fields, rows))
    monkeypatch.setattr(realtime, "backup_dashboard", lambda value: pytest.fail(f"不应备份: {value}"))

    realtime.repair_dashboard(connection, object(), {view_id: sql})

    select_sql = connection.cursor_value.executed[0]
    select_params = connection.cursor_value.parameters[0]
    assert "AND datasource = %s" in select_sql
    assert select_params == (realtime.DASHBOARD_ID, realtime.TENANT_ID, realtime.DATASOURCE_ID)
    assert not any("UPDATE public.core_dashboard" in sql for sql in connection.cursor_value.executed)


@pytest.mark.parametrize("update_rowcount", [0, 2])
def test_realtime_repair_fails_when_scoped_update_does_not_change_exactly_one_row(
    monkeypatch,
    update_rowcount,
) -> None:
    import repair_flam_first_zombie_realtime_dashboard as realtime

    view_id = "4fc570b4be7d406c9f648d9088f760bb"
    fields = ["hour_label", "pay_count"]
    rows = [{"hour_label": "10:00", "pay_count": 1}]
    field_meta = realtime.REALTIME_VIEW_FIELDS[view_id]
    view = {
        "chart": {
            "title": field_meta["y_name"],
            "type": "line",
            "xAxis": [],
            "yAxis": [],
            "columns": [],
        },
        "datasource": realtime.DATASOURCE_ID,
        "sql": "SELECT stale",
        "data": {"fields": [], "data": []},
        "fields": [],
    }
    row = (
        realtime.DASHBOARD_ID,
        "实时看板",
        realtime.DATASOURCE_ID,
        realtime.TENANT_ID,
        json.dumps({view_id: view}),
        0,
    )
    connection = _Connection(row, update_rowcount=update_rowcount)

    monkeypatch.setattr(realtime, "run_chart_sql", lambda conf, query: (fields, rows))
    monkeypatch.setattr(realtime, "backup_dashboard", lambda value: None)

    with pytest.raises(RuntimeError, match="精确更新"):
        realtime.repair_dashboard(connection, object(), {view_id: "SELECT repaired"})

    update_index = next(
        index
        for index, sql in enumerate(connection.cursor_value.executed)
        if "UPDATE public.core_dashboard" in sql
    )
    update_sql = connection.cursor_value.executed[update_index]
    update_params = connection.cursor_value.parameters[update_index]
    assert "WHERE id = %s" in update_sql
    assert "AND tenant_id = %s" in update_sql
    assert "AND datasource = %s" in update_sql
    assert update_params is not None
    assert update_params[-3:] == (
        realtime.DASHBOARD_ID,
        realtime.TENANT_ID,
        realtime.DATASOURCE_ID,
    )


def test_realtime_repair_refreshes_only_changed_component_snapshot(monkeypatch) -> None:
    import repair_flam_first_zombie_realtime_dashboard as realtime

    stable_view_id = "4fc570b4be7d406c9f648d9088f760bb"
    changed_view_id = "2149b7abbc6c4cd7ad6f52379e69b15a"
    stable_fields = ["hour_label", "pay_count"]
    stable_rows = [{"hour_label": "10:00", "pay_count": 1}]
    stable_meta = realtime.REALTIME_VIEW_FIELDS[stable_view_id]
    stable_view = {
        "chart": {
            "title": stable_meta["y_name"],
            "type": "line",
            "xAxis": [{"name": stable_meta["x_name"], "value": stable_meta["x_value"], "type": "x"}],
            "yAxis": [{"name": stable_meta["y_name"], "value": stable_meta["y_value"], "type": "y"}],
            "columns": [
                {"name": stable_meta["x_name"], "value": stable_meta["x_value"]},
                {"name": stable_meta["y_name"], "value": stable_meta["y_value"]},
            ],
        },
        "datasource": realtime.DATASOURCE_ID,
        "sql": "SELECT stable",
        "data": {"fields": stable_fields, "data": stable_rows},
        "fields": stable_fields,
        "status": "success",
        "message": "",
        "dataState": "ready",
        "loadingProgress": 100,
        "snapshotRefreshedAt": 123,
    }
    changed_view = {
        "chart": {"title": "累计付费事件次数", "type": "line"},
        "datasource": realtime.DATASOURCE_ID,
        "sql": "SELECT stale",
        "data": {"fields": [], "data": []},
        "fields": [],
        "snapshotRefreshedAt": 456,
    }
    row = (
        realtime.DASHBOARD_ID,
        "实时看板",
        realtime.DATASOURCE_ID,
        realtime.TENANT_ID,
        json.dumps({stable_view_id: stable_view, changed_view_id: changed_view}),
        0,
    )
    connection = _Connection(row)
    backups: list[object] = []

    def fake_run_chart_sql(conf, sql):
        del conf
        if sql == "SELECT stable":
            return stable_fields, stable_rows
        return ["hour_label", "cumulative_pay_count"], [{"hour_label": "10:00", "cumulative_pay_count": 1}]

    monkeypatch.setattr(realtime, "run_chart_sql", fake_run_chart_sql)
    monkeypatch.setattr(realtime, "backup_dashboard", lambda value: backups.append(value))
    monkeypatch.setattr(realtime.time, "time", lambda: 1_700_000_000.123)

    realtime.repair_dashboard(
        connection,
        object(),
        {stable_view_id: "SELECT stable", changed_view_id: "SELECT repaired"},
    )

    update_index = next(
        index
        for index, sql in enumerate(connection.cursor_value.executed)
        if "UPDATE public.core_dashboard" in sql
    )
    update_params = connection.cursor_value.parameters[update_index]
    assert update_params is not None
    updated_canvas = json.loads(update_params[0])
    assert updated_canvas[stable_view_id]["snapshotRefreshedAt"] == 123
    assert updated_canvas[changed_view_id]["snapshotRefreshedAt"] == 1_700_000_000_123
    assert len(backups) == 1
    assert backups[0]["canvas_view_info"] == row[4]


def test_realtime_skill_lookup_requires_exact_datasource_scope() -> None:
    source = (TOOLS_DIR / "repair_flam_first_zombie_realtime_dashboard.py").read_text(encoding="utf-8")

    assert "datasource_ids = %s::jsonb" in source
    assert "datasource_ids @> %s::jsonb" not in source


def test_realtime_diagnostics_do_not_select_or_output_personal_payload(monkeypatch) -> None:
    import repair_flam_first_zombie_realtime_dashboard as realtime

    executed_sql: list[str] = []

    def fake_run_chart_sql(conf, sql):
        del conf
        executed_sql.append(sql)
        return [], []

    monkeypatch.setattr(realtime, "run_chart_sql", fake_run_chart_sql)

    realtime.verify_data_side(object())

    ccu_sql = next(sql for sql in executed_sql if "FROM `event` e" in sql)
    ccu_select = ccu_sql.split("FROM `event` e", maxsplit=1)[0]
    assert "MIN(e.personal)" not in ccu_select
    assert "MAX(e.personal)" not in ccu_select
    assert " e.personal AS" not in ccu_select
    assert ccu_select.count("e.personal") == 1
    assert "JSON_EXTRACT(e.personal, '$.ed_ccu')" in ccu_select
