from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def test_repair_roi_sql_formats_date_and_uses_chinese_aliases() -> None:
    from repair_flam_roi_dashboard import (
        CHINESE_FIELDS,
        LEGACY_SELECT_BLOCK,
        repair_sql,
    )

    repaired_sql = repair_sql(f"{LEGACY_SELECT_BLOCK}\nFROM source_table")

    assert "CAST(all_dt AS DATE)" in repaired_sql
    assert "'%Y-%m-%d'" in repaired_sql
    for field in CHINESE_FIELDS:
        assert f"`{field}`" in repaired_sql
    assert " AS ad_channel" not in repaired_sql
    assert " AS installs" not in repaired_sql


def test_repair_roi_sql_is_idempotent() -> None:
    from repair_flam_roi_dashboard import LEGACY_SELECT_BLOCK, repair_sql

    repaired_sql = repair_sql(f"{LEGACY_SELECT_BLOCK}\nFROM source_table")

    assert repair_sql(repaired_sql) == repaired_sql


def test_repair_roi_sql_rejects_unknown_projection() -> None:
    from repair_flam_roi_dashboard import repair_sql

    with pytest.raises(ValueError, match="未找到预期的 ROI_flame 输出字段"):
        repair_sql("SELECT all_dt FROM source_table")


def test_repair_chart_config_rebinds_all_fields_to_chinese_names() -> None:
    from repair_flam_roi_dashboard import CHINESE_FIELDS, repair_chart_config

    repaired_config = repair_chart_config(
        {
            "x": "all_dt",
            "y": ["campaign_name", "all_campaign_id", "ad_channel"],
            "series": "cpi",
            "columns": ["all_dt"],
            "pivot": {"enabled": False},
            "insight": {"enabled": False},
        }
    )

    assert repaired_config["x"] == "日期"
    assert repaired_config["y"] == list(CHINESE_FIELDS[1:])
    assert repaired_config["series"] == "单次安装成本"
    assert repaired_config["columns"] == ["日期"]
    assert repaired_config["pivot"] == {"enabled": False}
    assert repaired_config["insight"] == {"enabled": False}
