from __future__ import annotations

from apps.chat.task.llm import _ensure_chart_covers_metric_fields


def test_time_series_rate_chart_keeps_line_when_counts_are_supporting_metrics() -> None:
    """
    是什么：test_time_series_rate_chart_keeps_line_when_counts_are_supporting_metrics 是 backend/tests/test_chart_config_postprocess.py 中的同步测试函数。
    谁调用：由 pytest 测试运行器收集并执行。
    做了什么：构造测试场景的测试条件，断言实际结果符合预期。
    """
    fields = [
        "新增日期",
        "新增用户数",
        "D1 留存人数",
        "D1 留存率",
        "D7 留存人数",
        "D7 留存率",
        "D14 留存人数",
        "D14 留存率",
    ]
    rows = [
        {
            "新增日期": "2026-06-01",
            "新增用户数": 120,
            "D1 留存人数": 66,
            "D1 留存率": 0.55,
            "D7 留存人数": 31,
            "D7 留存率": 0.2583,
            "D14 留存人数": 18,
            "D14 留存率": 0.15,
        },
        {
            "新增日期": "2026-06-02",
            "新增用户数": 140,
            "D1 留存人数": 73,
            "D1 留存率": 0.5214,
            "D7 留存人数": 35,
            "D7 留存率": 0.25,
            "D14 留存人数": 20,
            "D14 留存率": 0.1429,
        },
    ]
    chart = {
        "type": "line",
        "title": "留存率趋势",
        "axis": {
            "x": {"value": "新增日期"},
            "y": [
                {"value": "D1 留存率"},
                {"value": "D7 留存率"},
                {"value": "D14 留存率"},
            ],
            "multi-quota": {"value": ["D1 留存率", "D7 留存率", "D14 留存率"]},
        },
    }

    checked_chart = _ensure_chart_covers_metric_fields(chart, fields, rows)

    assert checked_chart["type"] == "line"
    assert [item["value"] for item in checked_chart["axis"]["y"]] == [
        "D1 留存率",
        "D7 留存率",
        "D14 留存率",
    ]


def test_chart_downgrades_to_table_when_important_metric_is_missing() -> None:
    """
    是什么：test_chart_downgrades_to_table_when_important_metric_is_missing 是 backend/tests/test_chart_config_postprocess.py 中的同步测试函数。
    谁调用：由 pytest 测试运行器收集并执行。
    做了什么：构造测试场景的测试条件，断言实际结果符合预期。
    """
    fields = ["日期", "收入", "成本", "利润"]
    rows = [
        {"日期": "2026-06-01", "收入": 1000, "成本": 650, "利润": 350},
        {"日期": "2026-06-02", "收入": 1200, "成本": 700, "利润": 500},
    ]
    chart = {
        "type": "line",
        "title": "收入趋势",
        "axis": {
            "x": {"value": "日期"},
            "y": [{"value": "收入"}],
        },
    }

    checked_chart = _ensure_chart_covers_metric_fields(chart, fields, rows)

    assert checked_chart["type"] == "table"
    assert [column["value"] for column in checked_chart["columns"]] == fields
