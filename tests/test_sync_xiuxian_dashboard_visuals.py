from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import sync_xiuxian_dashboard_visuals as sync_module  # noqa: E402
from sync_xiuxian_dashboard_visuals import (  # noqa: E402
    CORE_DASHBOARD_ID,
    ROI_EXTRA_VIEW_ID,
    TENANT_ID,
    _load_targets,
    main,
    run,
    restore_backup,
    transform_core_dashboard,
    transform_roi_dashboard,
    validate_layout,
)


def _component(
    view_id: str, x: int, y: int, size_x: int = 36, size_y: int = 16
) -> dict:
    return {"id": view_id, "x": x, "y": y, "sizeX": size_x, "sizeY": size_y}


def _view(
    view_id: str,
    title: str,
    chart_type: str,
    sql: str,
    *,
    datasource: int = 6,
    fields: list[str] | None = None,
) -> dict:
    return {
        "id": view_id,
        "datasource": datasource,
        "sql": sql,
        "dateFilter": {"enabled": True},
        "sourceConfig": {"keep": True},
        "sources": [{"id": "source-1"}],
        "primarySource": "source-1",
        "pivot": {"enabled": False},
        "dataSourceType": "sql",
        "fields": fields or ["日期", "指标"],
        "chart": {
            "id": view_id,
            "title": title,
            "type": chart_type,
            "sourceType": chart_type,
            "xAxis": [{"value": "日期"}],
            "yAxis": [{"value": "指标"}],
            "series": [],
        },
    }


def _core_fixture() -> tuple[list[dict], dict[str, dict]]:
    specs = [
        ("active", "活跃用户", "metric", 1, 1, 18, 10),
        ("new", "新增用户", "metric", 19, 1, 18, 10),
        ("pay_users", "充值人数", "metric", 37, 1, 18, 10),
        ("pay_amount", "充值总额", "metric", 55, 1, 18, 10),
        ("arpu", "ARPU与ARPPU", "line", 1, 11, 36, 16),
        ("payer_rate", "日付费率", "line", 37, 11, 36, 16),
        ("dau", "DAU趋势", "line", 1, 27, 36, 16),
        ("new_trend", "新增用户趋势", "line", 37, 27, 36, 16),
        ("channel_new", "每日渠道新增用户", "line", 1, 43, 36, 16),
        ("cum_pay", "累计付费用户趋势", "line", 37, 43, 36, 16),
        ("gift", "礼包购买情况", "table", 1, 59, 36, 16),
        ("channel_pay", "渠道累计付费排行", "bar", 37, 59, 36, 16),
        ("extra", "新增用户ARPU与ARPPU", "table", 1, 75, 36, 14),
        ("level", "当前等级分布", "column", 37, 75, 35, 16),
        ("retention", "各渠道新增留存", "table", 1, 91, 72, 18),
    ]
    components = [
        _component(view_id, x, y, size_x, size_y)
        for view_id, _, _, x, y, size_x, size_y in specs
    ]
    canvas = {
        view_id: _view(view_id, title, chart_type, f"SELECT '{title}'")
        for view_id, title, chart_type, *_ in specs
    }
    canvas["arpu"]["chart"]["xAxis"] = [{"value": "dt"}]
    canvas["arpu"]["chart"]["yAxis"] = [{"value": "ARPU"}, {"value": "ARPPU"}]
    canvas["arpu"]["fields"] = ["dt", "ARPU", "ARPPU"]
    canvas["new_trend"]["chart"]["yAxis"] = [{"value": "新增用户数"}]
    canvas["new_trend"]["fields"] = ["日期", "新增用户数"]
    canvas["channel_new"]["chart"]["series"] = [{"value": "渠道"}]
    canvas["channel_new"]["chart"]["yAxis"] = [{"value": "新增用户数"}]
    canvas["channel_new"]["fields"] = ["日期", "渠道", "新增用户数"]
    return components, canvas


def _roi_fixture() -> tuple[list[dict], dict[str, dict]]:
    specs = [
        ("install", "安装投放趋势", "line", 1, 1, 72, 16),
        ("summary", "ROI总览", "table", 1, 17, 72, 15),
        ("region", "ROI地区总览", "table", 1, 32, 72, 15),
        ("ad_region", "ROI广告地区总览", "table", 1, 47, 72, 17),
    ]
    components = [
        _component(view_id, x, y, size_x, size_y)
        for view_id, _, _, x, y, size_x, size_y in specs
    ]
    canvas = {
        view_id: _view(view_id, title, chart_type, f"SELECT '{title}'")
        for view_id, title, chart_type, *_ in specs
    }
    canvas["summary"]["sql"] = "SELECT roi_sql FROM xiuxian"
    canvas["summary"]["fields"] = [
        "日期",
        "安装数",
        "投放成本",
        "单次安装成本",
        "首日收入",
        "3日收入",
        "首日ROI",
        "3日ROI",
    ]
    canvas["region"]["fields"] = [
        "日期",
        "地区",
        "首日ROI",
        "3日ROI",
    ]
    canvas["ad_region"]["fields"] = [
        "日期",
        "广告渠道",
        "安装数",
        "投放成本",
        "单次安装成本",
        "首日收入",
        "3日收入",
        "首日ROI",
        "3日ROI",
    ]
    canvas["install"]["fields"] = ["日期", "安装数", "投放成本", "单次安装成本"]
    return components, canvas


def test_core_visual_transform_updates_shared_chart_types_without_sql_changes() -> None:
    components, canvas = _core_fixture()
    original = copy.deepcopy(canvas)

    new_components, new_canvas, summary = transform_core_dashboard(components, canvas)

    assert new_canvas["arpu"]["chart"]["type"] == "column"
    assert new_canvas["new_trend"]["chart"]["type"] == "column"
    assert new_canvas["channel_new"]["chart"]["type"] == "area"
    assert new_canvas["arpu"]["sql"] == original["arpu"]["sql"]
    assert new_canvas["arpu"]["datasource"] == 6
    assert summary["changed"] is True
    validate_layout(new_components)


def test_roi_visual_transform_adds_roi_chart_from_xiuxian_sql_and_is_idempotent() -> (
    None
):
    components, canvas = _roi_fixture()

    new_components, new_canvas, summary = transform_roi_dashboard(components, canvas)

    assert len(new_components) == 5
    extra_component = next(
        item for item in new_components if item["id"] == ROI_EXTRA_VIEW_ID
    )
    assert extra_component["component"] == "SQView"
    assert extra_component["name"] == "new-view"
    assert extra_component["propValue"] == "&nbsp;"
    assert extra_component["_dragId"] == ROI_EXTRA_VIEW_ID
    assert new_canvas[ROI_EXTRA_VIEW_ID]["sql"] == canvas["summary"]["sql"]
    assert (
        new_canvas[ROI_EXTRA_VIEW_ID]["datasource"] == canvas["summary"]["datasource"]
    )
    assert new_canvas[ROI_EXTRA_VIEW_ID]["chart"]["title"] == "图表"
    assert new_canvas[ROI_EXTRA_VIEW_ID]["chart"]["type"] == "column"
    assert [
        item["value"] for item in new_canvas[ROI_EXTRA_VIEW_ID]["chart"]["yAxis"]
    ] == [
        "首日ROI",
        "3日ROI",
    ]
    assert new_canvas["region"]["chart"]["type"] == "area"
    assert new_canvas["ad_region"]["chart"]["type"] == "column"
    validate_layout(new_components)

    again_components, again_canvas, again_summary = transform_roi_dashboard(
        new_components, new_canvas
    )
    assert again_components == new_components
    assert again_canvas == new_canvas
    assert again_summary["changed"] is False


def test_visual_transform_rejects_existing_conflicting_roi_chart() -> None:
    components, canvas = _roi_fixture()
    components.append(_component(ROI_EXTRA_VIEW_ID, 36, 1, 36, 17))
    canvas[ROI_EXTRA_VIEW_ID] = _view(
        ROI_EXTRA_VIEW_ID, "错误标题", "line", "SELECT wrong"
    )

    with pytest.raises(ValueError, match="ROI (新图|看板组件清单)"):
        transform_roi_dashboard(components, canvas)


def test_visual_transform_rejects_roi_execution_config_drift() -> None:
    components, canvas = _roi_fixture()
    new_components, new_canvas, _ = transform_roi_dashboard(components, canvas)
    new_canvas[ROI_EXTRA_VIEW_ID]["sources"] = [{"id": "wrong-source"}]

    with pytest.raises(ValueError, match="ROI 新图"):
        transform_roi_dashboard(new_components, new_canvas)


def test_visual_transform_rejects_missing_roi_fields() -> None:
    components, canvas = _roi_fixture()
    canvas["region"]["fields"].remove("地区")

    with pytest.raises(ValueError, match="ROI地区总览.*地区"):
        transform_roi_dashboard(components, canvas)


def test_visual_transform_rejects_unexpected_roi_component() -> None:
    components, canvas = _roi_fixture()
    components.append(_component("unexpected", 1, 70, 72, 10))
    canvas["unexpected"] = _view("unexpected", "额外图表", "line", "SELECT unexpected")

    with pytest.raises(ValueError, match="ROI 看板组件清单"):
        transform_roi_dashboard(components, canvas)


def test_visual_transform_rejects_conflicting_roi_component_metadata() -> None:
    components, canvas = _roi_fixture()
    new_components, new_canvas, _ = transform_roi_dashboard(components, canvas)
    extra_component = next(
        item for item in new_components if item["id"] == ROI_EXTRA_VIEW_ID
    )
    extra_component["component"] = "SQEmpty"

    with pytest.raises(ValueError, match="ROI 新图组件"):
        transform_roi_dashboard(new_components, new_canvas)


def test_core_transform_rejects_metric_layout_drift() -> None:
    components, canvas = _core_fixture()
    components[0]["sizeX"] = 17

    with pytest.raises(ValueError, match="核心看板.*布局"):
        transform_core_dashboard(components, canvas)


def test_validate_layout_rejects_overlapping_components() -> None:
    with pytest.raises(ValueError, match="重叠"):
        validate_layout([_component("one", 1, 1), _component("two", 10, 1)])


def test_validate_layout_rejects_fractional_grid_values() -> None:
    component = _component("one", 1, 1)
    component["x"] = 1.5

    with pytest.raises(ValueError, match="整数"):
        validate_layout([component])


def test_cli_modes_are_mutually_exclusive(monkeypatch) -> None:
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals.verify", lambda: {"verified": True}
    )

    with pytest.raises(SystemExit):
        main(["--apply", "--verify"])


def test_restore_backup_rejects_current_canvas_hash_mismatch(
    tmp_path, monkeypatch
) -> None:
    old_component = "[]"
    old_canvas = "{}"
    backup_payload = {
        "schema": "xiuxian-dashboard-visual-sync/v1",
        "dashboard_id": CORE_DASHBOARD_ID,
        "old_component_sha256": hashlib.sha256(old_component.encode()).hexdigest(),
        "new_component_sha256": hashlib.sha256("new-components".encode()).hexdigest(),
        "old_canvas_sha256": hashlib.sha256(old_canvas.encode()).hexdigest(),
        "new_canvas_sha256": hashlib.sha256("new-canvas".encode()).hexdigest(),
        "row": {
            "id": CORE_DASHBOARD_ID,
            "name": "核心看板",
            "tenant_id": TENANT_ID,
            "datasource": 6,
            "component_data": old_component,
            "canvas_view_info": old_canvas,
        },
    }
    backup = tmp_path / "backup.json"
    backup.write_text(json.dumps(backup_payload), encoding="utf-8")

    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals._read_dashboard_for_restore",
        lambda cursor, dashboard_id: {
            "id": dashboard_id,
            "component_data": "new-components",
            "canvas_view_info": "edited-after-migration",
        },
    )

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, *_):
            return None

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def cursor(self):
            return _Cursor()

        def rollback(self):
            return None

        def commit(self):
            return None

    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals.psycopg.connect",
        lambda **kwargs: _Connection(),
    )

    with pytest.raises(RuntimeError, match="新画布哈希"):
        restore_backup(backup)


def test_restore_backup_rejects_unknown_dashboard_before_connect(
    tmp_path, monkeypatch
) -> None:
    backup = tmp_path / "backup.json"
    backup.write_text(
        json.dumps(
            {
                "schema": "xiuxian-dashboard-visual-sync/v1",
                "dashboard_id": "not-a-target",
                "old_component_sha256": hashlib.sha256(b"[]").hexdigest(),
                "new_component_sha256": hashlib.sha256(b"new-components").hexdigest(),
                "old_canvas_sha256": hashlib.sha256(b"{}").hexdigest(),
                "new_canvas_sha256": hashlib.sha256(b"new-canvas").hexdigest(),
                "row": {
                    "id": "not-a-target",
                    "name": "其他看板",
                    "tenant_id": TENANT_ID,
                    "datasource": 6,
                    "component_data": "[]",
                    "canvas_view_info": "{}",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals.psycopg.connect",
        lambda **kwargs: pytest.fail("不应连接数据库"),
    )

    with pytest.raises(ValueError, match="目标看板"):
        restore_backup(backup)


def test_restore_backup_rejects_tampered_old_payload_before_connect(
    tmp_path, monkeypatch
) -> None:
    backup = tmp_path / "backup.json"
    backup.write_text(
        json.dumps(
            {
                "schema": "xiuxian-dashboard-visual-sync/v1",
                "dashboard_id": CORE_DASHBOARD_ID,
                "old_component_sha256": hashlib.sha256(b"original").hexdigest(),
                "new_component_sha256": hashlib.sha256(b"new-components").hexdigest(),
                "old_canvas_sha256": hashlib.sha256(b"{}").hexdigest(),
                "new_canvas_sha256": hashlib.sha256(b"new-canvas").hexdigest(),
                "row": {
                    "id": CORE_DASHBOARD_ID,
                    "name": "核心看板",
                    "tenant_id": TENANT_ID,
                    "datasource": 6,
                    "component_data": "tampered",
                    "canvas_view_info": "{}",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals.psycopg.connect",
        lambda **kwargs: pytest.fail("不应连接数据库"),
    )

    with pytest.raises(ValueError, match="旧组件哈希"):
        restore_backup(backup)


def test_load_targets_query_enforces_default_scope_and_identity() -> None:
    class _Cursor:
        def __init__(self) -> None:
            self.sql = ""
            self.params = None

        def execute(self, sql, params) -> None:
            self.sql = sql
            self.params = params

        def fetchall(self):
            return [
                {"id": dashboard_id, "name": name}
                for dashboard_id, name in {
                    CORE_DASHBOARD_ID: "核心看板",
                    "17531de20e5d439f9ddfb2eeececced5": "ROI看板",
                }.items()
            ]

    cursor = _Cursor()
    _load_targets(cursor, for_update=False)

    assert "t.scope = 'default'" in cursor.sql
    assert "d.tenant_id = %s" in cursor.sql
    assert "d.datasource = %s" in cursor.sql
    assert set(cursor.params[0]) == {
        CORE_DASHBOARD_ID,
        "17531de20e5d439f9ddfb2eeececced5",
    }
    assert cursor.params[1:] == (TENANT_ID, 6)


def test_backup_verification_rejects_preserved_sql_drift() -> None:
    assert hasattr(sync_module, "_verify_preserved_views")
    components, old_canvas = _core_fixture()
    _, new_canvas, _ = transform_core_dashboard(components, old_canvas)
    new_canvas["arpu"]["sql"] = "SELECT changed"

    with pytest.raises(RuntimeError, match="ARPU与ARPPU.*sql"):
        sync_module._verify_preserved_views(CORE_DASHBOARD_ID, old_canvas, new_canvas)


def test_backup_verification_rejects_flam_hash_drift() -> None:
    assert hasattr(sync_module, "_verify_row_against_backup")
    components, old_canvas = _core_fixture()
    new_components, new_canvas, _ = transform_core_dashboard(components, old_canvas)
    old_component_raw = json.dumps(
        components, ensure_ascii=False, separators=(",", ":")
    )
    old_canvas_raw = json.dumps(old_canvas, ensure_ascii=False, separators=(",", ":"))
    new_component_raw = json.dumps(
        new_components, ensure_ascii=False, separators=(",", ":")
    )
    new_canvas_raw = json.dumps(new_canvas, ensure_ascii=False, separators=(",", ":"))
    baseline = {"flam-core": {"component_sha256": "one", "canvas_sha256": "two"}}
    payload = {
        "schema": "xiuxian-dashboard-visual-sync/v2",
        "dashboard_id": CORE_DASHBOARD_ID,
        "old_component_sha256": hashlib.sha256(old_component_raw.encode()).hexdigest(),
        "new_component_sha256": hashlib.sha256(new_component_raw.encode()).hexdigest(),
        "old_canvas_sha256": hashlib.sha256(old_canvas_raw.encode()).hexdigest(),
        "new_canvas_sha256": hashlib.sha256(new_canvas_raw.encode()).hexdigest(),
        "flam_hashes": baseline,
        "row": {
            "id": CORE_DASHBOARD_ID,
            "name": "核心看板",
            "tenant_id": TENANT_ID,
            "datasource": 6,
            "component_data": old_component_raw,
            "canvas_view_info": old_canvas_raw,
        },
    }
    current_row = {
        "id": CORE_DASHBOARD_ID,
        "name": "核心看板",
        "tenant_id": TENANT_ID,
        "datasource": 6,
        "component_data": new_component_raw,
        "canvas_view_info": new_canvas_raw,
    }

    with pytest.raises(RuntimeError, match="flam 基准看板哈希"):
        sync_module._verify_row_against_backup(
            current_row,
            payload,
            {"flam-core": {"component_sha256": "changed", "canvas_sha256": "two"}},
        )


def test_backup_verification_accepts_partially_migrated_summary_title() -> None:
    components, old_canvas = _roi_fixture()
    old_canvas["summary"]["chart"]["title"] = "ROI数据总览"
    _, current_canvas, _ = transform_roi_dashboard(components, old_canvas)

    sync_module._verify_preserved_views(
        "17531de20e5d439f9ddfb2eeececced5", old_canvas, current_canvas
    )


class _RunCursor:
    def __init__(self, *, cas_rowcount: int = 1, readback=None) -> None:
        self.cas_rowcount = cas_rowcount
        self.rowcount = 1
        self.statements: list[str] = []
        self.readback = readback

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None) -> None:
        self.statements.append(sql)
        if "UPDATE public.core_dashboard" in sql:
            self.rowcount = self.cas_rowcount

    def fetchone(self):
        return self.readback


class _RunConnection:
    def __init__(self, cursor: _RunCursor) -> None:
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self._cursor

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _database_rows() -> list[dict]:
    return [
        {
            "id": dashboard_id,
            "name": name,
            "tenant_id": TENANT_ID,
            "datasource": 6,
            "component_data": "old-components",
            "canvas_view_info": "old-canvas",
        }
        for dashboard_id, name in {
            CORE_DASHBOARD_ID: "核心看板",
            "17531de20e5d439f9ddfb2eeececced5": "ROI看板",
        }.items()
    ]


def test_run_dry_run_never_updates_or_commits(monkeypatch) -> None:
    cursor = _RunCursor()
    connection = _RunConnection(cursor)
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals.psycopg.connect",
        lambda **kwargs: connection,
    )
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals._load_targets",
        lambda cursor, for_update: _database_rows(),
    )
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals._transform_row",
        lambda row: (
            row["component_data"],
            row["canvas_view_info"],
            {"changed": False},
        ),
    )

    result = run(apply=False)

    assert result["applied"] is False
    assert not any("UPDATE public.core_dashboard" in sql for sql in cursor.statements)
    assert connection.rolled_back is True
    assert connection.committed is False


def test_run_rolls_back_all_updates_when_cas_fails(monkeypatch, tmp_path) -> None:
    cursor = _RunCursor(cas_rowcount=0)
    connection = _RunConnection(cursor)
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals.psycopg.connect",
        lambda **kwargs: connection,
    )
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals._load_targets",
        lambda cursor, for_update: _database_rows(),
    )
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals._transform_row",
        lambda row: ("new-components", "new-canvas", {"changed": True}),
    )
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals._load_flam_hashes",
        lambda cursor, for_share: {"flam": "hash"},
    )
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals._backup",
        lambda row, new_component_raw, new_canvas_raw, flam_hashes: (
            tmp_path / f"{row['id']}.json"
        ),
    )

    with pytest.raises(RuntimeError, match="CAS 更新失败"):
        run(apply=True)

    assert connection.rolled_back is True
    assert connection.committed is False


def test_run_rolls_back_when_transaction_readback_differs(
    monkeypatch, tmp_path
) -> None:
    cursor = _RunCursor(
        readback={"component_data": "different", "canvas_view_info": "new-canvas"}
    )
    connection = _RunConnection(cursor)
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals.psycopg.connect",
        lambda **kwargs: connection,
    )
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals._load_targets",
        lambda cursor, for_update: _database_rows(),
    )
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals._transform_row",
        lambda row: ("new-components", "new-canvas", {"changed": True}),
    )
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals._load_flam_hashes",
        lambda cursor, for_share: {"flam": "hash"},
    )
    monkeypatch.setattr(
        "sync_xiuxian_dashboard_visuals._backup",
        lambda row, new_component_raw, new_canvas_raw, flam_hashes: (
            tmp_path / f"{row['id']}.json"
        ),
    )

    with pytest.raises(RuntimeError, match="事务内读回不一致"):
        run(apply=True)

    assert connection.rolled_back is True
    assert connection.committed is False
