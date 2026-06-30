"""
脚本说明：这个脚本是测试文件，用来验证对应功能在常见情况下能按预期工作。
"""
from __future__ import annotations

import json

import pytest

from apps.chat.task.llm import _parse_sql_answer_data


def test_parse_sql_answer_data_accepts_strict_json() -> None:
    """
    是什么：test_parse_sql_answer_data_accepts_strict_json 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    payload = {
        "success": True,
        "sql": 'SELECT "p"."channel" AS "渠道"',
        "tables": ["dim_player"],
        "chart_type": "pie",
        "brief": "渠道分布",
    }

    data = _parse_sql_answer_data(json.dumps(payload, ensure_ascii=False))

    assert data["success"] is True
    assert data["sql"] == 'SELECT "p"."channel" AS "渠道"'
    assert data["tables"] == ["dim_player"]
    assert data["chart_type"] == "pie"
    assert data["brief"] == "渠道分布"


def test_parse_sql_answer_data_recovers_postgres_identifier_quotes() -> None:
    """
    是什么：test_parse_sql_answer_data_recovers_postgres_identifier_quotes 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    llm_answer = (
        '{"success":true,"sql":"SELECT \\"p"."channel\\" AS \\"渠道\\", '
        'SUM(\\"fp\\".\\"net_revenue_usd\\") AS \\"净收入\\" '
        'FROM \\"public\\".\\"dim_player\\" \\"p\\" '
        'JOIN \\"public\\".\\"fact_payments\\" \\"fp\\" '
        'ON \\"p\\".\\"player_id\\" = \\"fp\\".\\"player_id\\" '
        'WHERE \\"p\\".\\"install_date\\" >= DATE \'2026-05-29\' '
        'AND \\"p\\".\\"install_date\\" <= DATE \'2026-06-28\' '
        'AND \\"fp\\".\\"payment_status\\" = \'success\' '
        'AND \\"fp\\".\\"net_revenue_usd\\" > 0 '
        'GROUP BY \\"p\\".\\"channel\\" ORDER BY \\"净收入\\" DESC LIMIT 1000",'
        '"tables":["dim_player","fact_payments"],"chart-type":"pie","brief":"近一月新增用户付费渠道分布"}'
    )

    data = _parse_sql_answer_data(llm_answer)

    assert data["success"] is True
    assert '"p"."channel"' in data["sql"]
    assert '"fp"."net_revenue_usd"' in data["sql"]
    assert data["tables"] == ["dim_player", "fact_payments"]
    assert data["chart-type"] == "pie"
    assert data["brief"] == "近一月新增用户付费渠道分布"


def test_parse_sql_answer_data_rejects_non_json_text() -> None:
    """
    是什么：test_parse_sql_answer_data_rejects_non_json_text 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    with pytest.raises(ValueError):
        _parse_sql_answer_data("SELECT 1")
