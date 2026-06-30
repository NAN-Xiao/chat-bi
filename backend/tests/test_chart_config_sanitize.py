from __future__ import annotations

from common.utils.chart_config import sanitize_chart_display_names


def test_sanitize_chart_display_names_keeps_explicit_display_labels() -> None:
    """
    是什么：test_sanitize_chart_display_names_keeps_explicit_display_labels 是 backend/tests/test_chart_config_sanitize.py 中的同步测试函数。
    谁调用：由 pytest 测试运行器收集并执行。
    做了什么：构造测试场景的测试条件，断言实际结果符合预期。
    """
    canvas = {
        "view-1": {
            "chart": {
                "type": "line",
                "xAxis": [{"value": "cohort_date", "name": "日期"}],
                "yAxis": [
                    {"value": "d1_retention_pct", "name": "次日留存率"},
                    {"value": "new_users", "name": "new_users"},
                ],
                "columns": [{"value": "cohort_date", "name": "日期"}],
                "multiQuotaName": "指标",
            }
        }
    }

    sanitized = sanitize_chart_display_names(canvas)
    chart = sanitized["view-1"]["chart"]

    assert chart["xAxis"][0] == {"value": "cohort_date", "name": "日期"}
    assert chart["yAxis"][0] == {"value": "d1_retention_pct", "name": "次日留存率"}
    assert chart["columns"][0] == {"value": "cohort_date", "name": "日期"}
    assert chart["yAxis"][1] == {"value": "new_users"}
    assert chart["multiQuotaName"] == "指标"
