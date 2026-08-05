"""First Zombie tracking dictionary semantic regression tests."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def test_tracking_dictionary_separates_transactions_and_removes_unverified_ext() -> None:
    import seed_flam_first_zombie_tracking_dictionary as tracking

    groups = {item["group_key"]: item for item in tracking.EVENT_GROUPS}
    field_names = {item["field_name"] for item in tracking.FIELDS}

    assert tracking.TRACKING_CONFIG["event_name_mappings"] == tracking.DEFAULT_EVENT_MAPPINGS
    assert groups["payment_transaction"]["event_names"] == ["ServerPayLog"]
    assert "ServerPayLog" not in groups["payment_process_event"]["event_names"]
    assert len(groups) == 13
    assert {
        "personal.money",
        "personal.orderId",
        "personal.productid",
        "personal.ed_ccu",
        "personal.ed_buildingId",
        "personal.ed_mainBuildingLevel",
        "personal.ed_myTeamBattlePower",
        "pay.firstpaytime",
    } <= field_names
    assert not (tracking.LEGACY_UNVERIFIED_EXT_FIELDS & field_names)
    assert "待补充字段映射" in tracking.TRACKING_CONFIG["sql_rules"]


def test_tracking_dictionary_upserts_are_scoped_by_tenant_and_datasource() -> None:
    seed_script = ROOT / "tools" / "seed_flam_first_zombie_tracking_dictionary.py"
    content = seed_script.read_text(encoding="utf-8")

    assert "ON CONFLICT (tenant_id, datasource_id)" in content
    assert "ON CONFLICT (tenant_id, datasource_id, table_name)" in content
    assert "ON CONFLICT (tenant_id, datasource_id, table_name, field_name)" in content
    assert "AND datasource_id = %s" in content
    assert "extra_properties = COALESCE(sys_tenant_tracking_field.extra_properties" in content
    assert "|| EXCLUDED.extra_properties" in content


def test_tracking_dictionary_seed_does_not_overwrite_user_dictionary_or_groups() -> None:
    seed_script = ROOT / "tools" / "seed_flam_first_zombie_tracking_dictionary.py"
    content = seed_script.read_text(encoding="utf-8")

    assert "event_name_mappings = EXCLUDED.event_name_mappings" not in content
    assert "ON CONFLICT (tenant_id, datasource_id, group_key) DO NOTHING" in content
    assert "value_mappings = EXCLUDED.value_mappings" not in content


def test_tracking_dictionary_keeps_events_without_properties() -> None:
    import seed_flam_first_zombie_tracking_dictionary as tracking

    events = {item["event_name"]: item for item in tracking.DEFAULT_EVENT_MAPPINGS}

    assert events["UserActive"]["properties"] == []
    assert events["UserRegister"]["properties"] == []


def test_tracking_dictionary_exposes_realtime_event_table() -> None:
    import seed_flam_first_zombie_tracking_dictionary as tracking

    table_names = {item["table_name"] for item in tracking.TABLES}
    realtime_fields = {
        item["field_name"]
        for item in tracking.FIELDS
        if item["table_name"] == "event_realtime"
    }
    realtime_roles = {
        (item["role"], item["field"])
        for item in tracking.TRACKING_CONFIG["field_role_mappings"]
        if item["table"] == "event_realtime"
    }

    assert "event_realtime" in table_names
    assert {"uid", "event", "time", "dt", "prod", "personal"} <= realtime_fields
    assert {
        ("subject_id", "uid"),
        ("event_name", "event"),
        ("event_time", "time"),
        ("partition_date", "dt"),
    } <= realtime_roles

    fields = {
        (item["table_name"], item["field_name"]): item
        for item in tracking.FIELDS
    }
    for table_name in ("event", "event_realtime", "user"):
        assert fields[(table_name, "dt")]["extra_properties"] == {
            "encoding": "yyyyMMdd"
        }
    for table_name in ("event", "event_realtime"):
        assert fields[(table_name, "time")]["extra_properties"] == {
            "encoding": "epoch_milliseconds"
        }


def test_tracking_dictionary_merges_only_missing_events() -> None:
    import seed_flam_first_zombie_tracking_dictionary as tracking

    existing = [
        {
            "event_name": "UserActive",
            "event_display_name": "用户维护的活跃事件",
            "properties": [{"property_name": "custom.value"}],
        }
    ]
    defaults = [
        {"event_name": "UserActive", "properties": []},
        {"event_name": "UserRegister", "properties": []},
    ]

    merged, inserted = tracking.merge_missing_event_mappings(existing, defaults)

    assert inserted == 1
    assert merged[0] == existing[0]
    assert merged[1] == {"event_name": "UserRegister", "properties": []}
    assert existing == [
        {
            "event_name": "UserActive",
            "event_display_name": "用户维护的活跃事件",
            "properties": [{"property_name": "custom.value"}],
        }
    ]


def test_tracking_dictionary_event_merge_is_idempotent() -> None:
    import seed_flam_first_zombie_tracking_dictionary as tracking

    first, first_inserted = tracking.merge_missing_event_mappings(
        [], tracking.DEFAULT_EVENT_MAPPINGS
    )
    second, second_inserted = tracking.merge_missing_event_mappings(
        first, tracking.DEFAULT_EVENT_MAPPINGS
    )

    assert first_inserted == len(tracking.DEFAULT_EVENT_MAPPINGS)
    assert second_inserted == 0
    assert second == first


def test_tracking_dictionary_default_groups_reference_existing_events() -> None:
    import seed_flam_first_zombie_tracking_dictionary as tracking

    tracking.validate_event_group_defaults(
        tracking.EVENT_GROUPS,
        tracking.DEFAULT_EVENT_MAPPINGS,
    )


def test_tracking_dictionary_event_repair_is_scoped() -> None:
    content = (
        ROOT / "tools" / "seed_flam_first_zombie_tracking_dictionary.py"
    ).read_text(encoding="utf-8")

    assert "WHERE tenant_id = %s AND datasource_id = %s" in content
    assert "event_name_mappings = EXCLUDED.event_name_mappings" not in content
    assert "ensure_default_event_mappings(cur, now)" in content


def test_event_group_defaults_require_explicit_validated_seed() -> None:
    import seed_flam_first_zombie_tracking_dictionary as tracking

    assert inspect.signature(tracking.main).parameters["seed_event_groups"].default is False
    with pytest.raises(RuntimeError, match="UserRegister"):
        tracking.validate_event_group_defaults(
            tracking.EVENT_GROUPS,
            [{"event_name": "ServerPayLog"}],
        )


def test_tracking_seed_bumps_tracking_and_schema_epochs_before_commit(monkeypatch) -> None:
    import seed_flam_first_zombie_tracking_dictionary as tracking

    events: list[object] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, parameters):
            events.append(("execute", str(statement), parameters))

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            events.append("commit")

    monkeypatch.setattr(tracking, "apply_chart_builder_expressions", lambda: None)
    monkeypatch.setattr(tracking, "upsert_config", lambda *_args: None)
    monkeypatch.setattr(tracking, "ensure_default_event_mappings", lambda *_args: 0)
    monkeypatch.setattr(tracking, "upsert_event_groups", lambda *_args: 0)
    monkeypatch.setattr(tracking, "upsert_tables", lambda *_args: None)
    monkeypatch.setattr(tracking, "upsert_fields", lambda *_args: None)
    monkeypatch.setattr(tracking, "delete_stale_fields", lambda *_args: 0)
    monkeypatch.setattr(tracking, "upsert_schema_comments", lambda *_args: (0, 0))
    monkeypatch.setattr(tracking.psycopg, "connect", lambda **_kwargs: FakeConnection())

    tracking.main()

    epoch_calls = [
        item for item in events
        if isinstance(item, tuple) and "INSERT INTO semantic_scope_epoch" in item[1]
    ]
    assert [call[2] for call in epoch_calls] == [
        ("TRACKING", tracking.TENANT_ID, tracking.DATASOURCE_ID, None),
        ("SCHEMA", tracking.TENANT_ID, tracking.DATASOURCE_ID, None),
    ]
    assert all(events.index(call) < events.index("commit") for call in epoch_calls)
