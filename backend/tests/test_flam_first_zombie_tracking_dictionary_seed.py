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
