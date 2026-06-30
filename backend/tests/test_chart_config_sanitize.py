"""
脚本说明：这个脚本是测试文件，用来验证对应功能在常见情况下能按预期工作。
"""
from __future__ import annotations

from common.utils.chart_config import sanitize_chart_display_names


def test_sanitize_chart_display_names_keeps_explicit_display_labels() -> None:
    """
    是什么：test_sanitize_chart_display_names_keeps_explicit_display_labels 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
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
