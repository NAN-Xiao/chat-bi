"""核心看板指标卡日期表达式迁移契约。"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import migrate_core_dashboard_metric_date_picker as migration  # noqa: E402


FIXED_DAY_SQL = """SELECT
    DATE_FORMAT(CURDATE(), '%Y-%m-%d') AS `日期`,
    COUNT(DISTINCT uid) AS `活跃用户`
FROM event
WHERE dt = CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
  AND prod = 110000047
  AND event = 'UserActive'"""

FIXED_REALTIME_DAY_SQL = FIXED_DAY_SQL.replace("FROM event\n", "FROM event_realtime\n")

PARAMETERIZED_SQL = """SELECT
    DATE_FORMAT(STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS `日期`,
    COUNT(DISTINCT uid) AS `活跃用户`
FROM event
WHERE dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
  AND prod = 110000047
  AND event = 'UserActive'"""


def metric_view(sql: str = FIXED_DAY_SQL) -> dict:
    return {
        "id": "metric-1",
        "chart": {"id": "metric-1", "type": "metric", "title": "活跃用户"},
        "sql": sql,
        "sourceConfig": {
            "sql": {
                "builder": {
                    "timeField": "dt",
                    "timeRange": "today",
                }
            }
        },
        "pivot": {"enabled": False},
        "unrelated": {"keep": [1, 2, 3]},
    }


def test_migrate_metric_view_enables_yesterday_expression() -> None:
    original = metric_view()

    migrated = migration.migrate_metric_view(
        original,
        time_field="dt",
        parameter_type="yyyymmdd_number",
    )

    builder = migrated["sourceConfig"]["sql"]["builder"]
    assert builder["metricDateExpressionEnabled"] is True
    assert builder["dateExpressionPickerEnabled"] is True
    assert builder["timeField"] == "dt"
    assert builder["timeRange"] == "expression"
    assert builder["timeExpression"] == migration.YESTERDAY_EXPRESSION
    assert migrated["pivot"]["time_field"] == "dt"
    assert migrated["pivot"]["range_enabled"] is True
    assert migrated["pivot"]["date_parameter_type"] == "yyyymmdd_number"
    assert migrated["pivot"]["date_expression"] == migration.YESTERDAY_EXPRESSION
    assert "{{dashboard_start_yyyymmdd}}" in migrated["sql"]
    assert "{{dashboard_end_yyyymmdd}}" in migrated["sql"]
    assert "CURDATE()" not in migrated["sql"]
    assert migrated["unrelated"] == original["unrelated"]


def test_migrate_metric_view_does_not_mutate_input_and_is_idempotent() -> None:
    original = metric_view()
    snapshot = copy.deepcopy(original)

    first = migration.migrate_metric_view(
        original,
        time_field="dt",
        parameter_type="yyyymmdd_number",
    )
    second = migration.migrate_metric_view(
        first,
        time_field="dt",
        parameter_type="yyyymmdd_number",
    )

    assert original == snapshot
    assert second == first


def test_migrate_metric_view_accepts_existing_dashboard_parameters() -> None:
    migrated = migration.migrate_metric_view(
        metric_view(PARAMETERIZED_SQL),
        time_field="dt",
        parameter_type="yyyymmdd_number",
    )

    assert migrated["sql"] == PARAMETERIZED_SQL


def test_migrate_metric_view_converts_realtime_table_to_historical_table() -> None:
    migrated = migration.migrate_metric_view(
        metric_view(FIXED_REALTIME_DAY_SQL),
        time_field="event.dt",
        parameter_type="yyyymmdd_number",
    )

    assert "FROM event\n" in migrated["sql"]
    assert "event_realtime" not in migrated["sql"]


def test_migrate_metric_view_rejects_non_metric_chart() -> None:
    view = metric_view()
    view["chart"]["type"] = "line"

    with pytest.raises(ValueError, match="metric"):
        migration.migrate_metric_view(
            view,
            time_field="dt",
            parameter_type="yyyymmdd_number",
        )


def test_parameterize_metric_sql_rejects_unknown_date_pattern() -> None:
    with pytest.raises(ValueError, match="日期模式"):
        migration.parameterize_metric_sql(
            "SELECT COUNT(*) FROM event WHERE prod = 110000047",
            "yyyymmdd_number",
        )


def test_migrate_target_views_preserves_non_targets() -> None:
    canvas = {
        "metric-1": metric_view(),
        "line-1": {"chart": {"type": "line"}, "sql": "SELECT 1"},
    }
    original_line = copy.deepcopy(canvas["line-1"])

    migrated = migration.migrate_target_views(
        canvas,
        targets={
            "metric-1": migration.ChartTarget(
                chart_id="metric-1",
                title="活跃用户",
                time_field="dt",
                parameter_type="yyyymmdd_number",
            )
        },
    )

    assert migrated["line-1"] == original_line
    assert migrated["line-1"] is not canvas["line-1"]
    assert migrated["metric-1"]["sourceConfig"]["sql"]["builder"][
        "metricDateExpressionEnabled"
    ] is True


def test_migrate_target_views_rejects_title_mismatch() -> None:
    canvas = {"metric-1": metric_view()}

    with pytest.raises(RuntimeError, match="身份"):
        migration.migrate_target_views(
            canvas,
            targets={
                "metric-1": migration.ChartTarget(
                    chart_id="metric-1",
                    title="新增用户",
                    time_field="dt",
                    parameter_type="yyyymmdd_number",
                )
            },
        )


def test_target_manifest_is_strictly_scoped_to_three_dashboards_and_12_metrics() -> None:
    assert {
        (target.workspace, target.tenant_id, target.dashboard_id, target.datasource_id)
        for target in migration.DASHBOARD_TARGETS
    } == {
        ("flam", 7477202383789887488, "6d50bd7dfc9f46ba961d636814c3294d", 3),
        ("修仙", 7482727237662281728, "afe201c9762c448aa0495f3508c01793", 6),
        ("模板_修仙", 7489861204282707968, "1f82f42788bc414d8139b20742aea882", 6),
    }
    assert sum(len(target.charts) for target in migration.DASHBOARD_TARGETS) == 12
    assert all(target.dashboard_name == "核心看板" for target in migration.DASHBOARD_TARGETS)
    assert all(chart.sql_sha256 for target in migration.DASHBOARD_TARGETS for chart in target.charts)


def test_migrate_target_views_rejects_sql_hash_mismatch() -> None:
    canvas = {"metric-1": metric_view()}
    wrong_hash = hashlib.sha256(b"different sql").hexdigest()

    with pytest.raises(RuntimeError, match="SQL 哈希"):
        migration.migrate_target_views(
            canvas,
            targets={
                "metric-1": migration.ChartTarget(
                    chart_id="metric-1",
                    title="活跃用户",
                    time_field="dt",
                    parameter_type="yyyymmdd_number",
                    sql_sha256=wrong_hash,
                )
            },
        )


class _Cursor:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount
        self.sql = ""
        self.params = None

    def execute(self, sql: str, params: tuple) -> None:
        self.sql = sql
        self.params = params

    def fetchone(self):
        return getattr(self, "row", None)


def test_cas_update_requires_exactly_one_row() -> None:
    cursor = _Cursor(rowcount=0)
    target = migration.DASHBOARD_TARGETS[0]

    with pytest.raises(RuntimeError, match="CAS"):
        migration.cas_update_dashboard(
            cursor,
            target=target,
            old_raw="old",
            new_raw="new",
        )

    assert "canvas_view_info = %s" in cursor.sql
    assert "tenant_id = %s" in cursor.sql
    assert cursor.params[-1] == "old"


def test_verify_migrated_canvas_rejects_non_target_change() -> None:
    original = {
        "metric-1": metric_view(),
        "line-1": {"chart": {"type": "line"}, "sql": "SELECT 1"},
    }
    target = migration.ChartTarget(
        chart_id="metric-1",
        title="活跃用户",
        time_field="dt",
        parameter_type="yyyymmdd_number",
        sql_sha256=hashlib.sha256(FIXED_DAY_SQL.encode()).hexdigest(),
    )
    migrated = migration.migrate_target_views(original, targets={"metric-1": target})
    migrated["line-1"]["sql"] = "SELECT 2"

    with pytest.raises(RuntimeError, match="非目标"):
        migration.verify_migrated_canvas(
            migrated,
            targets={"metric-1": target},
            unchanged_hashes=migration.non_target_hashes(
                original, target_ids={"metric-1"}
            ),
        )


def test_verify_migrated_view_rejects_realtime_table() -> None:
    target = migration.ChartTarget(
        chart_id="metric-1",
        title="活跃用户",
        time_field="event.dt",
        parameter_type="yyyymmdd_number",
    )
    migrated = migration.migrate_metric_view(
        metric_view(FIXED_REALTIME_DAY_SQL),
        time_field=target.time_field,
        parameter_type=target.parameter_type,
    )
    migrated["sql"] = migrated["sql"].replace("FROM event\n", "FROM event_realtime\n")

    with pytest.raises(RuntimeError, match="实时表"):
        migration.verify_migrated_view(migrated, target=target)


def test_verify_migrated_view_rejects_realtime_table_in_join() -> None:
    target = migration.ChartTarget(
        chart_id="metric-1",
        title="活跃用户",
        time_field="event.dt",
        parameter_type="yyyymmdd_number",
    )
    migrated = migration.migrate_metric_view(
        metric_view(FIXED_DAY_SQL),
        time_field=target.time_field,
        parameter_type=target.parameter_type,
    )
    migrated["sql"] += "\nJOIN event_realtime recent ON recent.uid = event.uid"
    migrated["sourceConfig"]["sql"]["sql"] = migrated["sql"]

    with pytest.raises(RuntimeError, match="实时表"):
        migration.verify_migrated_view(migrated, target=target)


def test_verify_migrated_view_rejects_stale_nested_sql() -> None:
    target = migration.ChartTarget(
        chart_id="metric-1",
        title="活跃用户",
        time_field="event.dt",
        parameter_type="yyyymmdd_number",
    )
    migrated = migration.migrate_metric_view(
        metric_view(FIXED_DAY_SQL),
        time_field=target.time_field,
        parameter_type=target.parameter_type,
    )
    migrated["sourceConfig"]["sql"]["sql"] = FIXED_DAY_SQL

    with pytest.raises(RuntimeError, match="嵌套 SQL"):
        migration.verify_migrated_view(migrated, target=target)


def test_target_time_fields_follow_workspace_metadata() -> None:
    by_workspace = {target.workspace: target for target in migration.DASHBOARD_TARGETS}
    assert {chart.time_field for chart in by_workspace["flam"].charts} == {"dt"}
    assert {chart.time_field for chart in by_workspace["修仙"].charts} == {"event.dt"}
    assert {chart.time_field for chart in by_workspace["模板_修仙"].charts} == {
        "event.dt"
    }


def test_backup_payload_roundtrip_validates_three_owned_rows(tmp_path: Path) -> None:
    rows = []
    new_raw_by_id = {}
    for index, target in enumerate(migration.DASHBOARD_TARGETS):
        old_raw = json.dumps({"old": index})
        new_raw = json.dumps({"new": index})
        rows.append(
            {
                "id": target.dashboard_id,
                "tenant_id": target.tenant_id,
                "name": target.dashboard_name,
                "datasource": target.datasource_id,
                "create_by": target.create_by,
                "canvas_view_info": old_raw,
                "update_time": 123,
            }
        )
        new_raw_by_id[target.dashboard_id] = new_raw

    path = migration.write_backup(rows, new_raw_by_id=new_raw_by_id, directory=tmp_path)
    payload = migration.load_restore_payload(path)

    assert len(payload["dashboards"]) == 3
    assert {
        item["dashboard_id"] for item in payload["dashboards"]
    } == {target.dashboard_id for target in migration.DASHBOARD_TARGETS}


def test_restore_payload_rejects_tampered_old_canvas(tmp_path: Path) -> None:
    target = migration.DASHBOARD_TARGETS[0]
    path = tmp_path / "backup.json"
    payload = {
        "schema": migration.BACKUP_SCHEMA,
        "dashboards": [
            {
                "workspace": target.workspace,
                "dashboard_id": target.dashboard_id,
                "tenant_id": target.tenant_id,
                "datasource_id": target.datasource_id,
                "create_by": target.create_by,
                "old_canvas_sha256": migration.sha256_text("original"),
                "new_canvas_sha256": migration.sha256_text("new"),
                "row": {"canvas_view_info": "tampered"},
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="哈希"):
        migration.load_restore_payload(path)


def test_transaction_readback_rejects_database_value_different_from_planned() -> None:
    target = migration.DASHBOARD_TARGETS[0]
    cursor = _Cursor(rowcount=1)
    cursor.row = {
        "id": target.dashboard_id,
        "tenant_id": target.tenant_id,
        "name": target.dashboard_name,
        "datasource": target.datasource_id,
        "create_by": target.create_by,
        "canvas_view_info": "unexpected",
    }

    with pytest.raises(RuntimeError, match="事务内读回"):
        migration.verify_transaction_readback(
            cursor,
            target=target,
            expected_raw="planned",
        )

    assert "FOR UPDATE" not in cursor.sql.upper()


def test_migrated_source_config_sql_matches_top_level_sql() -> None:
    view = metric_view(FIXED_REALTIME_DAY_SQL)
    view["sourceConfig"]["sql"]["sql"] = FIXED_REALTIME_DAY_SQL

    migrated = migration.migrate_metric_view(
        view,
        time_field="event.dt",
        parameter_type="yyyymmdd_number",
    )

    assert migrated["sourceConfig"]["sql"]["sql"] == migrated["sql"]
