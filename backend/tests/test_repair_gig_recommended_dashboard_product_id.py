"""gig 推荐看板产品条件修复工具测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import repair_gig_recommended_dashboard_product_id as repair  # noqa: E402


def test_replace_only_changes_old_prod_literal_predicates() -> None:
    sql = """
    SELECT e.uid
    FROM event AS e
    JOIN user AS u ON u.uid = e.uid AND u.prod = e.prod
    WHERE e.prod = 110000047 OR 110000038 = u.prod
    """

    rewritten, counts = repair._replace_old_product_predicates(sql)

    assert counts == {"110000047": 1, "110000038": 1}
    assert "e.prod = 110000036" in rewritten
    assert "110000036 = u.prod" in rewritten
    assert "u.prod = e.prod" in rewritten
    assert repair._literal_product_predicates(rewritten) == {"110000036": 2}


def test_replace_rejects_old_literal_outside_prod_predicate() -> None:
    with pytest.raises(RuntimeError, match="旧产品常量不全是 prod 等值条件"):
        repair._replace_old_product_predicates(
            "SELECT * FROM event WHERE prod = 110000047 AND uid = 110000038"
        )


def test_add_missing_filter_uses_requested_alias_and_preserves_grain() -> None:
    sql = """SELECT e.event, COUNT(*) AS total
FROM event AS e
WHERE e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
GROUP BY e.event
ORDER BY total DESC"""

    rewritten = repair._add_missing_product_filter(sql, column_sql="e.prod")

    assert "AND e.prod = 110000036\nGROUP BY e.event" in rewritten
    assert repair._literal_product_predicates(rewritten) == {"110000036": 1}


def test_clear_result_snapshot_keeps_chart_configuration() -> None:
    view = {
        "chart": {"xAxis": [{"value": "日期"}]},
        "data": {
            "data": [{"日期": "20260813"}],
            "fields": ["日期"],
            "source_data": [{"日期": "20260813"}],
            "snapshotRefreshedAt": 123,
        },
        "fields": ["日期"],
        "snapshotRefreshedAt": 123,
    }
    sql_config = {"sql": "select 1", "lastResult": {"data": [{"日期": "20260813"}]}}

    repair._clear_result_snapshot(view, sql_config)

    assert view["chart"] == {"xAxis": [{"value": "日期"}]}
    assert view["data"]["data"] == []
    assert view["data"]["fields"] == []
    assert "source_data" not in view["data"]
    assert view["snapshotRefreshedAt"] == 0
    assert view["data"]["snapshotRefreshedAt"] == 0
    assert "lastResult" not in sql_config


def test_configure_profile_requires_complete_scope() -> None:
    with pytest.raises(RuntimeError, match="修复配置缺少字段"):
        repair.configure_profile({"tenant_id": 1})
