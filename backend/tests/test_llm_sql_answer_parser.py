"""
脚本说明：这个脚本是测试文件，用来验证对应功能在常见情况下能按预期工作。
"""
from __future__ import annotations

import json

import pytest

from apps.chat.task.llm import _data_skill_sql_validation_error, _parse_sql_answer_data


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


def test_data_skill_sql_validation_rejects_flam_ltv_snapshot_offset_mismatch() -> None:
    """
    是什么：test_data_skill_sql_validation_rejects_flam_ltv_snapshot_offset_mismatch 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    data_skill = """
<!-- data-skill-sql-validation:{
  "match":["ltv","首日 LTV","3 日 LTV","7 日 LTV"],
  "forbidden_sql_patterns":[
    "DATE_ADD\\\\s*\\\\([\\\\s\\\\S]{0,240}INTERVAL\\\\s+1\\\\s+DAY[\\\\s\\\\S]{0,160}d1_dt",
    "DATE_ADD\\\\s*\\\\([\\\\s\\\\S]{0,240}INTERVAL\\\\s+3\\\\s+DAY[\\\\s\\\\S]{0,160}d3_dt",
    "DATE_ADD\\\\s*\\\\([\\\\s\\\\S]{0,240}INTERVAL\\\\s+7\\\\s+DAY[\\\\s\\\\S]{0,160}d7_dt"
  ],
  "message":"flam 新增 cohort LTV 的 pay 窗口字段必须按快照成熟日读取。"
} -->
"""
    wrong_sql = """
WITH cohort AS (
  SELECT u.dt AS cohort_dt,
         CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS d1_dt,
         CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 3 DAY), '%Y%m%d') AS SIGNED) AS d3_dt,
         CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED) AS d7_dt
  FROM `user` u
)
SELECT SUM(CASE WHEN s.dt = c.d1_dt THEN JSON_EXTRACT(s.pay, '$.pay1') END) AS `首日 LTV`
FROM cohort c
LEFT JOIN `user` s ON s.uid = c.uid
"""
    correct_sql = """
WITH cohort AS (
  SELECT u.dt AS cohort_dt,
         u.dt AS d1_dt,
         CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 2 DAY), '%Y%m%d') AS SIGNED) AS d3_dt,
         CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 6 DAY), '%Y%m%d') AS SIGNED) AS d7_dt
  FROM `user` u
)
SELECT SUM(CASE WHEN s.dt = c.d1_dt THEN JSON_EXTRACT(s.pay, '$.pay1') END) AS `首日 LTV`
FROM cohort c
LEFT JOIN `user` s ON s.uid = c.uid
"""

    error = _data_skill_sql_validation_error("最近 30 天新增用户首日 LTV、3 日 LTV、7 日 LTV", wrong_sql, data_skill)

    assert error == "flam 新增 cohort LTV 的 pay 窗口字段必须按快照成熟日读取。"
    assert (
        _data_skill_sql_validation_error(
            "最近 30 天新增用户首日 LTV、3 日 LTV、7 日 LTV",
            correct_sql,
            data_skill,
        )
        is None
    )
