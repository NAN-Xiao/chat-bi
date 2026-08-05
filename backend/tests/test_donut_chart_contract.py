"""验证独立环形图类型的后端协议和选择边界。"""
from __future__ import annotations

from pathlib import Path

from apps.analysis_assistant.api import analysis_assistant as analysis_api
from common.utils.chart_config import CHART_TYPES as COMMON_CHART_TYPES


def _result() -> dict:
    return {
        "fields": ["category", "amount"],
        "data": [
            {"category": "A", "amount": 30},
            {"category": "B", "amount": 70},
        ],
    }


def test_donut_is_a_supported_chart_type() -> None:
    assert "donut" in COMMON_CHART_TYPES
    assert "donut" in analysis_api.CHART_TYPES


def test_analysis_assistant_builds_explicit_donut_with_y_and_series() -> None:
    chart = analysis_api._build_chart_config(
        {
            "chart_type": "donut",
            "title": "分类占比",
            "x": "category",
            "y": "amount",
            "_user_question": "用环形图展示分类占比",
        },
        _result(),
    )

    assert chart["type"] == "donut"
    assert chart["axis"]["y"] == {"value": "amount"}
    assert chart["axis"]["series"] == {"value": "category"}


def test_analysis_assistant_rejects_implicit_donut_selection() -> None:
    chart = analysis_api._build_chart_config(
        {
            "chart_type": "donut",
            "title": "分类占比",
            "x": "category",
            "y": "amount",
            "_user_question": "展示分类占比",
        },
        _result(),
    )

    assert chart["type"] != "donut"


def test_template_limits_donut_to_explicit_user_requests() -> None:
    template = (Path(__file__).resolve().parents[1] / "templates" / "template.yaml").read_text(
        encoding="utf-8"
    )

    assert "环形图(donut)" in template
    assert "仅当用户明确要求环形图、圆环图或 donut 时" in template
    assert "不得因为占比、结构、构成或分布自动选择 donut" in template
