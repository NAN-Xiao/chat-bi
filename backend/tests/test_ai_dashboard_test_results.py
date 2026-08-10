"""Validate the question-bank AI dashboard acceptance rule."""

from __future__ import annotations

import pytest

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


_TOOL_PATH = Path(__file__).resolve().parents[2] / "tools" / "validate_ai_dashboard_test_results.py"
_SPEC = spec_from_file_location("validate_ai_dashboard_test_results", _TOOL_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
classify_attempt = _MODULE.classify_attempt
validate_results = _MODULE.validate_results


def _attempt(**overrides):
    result = {
        "question_id": "q-1",
        "attempt_id": "a-1",
        "record_id": 101,
        "finish": True,
        "has_complete_sql": True,
        "has_sql_answer": True,
        "has_chart_answer": True,
        "chart_rendered": True,
    }
    result.update(overrides)
    return result


def test_success_requires_complete_sql_and_rendered_chart_in_same_attempt():
    result = classify_attempt(_attempt())

    assert result["status"] == "success"
    assert result["success"] is True
    assert result["chart_not_generated"] is False


def test_complete_sql_without_chart_is_a_collected_chart_failure():
    validated, chart_failures = validate_results([
        _attempt(has_chart_answer=False, chart_rendered=False),
    ])

    assert validated[0]["status"] == "chart_not_generated"
    assert validated[0]["success"] is False
    assert validated[0]["chart_not_generated"] is True
    assert len(chart_failures) == 1
    assert chart_failures[0]["question_id"] == "q-1"


def test_chart_config_without_visible_chart_is_collected_as_chart_failure():
    validated, chart_failures = validate_results([
        _attempt(has_chart_answer=True, chart_rendered=False),
    ])

    assert validated[0]["status"] == "chart_error"
    assert validated[0]["chart_not_generated"] is True
    assert len(chart_failures) == 1


def test_text_or_finished_without_complete_sql_is_not_success():
    result = classify_attempt(
        _attempt(has_complete_sql=False, has_sql_answer=False, has_chart_answer=False, chart_rendered=False)
    )

    assert result["status"] == "sql_not_generated"
    assert result["success"] is False
    assert result["chart_not_generated"] is False


def test_result_evidence_fields_are_required():
    with pytest.raises(ValueError, match="has_chart_answer"):
        validate_results([_attempt_without("has_chart_answer")])


def _attempt_without(field: str):
    result = _attempt()
    result.pop(field)
    return result
