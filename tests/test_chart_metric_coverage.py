from apps.chat.task.llm import _ensure_chart_covers_metric_fields


def test_multi_metric_chart_with_single_bound_metric_falls_back_to_table():
    chart = {
        "type": "column",
        "title": "最近 7 天渠道指标对比",
        "axis": {
            "x": {"name": "渠道", "value": "channel"},
            "y": [{"name": "收入", "value": "revenue"}],
        },
    }
    result = _ensure_chart_covers_metric_fields(
        chart,
        ["channel", "dau", "revenue", "payer_count", "payer_rate", "arpu"],
        [
            {
                "channel": "tiktok_ads",
                "dau": 65.57,
                "revenue": 750.8,
                "payer_count": 11,
                "payer_rate": 3.53,
                "arpu": 2.41,
            }
        ],
    )

    assert result["type"] == "table"
    assert [column["value"] for column in result["columns"]] == [
        "channel",
        "dau",
        "revenue",
        "payer_count",
        "payer_rate",
        "arpu",
    ]


def test_single_metric_chart_is_kept():
    chart = {
        "type": "column",
        "title": "最近 7 天渠道收入对比",
        "axis": {
            "x": {"name": "渠道", "value": "channel"},
            "y": [{"name": "收入", "value": "revenue"}],
        },
    }
    result = _ensure_chart_covers_metric_fields(
        chart,
        ["channel", "revenue"],
        [{"channel": "tiktok_ads", "revenue": 750.8}],
    )

    assert result == chart


def test_multi_quota_chart_covering_all_metrics_is_kept():
    chart = {
        "type": "column",
        "title": "指标对比",
        "axis": {
            "x": {"name": "渠道", "value": "channel"},
            "y": [
                {"name": "DAU", "value": "dau"},
                {"name": "收入", "value": "revenue"},
            ],
            "multi-quota": {"name": "指标类型", "value": ["dau", "revenue"]},
        },
    }
    result = _ensure_chart_covers_metric_fields(
        chart,
        ["channel", "dau", "revenue"],
        [{"channel": "tiktok_ads", "dau": 65.57, "revenue": 750.8}],
    )

    assert result == chart


def test_rate_chart_with_supporting_count_fields_is_kept():
    chart = {
        "type": "column",
        "title": "最近 30 天新增用户留存率",
        "axis": {
            "x": {"name": "留存周期", "value": "lifecycle_day"},
            "y": [{"name": "留存率", "value": "retention_pct"}],
        },
    }
    result = _ensure_chart_covers_metric_fields(
        chart,
        ["lifecycle_day", "day_index", "cohort_size", "retained_users", "retention_pct"],
        [
            {
                "lifecycle_day": "D1",
                "day_index": 1,
                "cohort_size": 2639,
                "retained_users": 1143,
                "retention_pct": 43.31,
            }
        ],
    )

    assert result == chart
