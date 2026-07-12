"""First Zombie tracking dictionary semantic regression tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def test_tracking_dictionary_separates_transactions_and_removes_unverified_ext() -> None:
    import seed_flam_first_zombie_tracking_dictionary as tracking

    mappings = {item["metric"]: item for item in tracking.TRACKING_CONFIG["event_name_mappings"]}
    field_names = {item["field_name"] for item in tracking.FIELDS}

    assert mappings["payment_transaction"]["events"] == ["ServerPayLog"]
    transaction_properties = {
        item["property_name"]: item
        for item in mappings["payment_transaction"]["properties"]
    }
    assert transaction_properties["personal.money"] == {
        "property_name": "personal.money",
        "property_display_name": "充值金额",
        "property_type": "number",
        "source_field": "personal",
        "json_path": "$.money",
    }
    assert transaction_properties["uid"] == {
        "property_name": "uid",
        "property_display_name": "用户 ID",
        "property_type": "identifier",
    }
    assert "ServerPayLog" not in mappings["payment_process_event"]["events"]
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
