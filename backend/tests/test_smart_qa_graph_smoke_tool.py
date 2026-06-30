"""
脚本说明：这个脚本是测试文件，用来验证对应功能在常见情况下能按预期工作。
"""
from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

import pytest


def _load_smoke_tool():
    """
    是什么：_load_smoke_tool 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试需要的数据找出来，整理成后面好用的样子。
    """
    tool_path = Path(__file__).resolve().parents[2] / "tools" / "smart_qa_graph_smoke.py"
    spec = importlib.util.spec_from_file_location("smart_qa_graph_smoke", tool_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_load_cases_accepts_custom_question_without_database() -> None:
    """
    是什么：test_load_cases_accepts_custom_question_without_database 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    smoke = _load_smoke_tool()

    cases = smoke._load_cases(
        "postgresql+psycopg://unused",
        None,
        datasource=2,
        question="show restricted revenue",
    )

    assert cases == [
        {
            "name": "custom",
            "source_record_id": None,
            "question": "show restricted revenue",
            "datasource": 2,
        }
    ]


def test_load_cases_requires_datasource_for_custom_question() -> None:
    """
    是什么：test_load_cases_requires_datasource_for_custom_question 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    smoke = _load_smoke_tool()

    with pytest.raises(ValueError, match="--datasource is required"):
        smoke._load_cases("postgresql+psycopg://unused", None, question="show revenue")


def test_smoke_failed_allows_expected_permission_error_without_finish() -> None:
    """
    是什么：test_smoke_failed_allows_expected_permission_error_without_finish 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    smoke = _load_smoke_tool()

    assert smoke._smoke_failed(
        {
            "finish": False,
            "step_violation": None,
            "expectation_violation": None,
        },
        "permission_denied",
    ) is False


def test_smoke_failed_rejects_unexpected_unfinished_result() -> None:
    """
    是什么：test_smoke_failed_rejects_unexpected_unfinished_result 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    smoke = _load_smoke_tool()

    assert smoke._smoke_failed(
        {
            "finish": False,
            "step_violation": None,
            "expectation_violation": None,
        },
        None,
    ) is True


def test_smoke_failed_rejects_step_or_expectation_violations() -> None:
    """
    是什么：test_smoke_failed_rejects_step_or_expectation_violations 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    smoke = _load_smoke_tool()

    assert smoke._smoke_failed(
        {
            "finish": True,
            "step_violation": "query_data should stop before chart events",
            "expectation_violation": None,
        },
        None,
    ) is True
    assert smoke._smoke_failed(
        {
            "finish": True,
            "step_violation": None,
            "expectation_violation": "expected error_type=permission_denied, got none",
        },
        "permission_denied",
    ) is True


def test_permission_fixture_legacy_alias_maps_to_column_deny() -> None:
    """
    是什么：test_permission_fixture_legacy_alias_maps_to_column_deny 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    smoke = _load_smoke_tool()

    assert smoke._normalize_permission_fixture(None, True) == smoke.PERMISSION_FIXTURE_COLUMN_DENY
    assert (
        smoke._normalize_permission_fixture(smoke.PERMISSION_FIXTURE_ROW_INVALID, True)
        == smoke.PERMISSION_FIXTURE_ROW_INVALID
    )


def test_row_invalid_permission_tree_uses_invalid_operator() -> None:
    """
    是什么：test_row_invalid_permission_tree_uses_invalid_operator 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    smoke = _load_smoke_tool()

    tree = smoke._row_invalid_expression_tree(123)

    assert tree["logic"] == "AND"
    assert tree["items"][0]["field_id"] == 123
    assert tree["items"][0]["term"] == "__codex_invalid_row_permission_term__"


def test_dynamic_assistant_payload_exposes_subquery_table() -> None:
    """
    是什么：test_dynamic_assistant_payload_exposes_subquery_table 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    smoke = _load_smoke_tool()

    payload = smoke._dynamic_assistant_datasource_payload(910001)
    datasource = payload["data"][0]
    table = datasource["tables"][0]

    assert payload["code"] == 0
    assert datasource["id"] == 910001
    assert datasource["type"] == "pg"
    assert table["name"] == smoke.DYNAMIC_ASSISTANT_DATASOURCE_TABLE
    assert "SELECT order_id" in table["sql"]


def test_assistant_certificate_header_is_url_quoted_base64_json() -> None:
    """
    是什么：test_assistant_certificate_header_is_url_quoted_base64_json 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    smoke = _load_smoke_tool()

    header = smoke._assistant_certificate_header([{"target": "header", "key": "X-Test", "value": "a b"}])
    decoded = base64.b64decode(header).decode("utf-8")

    assert decoded == "%5B%7B%22target%22%3A%20%22header%22%2C%20%22key%22%3A%20%22X-Test%22%2C%20%22value%22%3A%20%22a%20b%22%7D%5D"
    assert json.loads(smoke.urllib.parse.unquote(decoded)) == [
        {"target": "header", "key": "X-Test", "value": "a b"}
    ]
