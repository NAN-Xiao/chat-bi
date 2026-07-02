"""
脚本说明：这个脚本是测试文件，用来验证对应功能在常见情况下能按预期工作。
"""
from __future__ import annotations

from apps.chat.task.llm import _ensure_chart_covers_metric_fields, _filter_chart_bindings_to_result_fields


def test_time_series_rate_chart_keeps_line_when_counts_are_supporting_metrics() -> None:
    """
    是什么：test_time_series_rate_chart_keeps_line_when_counts_are_supporting_metrics 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
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
    是什么：test_chart_downgrades_to_table_when_important_metric_is_missing 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
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


def test_chart_filters_axis_fields_missing_from_result() -> None:
    """
    是什么：图表模型引用了已被业务校验裁掉的字段时，保存前应删除无效绑定。
    """
    fields = ["日期", "DAU", "PDAU"]
    chart = {
        "type": "line",
        "title": "DAU、PDAU 与飞船升级触发用户趋势",
        "axis": {
            "x": {"value": "日期"},
            "y": [
                {"value": "DAU"},
                {"value": "PDAU"},
                {"value": "飞船升级完成触发用户数"},
            ],
            "multi-quota": {"value": ["DAU", "PDAU", "飞船升级完成触发用户数"]},
        },
    }

    checked_chart = _filter_chart_bindings_to_result_fields(chart, fields)

    assert checked_chart["type"] == "line"
    assert [item["value"] for item in checked_chart["axis"]["y"]] == ["DAU", "PDAU"]
    assert checked_chart["axis"]["multi-quota"]["value"] == ["DAU", "PDAU"]
