"""验证四空间 ROI 看板跨库限定名修复。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import repair_clone_roi_dashboard_namespaces as repair  # noqa: E402


def test_rewrite_removes_only_known_database_qualifiers() -> None:
    original = """
    SELECT r.dt, SUM(r.revenue) AS revenue
    FROM first_zombie.roi_midrevenue_channel_type_utc8 r
    JOIN `xtxdj`.`ad_spending` a ON a.dt = r.dt AND a.prod = r.prod
    WHERE r.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND r.prod = 110000039
    GROUP BY r.dt
    """

    rewritten, counts = repair.rewrite_sql_namespaces(original, "mysql")

    assert "first_zombie." not in rewritten
    assert "`xtxdj`." not in rewritten
    assert "roi_midrevenue_channel_type_utc8 r" in rewritten
    assert "`ad_spending` a" in rewritten
    assert "110000039" in rewritten
    assert "{{dashboard_start_yyyymmdd}}" in rewritten
    assert counts == {"first_zombie": 1, "xtxdj": 1}


def test_rewrite_rejects_unexpected_database_qualifier() -> None:
    with pytest.raises(RuntimeError, match="非预期限定表"):
        repair.rewrite_sql_namespaces("SELECT * FROM legacy.orders", "mysql")


def test_rewrite_is_idempotent_after_cleanup() -> None:
    sql = "SELECT * FROM roi_midrevenue_channel_type WHERE prod = 110000036"

    rewritten, counts = repair.rewrite_sql_namespaces(sql, "mysql")

    assert rewritten == sql
    assert counts == {}


def test_clear_result_snapshot_preserves_chart_configuration() -> None:
    view = {
        "chart": {"xAxis": [{"value": "日期"}]},
        "data": {"data": [{"日期": "20260816"}], "fields": ["日期"]},
        "fields": ["日期"],
    }
    sql_config = {"sql": "SELECT 1", "lastResult": {"data": [1]}}

    repair._clear_result_snapshot(view, sql_config)

    assert view["chart"] == {"xAxis": [{"value": "日期"}]}
    assert view["data"]["data"] == []
    assert view["fields"] == []
    assert "lastResult" not in sql_config


def test_profiles_cover_each_workspace_and_roi_datasource_once() -> None:
    profiles = list(repair.PROFILES.values())

    assert set(repair.PROFILES) == {"gig", "lds", "j2000", "unicorn"}
    assert len({profile["tenant_id"] for profile in profiles}) == 4
    assert {profile["asset_datasource"] for profile in profiles} == {9, 10, 11, 12}
    assert {profile["roi_datasource"] for profile in profiles} == {13, 14, 15, 16}
    assert len({profile["dashboard_id"] for profile in profiles}) == 4
