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


def test_data_skill_sql_validation_rejects_flam_ltv_snapshot_join_without_dt_filter() -> None:
    """
    是什么：test_data_skill_sql_validation_rejects_flam_ltv_snapshot_join_without_dt_filter 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    data_skill = r"""
<!-- data-skill-sql-validation:{
  "match":["ltv","3日LTV","3 日 LTV","7日LTV","7 日 LTV"],
  "forbidden_sql_patterns":[
    "LEFT\\s+JOIN\\s+(?:`?first_zombie`?\\s*\\.\\s*)?`?user`?\\s+(?:AS\\s+)?`?s`?\\s+ON\\s+(?!(?:(?!\\b(?:WHERE|GROUP\\s+BY|ORDER\\s+BY|LIMIT|LEFT\\s+JOIN|RIGHT\\s+JOIN|INNER\\s+JOIN|JOIN)\\b)[\\s\\S])*`?s`?\\s*\\.\\s*`?dt`?)(?:(?!\\b(?:WHERE|GROUP\\s+BY|ORDER\\s+BY|LIMIT|LEFT\\s+JOIN|RIGHT\\s+JOIN|INNER\\s+JOIN|JOIN)\\b)[\\s\\S])*`?s`?\\s*\\.\\s*`?uid`?\\s*=\\s*`?c`?\\s*\\.\\s*`?uid`?"
  ],
  "message":"flam 新增 cohort LTV 回连 user 快照时必须在 JOIN 条件中限定成熟快照分区。"
} -->
"""
    wrong_sql = """
WITH cohort AS (
  SELECT u.dt AS cohort_dt,
         u.uid,
         CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 2 DAY), '%Y%m%d') AS SIGNED) AS d3_dt,
         CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 6 DAY), '%Y%m%d') AS SIGNED) AS d7_dt
  FROM `first_zombie`.`user` `u`
  WHERE `u`.`dt` BETWEEN 20260618 AND 20260630
    AND JSON_UNQUOTE(JSON_EXTRACT(`u`.`userinfo`, '$.country')) = 'US'
)
SELECT c.cohort_dt,
       ROUND(SUM(CASE WHEN `s`.`dt` = `c`.`d3_dt` THEN JSON_EXTRACT(`s`.`pay`, '$.pay3') END) / COUNT(DISTINCT c.uid), 2) AS `3 日 LTV`,
       ROUND(SUM(CASE WHEN `s`.`dt` = `c`.`d7_dt` THEN JSON_EXTRACT(`s`.`pay`, '$.pay7') END) / COUNT(DISTINCT c.uid), 2) AS `7 日 LTV`
FROM cohort c
LEFT JOIN `first_zombie`.`user` `s` ON `s`.`uid` = `c`.`uid` AND `s`.`prod` = 110000038
GROUP BY c.cohort_dt
"""
    correct_sql = """
WITH cohort AS (
  SELECT u.dt AS cohort_dt,
         u.uid,
         CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 2 DAY), '%Y%m%d') AS SIGNED) AS d3_dt,
         CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 6 DAY), '%Y%m%d') AS SIGNED) AS d7_dt
  FROM `first_zombie`.`user` `u`
  WHERE `u`.`dt` BETWEEN 20260618 AND 20260630
    AND JSON_UNQUOTE(JSON_EXTRACT(`u`.`userinfo`, '$.country')) = 'US'
)
SELECT c.cohort_dt,
       ROUND(SUM(CASE WHEN `s`.`dt` = `c`.`d3_dt` THEN JSON_EXTRACT(`s`.`pay`, '$.pay3') END) / COUNT(DISTINCT c.uid), 2) AS `3 日 LTV`,
       ROUND(SUM(CASE WHEN `s`.`dt` = `c`.`d7_dt` THEN JSON_EXTRACT(`s`.`pay`, '$.pay7') END) / COUNT(DISTINCT c.uid), 2) AS `7 日 LTV`
FROM cohort c
LEFT JOIN `first_zombie`.`user` `s`
  ON `s`.`uid` = `c`.`uid`
 AND `s`.`prod` = 110000038
 AND `s`.`dt` IN (`c`.`d3_dt`, `c`.`d7_dt`)
GROUP BY c.cohort_dt
"""

    error = _data_skill_sql_validation_error("美国 6 月 18 日之后新增用户 3 日 LTV 和 7 日 LTV", wrong_sql, data_skill)

    assert error == "flam 新增 cohort LTV 回连 user 快照时必须在 JOIN 条件中限定成熟快照分区。"
    assert (
        _data_skill_sql_validation_error(
            "美国 6 月 18 日之后新增用户 3 日 LTV 和 7 日 LTV",
            correct_sql,
            data_skill,
        )
        is None
    )


def test_data_skill_sql_validation_allows_event_metric_when_required_metric_sources_exist() -> None:
    """
    是什么：DAU/PDAU 使用正确来源表时，同一 SQL 可额外用 fact_events 统计指定埋点。
    """
    rules = [
        {
            "match": ["DAU", "dau", "活跃趋势", "活跃用户"],
            "required_sql_contains": ["fact_sessions"],
            "forbidden_sql_select_all_contains": [
                ["fact_events", "count(distinct", ' as "dau"'],
                ["fact_events", "count(distinct", " as dau"],
            ],
            "message": "DAU 趋势必须按本 Data Skill 使用 fact_sessions 计算。fact_events 只能用于事件 PV/UV 或用户明确指定的埋点触发人数。",
        },
        {
            "match": ["PDAU", "pdau", "付费DAU", "付费活跃", "付费用户趋势"],
            "required_sql_contains": ["fact_payments"],
            "forbidden_sql_select_all_contains": [
                ["fact_events", "count(distinct", ' as "pdau"'],
                ["fact_events", "count(distinct", " as pdau"],
            ],
            "message": "PDAU 趋势必须按本 Data Skill 使用 fact_payments 的成功净收入订单计算。fact_events 只能用于事件 PV/UV 或用户明确指定的埋点触发人数。",
        },
    ]
    data_skill = f"<!-- data-skill-sql-validation:{json.dumps(rules, ensure_ascii=False)} -->"
    mixed_sql = """
WITH obs AS (
  SELECT max(session_start::date) AS max_date FROM fact_sessions
),
days AS (
  SELECT generate_series(obs.max_date - 29, obs.max_date, interval '1 day')::date AS event_date FROM obs
),
dau AS (
  SELECT s.session_start::date AS event_date, count(DISTINCT s.player_id) AS dau
  FROM fact_sessions s CROSS JOIN obs
  WHERE s.session_start::date BETWEEN obs.max_date - 29 AND obs.max_date
  GROUP BY s.session_start::date
),
pdau AS (
  SELECT p.event_date, count(DISTINCT p.player_id) AS pdau
  FROM fact_payments p CROSS JOIN obs
  WHERE p.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    AND p.payment_status = 'success'
    AND p.net_revenue_usd > 0
  GROUP BY p.event_date
),
event_users AS (
  SELECT e.event_date, count(DISTINCT e.player_id) AS spaceship_upgrade_complete_users
  FROM fact_events e CROSS JOIN obs
  WHERE e.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    AND e.event_name = 'spaceship_upgrade_complete'
  GROUP BY e.event_date
)
SELECT d.event_date AS "日期",
       coalesce(da.dau, 0) AS "DAU",
       coalesce(pa.pdau, 0) AS "PDAU",
       coalesce(eu.spaceship_upgrade_complete_users, 0) AS "spaceship_upgrade_complete触发用户"
FROM days d
LEFT JOIN dau da ON da.event_date = d.event_date
LEFT JOIN pdau pa ON pa.event_date = d.event_date
LEFT JOIN event_users eu ON eu.event_date = d.event_date
ORDER BY d.event_date
"""
    wrong_sql = """
SELECT e.event_date AS "日期",
       count(DISTINCT e.player_id) AS "DAU",
       count(DISTINCT e.player_id) FILTER (WHERE e.event_name = 'pay') AS "PDAU"
FROM fact_events e
GROUP BY e.event_date
"""

    question = "显示最近 30 天的 DAU、PDAU 趋势，同时统计 spaceship_upgrade_complete 埋点的触发用户"

    assert _data_skill_sql_validation_error(question, mixed_sql, data_skill) is None
    assert (
        _data_skill_sql_validation_error(question, wrong_sql, data_skill)
        == "DAU 趋势必须按本 Data Skill 使用 fact_sessions 计算。fact_events 只能用于事件 PV/UV 或用户明确指定的埋点触发人数。"
    )
