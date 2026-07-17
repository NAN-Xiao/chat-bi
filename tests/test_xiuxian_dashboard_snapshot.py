from __future__ import annotations

import hashlib
import importlib
import json
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

snapshot = importlib.import_module("xiuxian_dashboard_snapshot")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_nine_dashboard_snapshots(
    *, drawer_count: int = 45, nonempty_count: int = 45
) -> list[snapshot.DashboardSnapshot]:
    view_ids = sorted(snapshot.EXPECTED_VIEW_IDS)[:drawer_count]
    dashboards = []
    for dashboard_index in range(9):
        start = dashboard_index * 5
        dashboard_view_ids = view_ids[start : start + 5]
        canvas = {}
        for global_index, view_id in enumerate(dashboard_view_ids, start=start):
            sql = f"SELECT {global_index} AS `指标`" if global_index < nonempty_count else ""
            canvas[view_id] = {
                "id": view_id,
                "sql": sql,
                "chart": {"title": f"组件 {global_index}", "columns": ["指标"]},
            }
        raw_canvas = json.dumps(canvas, ensure_ascii=False, indent=2)
        dashboards.append(
            snapshot.DashboardSnapshot.from_row(
                (
                    f"dashboard-{dashboard_index}",
                    f"推荐看板 {dashboard_index}",
                    snapshot.TENANT_ID,
                    snapshot.DATASOURCE_ID,
                    raw_canvas,
                )
            )
        )
    return dashboards


def test_write_verified_backup_contains_full_canvas_and_drawer_sql(tmp_path):
    dashboards = make_nine_dashboard_snapshots(drawer_count=45, nonempty_count=45)

    path = snapshot.write_verified_backup(
        dashboards, tmp_path, timestamp="20260716-120000"
    )
    manifest = snapshot.verify_backup(path)

    assert manifest.dashboard_count == 9
    assert manifest.drawer_count == 45
    assert manifest.nonempty_drawer_count == 45
    assert len(list((path / "dashboards").glob("*.json"))) == 9

    dashboard_payload = json.loads(
        (path / "dashboards" / "dashboard-0.json").read_text(encoding="utf-8")
    )
    assert dashboard_payload["canvas_view_info"] == dashboards[0].canvas_view_info

    drawer_rows = json.loads((path / "drawer_sql.json").read_text(encoding="utf-8"))
    assert {row["view_id"] for row in drawer_rows} == set(snapshot.EXPECTED_VIEW_IDS)
    first_drawer = drawer_rows[0]
    assert first_drawer["sql_sha256"] == _sha256_text(first_drawer["sql"])
    assert manifest.sql_sha256[
        f'{first_drawer["dashboard_id"]}:{first_drawer["view_id"]}'
    ] == first_drawer["sql_sha256"]
    assert set(manifest.file_sha256) == {
        "drawer_sql.json",
        *(f"dashboards/{dashboard.id}.json" for dashboard in dashboards),
    }


def test_backup_refuses_existing_directory(tmp_path):
    dashboards = make_nine_dashboard_snapshots(drawer_count=45, nonempty_count=45)
    snapshot.write_verified_backup(dashboards, tmp_path, timestamp="20260716-120000")

    with pytest.raises(FileExistsError):
        snapshot.write_verified_backup(
            dashboards, tmp_path, timestamp="20260716-120000"
        )


def test_backup_verification_does_not_depend_on_dashboard_filename_order(tmp_path):
    dashboards = list(reversed(make_nine_dashboard_snapshots()))

    path = snapshot.write_verified_backup(
        dashboards, tmp_path, timestamp="20260716-120000"
    )

    assert snapshot.verify_backup(path).dashboard_count == 9


@pytest.mark.parametrize(
    ("dashboards", "message"),
    [
        (lambda rows: rows[:-1], "看板数量"),
        (
            lambda rows: [
                snapshot.DashboardSnapshot(
                    id=rows[0].id,
                    name=rows[0].name,
                    tenant_id=rows[0].tenant_id,
                    datasource=rows[0].datasource,
                    canvas_view_info=rows[0].canvas_view_info,
                    drawers=rows[0].drawers[:-1],
                ),
                *rows[1:],
            ],
            "抽屉数量",
        ),
    ],
)
def test_backup_fails_closed_on_wrong_counts(tmp_path, dashboards, message):
    rows = dashboards(make_nine_dashboard_snapshots())

    with pytest.raises(ValueError, match=message):
        snapshot.write_verified_backup(rows, tmp_path, timestamp="20260716-120000")


def test_backup_rejects_empty_sql_and_unknown_view_id(tmp_path):
    with pytest.raises(ValueError, match="非空 SQL"):
        snapshot.write_verified_backup(
            make_nine_dashboard_snapshots(nonempty_count=44),
            tmp_path,
            timestamp="20260716-120000",
        )

    dashboards = make_nine_dashboard_snapshots()
    first = dashboards[0]
    canvas = json.loads(first.canvas_view_info)
    old_view_id = next(iter(canvas))
    canvas["unknown-view-id"] = canvas.pop(old_view_id)
    dashboards[0] = snapshot.DashboardSnapshot.from_row(
        (
            first.id,
            first.name,
            first.tenant_id,
            first.datasource,
            json.dumps(canvas, ensure_ascii=False, indent=2),
        )
    )

    with pytest.raises(ValueError, match="view id"):
        snapshot.write_verified_backup(
            dashboards, tmp_path, timestamp="20260716-120000"
        )


def test_verify_backup_rejects_file_and_sql_hash_tampering(tmp_path):
    dashboards = make_nine_dashboard_snapshots()
    path = snapshot.write_verified_backup(
        dashboards, tmp_path, timestamp="20260716-120000"
    )
    drawer_path = path / "drawer_sql.json"
    drawer_rows = json.loads(drawer_path.read_text(encoding="utf-8"))
    drawer_rows[0]["sql"] += " -- tampered"
    drawer_path.write_text(
        json.dumps(drawer_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="哈希"):
        snapshot.verify_backup(path)


def test_verify_backup_rejects_manifest_byte_tampering(tmp_path):
    dashboards = make_nine_dashboard_snapshots()
    path = snapshot.write_verified_backup(
        dashboards, tmp_path, timestamp="20260716-120000"
    )
    manifest_path = path / "manifest.json"
    manifest_value = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest_value["manifest_payload_sha256"]) == 64

    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="manifest"):
        snapshot.verify_backup(path)


def test_failed_write_cleans_staging_and_allows_same_timestamp_retry(
    tmp_path, monkeypatch
):
    dashboards = make_nine_dashboard_snapshots()
    timestamp = "20260716-120000"
    original_write_json = snapshot._write_json
    write_count = 0

    def fail_on_third_write(path, value):
        nonlocal write_count
        write_count += 1
        if write_count == 3:
            raise RuntimeError("injected write failure")
        original_write_json(path, value)

    monkeypatch.setattr(snapshot, "_write_json", fail_on_third_write)
    with pytest.raises(RuntimeError, match="injected write failure"):
        snapshot.write_verified_backup(dashboards, tmp_path, timestamp=timestamp)

    assert not (tmp_path / timestamp).exists()
    assert list(tmp_path.glob(f".{timestamp}.*.staging")) == []

    monkeypatch.setattr(snapshot, "_write_json", original_write_json)
    path = snapshot.write_verified_backup(dashboards, tmp_path, timestamp=timestamp)
    assert snapshot.verify_backup(path).dashboard_count == 9


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows


class _FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = _FakeCursor(rows)

    def cursor(self):
        return nullcontext(self.cursor_instance)


def test_load_recommended_dashboards_is_read_only_and_preserves_raw_canvas():
    view_id = sorted(snapshot.EXPECTED_VIEW_IDS)[0]
    raw_canvas = (
        '{\n  "' + view_id + '": {"sql": "SELECT 1", "title": "原始顺序"}\n}'
    )
    connection = _FakeConnection(
        [
            (
                "dashboard-1",
                "推荐看板",
                snapshot.TENANT_ID,
                snapshot.DATASOURCE_ID,
                raw_canvas,
            )
        ]
    )

    dashboards = snapshot.load_recommended_dashboards(connection)

    assert len(dashboards) == 1
    assert dashboards[0].canvas_view_info == raw_canvas
    assert dashboards[0].drawers[0].sql == "SELECT 1"
    assert dashboards[0].drawers[0].sql_sha256 == _sha256_text("SELECT 1")
    assert connection.cursor_instance.params == (
        snapshot.TENANT_ID,
        snapshot.DATASOURCE_ID,
    )
    normalized_sql = " ".join(connection.cursor_instance.sql.split()).upper()
    assert normalized_sql.startswith("SELECT ")
    assert " UPDATE " not in f" {normalized_sql} "
    assert " DELETE " not in f" {normalized_sql} "
    assert " INSERT " not in f" {normalized_sql} "
