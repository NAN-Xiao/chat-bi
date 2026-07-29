from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session

from apps.dashboard.crud import dashboard_date_filter_migration as migration
from apps.dashboard.models.dashboard_date_filter_migration_model import CoreDashboardDateFilterMigrationAudit
from apps.dashboard.models.dashboard_model import CoreDashboard


TENANT_ID = 7482727237662281728
DASHBOARD_ID = "1752a05a80724b379438838bee516a46"
TARGET_CHART_ID = "2197205356986408960"


def _view(*, parameter_type: str = "yyyymmdd_number", valid_sql: bool = True) -> dict:
    sql = (
        "SELECT * FROM orders WHERE stat_date >= {{dashboard_start_yyyymmdd}} "
        "AND stat_date <= {{dashboard_end_yyyymmdd}}"
        if valid_sql
        else "SELECT * FROM orders"
    )
    return {
        "sql": sql,
        "pivot": {
            "date_parameter_type": parameter_type,
            "date_expression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
        },
    }


def _view_without_date_config() -> dict:
    return {
        "sql": (
            "SELECT * FROM orders WHERE stat_date >= {{dashboard_start_yyyymmdd}} "
            "AND stat_date <= {{dashboard_end_yyyymmdd}}"
        ),
        "pivot": {"enabled": False},
    }


def _dashboard(canvas: dict) -> CoreDashboard:
    return CoreDashboard(
        id=DASHBOARD_ID,
        tenant_id=TENANT_ID,
        name="日期筛选迁移测试",
        canvas_view_info=json.dumps(canvas, ensure_ascii=False, separators=(",", ":")),
    )


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    CoreDashboard.metadata.create_all(engine, tables=[CoreDashboard.__table__, CoreDashboardDateFilterMigrationAudit.__table__])
    with Session(engine) as value:
        yield value


def test_scan_classifies_automatic_approved_repair_and_manual_review(session: Session):
    canvas = {
        TARGET_CHART_ID: _view(),
        "automatic-chart": _view(),
        "manual-chart": _view(valid_sql=False),
    }
    session.add(_dashboard(canvas))
    session.commit()
    original_canvas = session.get(CoreDashboard, DASHBOARD_ID).canvas_view_info

    report = migration.scan_dashboard(
        session,
        tenant_id=TENANT_ID,
        dashboard_id=DASHBOARD_ID,
        manifest=migration.Manifest(
            tenant_id=TENANT_ID,
            dashboard_id=DASHBOARD_ID,
            charts={
                TARGET_CHART_ID: migration.TargetConfig(
                    parameter_type="yyyymmdd_number",
                    expression={"version": 1, "mode": "preset", "preset": "past_7_days"},
                )
            },
        ),
    )

    assert report.classifications[TARGET_CHART_ID] == "approved_repair"
    assert report.classifications["automatic-chart"] == "automatic"
    assert report.classifications["manual-chart"] == "manual_review"
    session.expire_all()
    assert session.get(CoreDashboard, DASHBOARD_ID).canvas_view_info == original_canvas


def test_scan_allows_explicit_manifest_repair_when_only_sql_tokens_remain(session: Session):
    session.add(_dashboard({TARGET_CHART_ID: _view_without_date_config()}))
    session.commit()
    manifest = migration.Manifest(
        tenant_id=TENANT_ID,
        dashboard_id=DASHBOARD_ID,
        charts={
            TARGET_CHART_ID: migration.TargetConfig(
                parameter_type="yyyymmdd_number",
                expression={"version": 1, "mode": "preset", "preset": "past_7_days"},
            )
        },
    )
    report = migration.scan_dashboard(
        session,
        tenant_id=TENANT_ID,
        dashboard_id=DASHBOARD_ID,
        manifest=manifest,
    )
    assert report.classifications[TARGET_CHART_ID] == "approved_repair"
    assert report.target_configs[TARGET_CHART_ID] == manifest.charts[TARGET_CHART_ID]
    assert migration.count_v1(
        session,
        tenant_id=TENANT_ID,
        dashboard_id=DASHBOARD_ID,
        manifest=manifest,
    ) == 0


def test_apply_is_idempotent_and_records_complete_original_canvas(session: Session):
    original_canvas = {TARGET_CHART_ID: _view()}
    dashboard = _dashboard(original_canvas)
    session.add(dashboard)
    session.commit()
    manifest = migration.Manifest(
        tenant_id=TENANT_ID,
        dashboard_id=DASHBOARD_ID,
        charts={
            TARGET_CHART_ID: migration.TargetConfig(
                parameter_type="yyyymmdd_number",
                expression={"version": 1, "mode": "preset", "preset": "past_7_days"},
            )
        },
    )

    first = migration.apply_dashboard(
        session, tenant_id=TENANT_ID, dashboard_id=DASHBOARD_ID, manifest=manifest, batch_id="batch-1"
    )
    second = migration.apply_dashboard(
        session, tenant_id=TENANT_ID, dashboard_id=DASHBOARD_ID, manifest=manifest, batch_id="batch-1"
    )

    assert first.applied is True
    assert second.idempotent is True
    audit = migration.get_audit(session, batch_id="batch-1", dashboard_id=DASHBOARD_ID)
    assert audit is not None
    assert audit.original_canvas == json.dumps(original_canvas, ensure_ascii=False, separators=(",", ":"))
    assert json.loads(audit.chart_ids) == [TARGET_CHART_ID]
    migrated = json.loads(session.get(CoreDashboard, DASHBOARD_ID).canvas_view_info)
    migrated_view = migrated[TARGET_CHART_ID]
    assert migrated_view["configVersion"] == 2
    assert migrated_view["dateFilter"] == {
        "enabled": True,
        "parameterType": "yyyymmdd_number",
        "expression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
    }
    assert "date_filter" not in migrated_view
    assert "date_parameter_type" not in migrated_view["pivot"]
    assert "date_expression" not in migrated_view["pivot"]


def test_apply_rejects_compare_and_swap_conflict(session, monkeypatch):
    session.add(_dashboard({TARGET_CHART_ID: _view()}))
    session.commit()
    manifest = migration.Manifest(
        tenant_id=TENANT_ID,
        dashboard_id=DASHBOARD_ID,
        charts={TARGET_CHART_ID: migration.TargetConfig("yyyymmdd_number", {"version": 1, "mode": "preset", "preset": "past_7_days"})},
    )
    original = migration._update_canvas_cas

    def conflict(*args, **kwargs):
        return 0

    monkeypatch.setattr(migration, "_update_canvas_cas", conflict)
    with pytest.raises(migration.CompareAndSwapConflict):
        migration.apply_dashboard(session, tenant_id=TENANT_ID, dashboard_id=DASHBOARD_ID, manifest=manifest, batch_id="batch-1")
    monkeypatch.setattr(migration, "_update_canvas_cas", original)


def test_rollback_rejects_changed_current_canvas(session):
    session.add(_dashboard({TARGET_CHART_ID: _view()}))
    session.commit()
    manifest = migration.Manifest(
        tenant_id=TENANT_ID,
        dashboard_id=DASHBOARD_ID,
        charts={TARGET_CHART_ID: migration.TargetConfig("yyyymmdd_number", {"version": 1, "mode": "preset", "preset": "past_7_days"})},
    )
    migration.apply_dashboard(session, tenant_id=TENANT_ID, dashboard_id=DASHBOARD_ID, manifest=manifest, batch_id="batch-1")
    dashboard = session.get(CoreDashboard, DASHBOARD_ID)
    assert dashboard is not None
    dashboard.canvas_view_info = "{}"
    session.add(dashboard)
    session.commit()

    with pytest.raises(migration.RollbackConflict):
        migration.rollback_dashboard(session, batch_id="batch-1", dashboard_id=DASHBOARD_ID)


def test_manifest_exactly_matches_required_dashboard_and_charts():
    manifest = migration.load_manifest(migration.default_manifest_path())

    assert manifest.tenant_id == TENANT_ID
    assert manifest.dashboard_id == DASHBOARD_ID
    assert set(manifest.charts) == {"2197205356986408960", "2197218114511478784"}
    assert {item.parameter_type for item in manifest.charts.values()} == {"yyyymmdd_number"}
    assert {item.expression["preset"] for item in manifest.charts.values()} == {"past_7_days"}
