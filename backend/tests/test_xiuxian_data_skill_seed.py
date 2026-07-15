"""验证修仙数据源 Data Skill 种子的付费与 ARPPU 口径。"""
from __future__ import annotations

import sys
from pathlib import Path

from apps.chat.task.llm import _data_skill_sql_validation_error

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import seed_xiuxian_data_skills as seed


def _payment_skill() -> dict[str, str]:
    return next(
        skill
        for skill in seed.DATA_SKILLS
        if "data-skill-source:xiuxian:paybuyret-monetization-arppu" in skill["prompt"]
    )


def _date_skill() -> dict[str, str]:
    return next(
        skill
        for skill in seed.DATA_SKILLS
        if "data-skill-source:xiuxian:date-partition-aggregation" in skill["prompt"]
    )


def test_xiuxian_payment_skill_is_scoped_and_keeps_date_skill() -> None:
    assert seed.TENANT_ID == 7482727237662281728
    assert seed.DATASOURCE_ID == 6
    assert len(seed.DATA_SKILLS) == 2
    assert any(
        "data-skill-source:xiuxian:date-partition-aggregation" in skill["prompt"]
        for skill in seed.DATA_SKILLS
    )
    assert _payment_skill()["name"] == "修仙付费收入与 ARPPU 口径"


def test_xiuxian_payment_skill_documents_verified_paybuyret_formula() -> None:
    prompt = _payment_skill()["prompt"]

    assert "event = 'PayBuyRet'" in prompt
    assert "personal.ed_money" in prompt
    assert "personal.ed_isSuccess" in prompt
    assert "COUNT(DISTINCT uid)" in prompt
    assert "SUM(ed_money) / NULLIF(COUNT(DISTINCT uid), 0)" in prompt
    assert "pay.paytotal" in prompt
    assert "不能用于当日付费金额、当日付费人数或 ARPPU" in prompt
    assert "ed_orderId" in prompt
    assert "ed_payId" in prompt
    assert "不能代替订单号" in prompt


def test_xiuxian_payment_skill_declares_recursive_ctes_with_column_aliases() -> None:
    """修仙 AnalyticDB 要求 WITH RECURSIVE 块内所有 CTE 显式声明输出列名。"""
    prompt = _payment_skill()["prompt"]

    for declaration in (
        "params (end_date, start_date) AS (",
        "days (calendar_date, end_date) AS (",
        "pay (pay_date, uid, ed_money) AS (",
        "daily_pay (pay_date, revenue, payers, payment_event_count) AS (",
    ):
        assert declaration in prompt


def test_xiuxian_payment_skill_uses_partition_bounds_for_recent_seven_days() -> None:
    """近七天查询直接使用系统日期边界限制整数分区。"""
    prompt = _payment_skill()["prompt"]

    assert "SELECT MAX(" not in prompt.upper()
    assert "bounds (start_dt, end_dt) AS (" not in prompt
    assert "CROSS JOIN bounds" not in prompt
    assert "DATE_SUB(CURDATE(), INTERVAL 7 DAY)" in prompt
    assert "DATE_SUB(CURDATE(), INTERVAL 1 DAY)" in prompt
    assert "WHERE e.dt BETWEEN" in prompt


def test_xiuxian_date_skill_uses_dynamic_bounds_without_max_date_scan() -> None:
    """通用日期口径根据问题动态生成边界，不扫描最大分区。"""
    prompt = _date_skill()["prompt"]

    assert "SELECT MAX(" not in prompt.upper()
    assert "WITH bounds AS" not in prompt
    assert "CROSS JOIN bounds" not in prompt
    assert "## 标准聚合 SQL" not in prompt
    assert "未指定日期窗口时，默认查询截至昨天的最近 28 个自然日" in prompt
    assert "用户指定相对日期窗口" in prompt
    assert "用户指定绝对起止日期" in prompt
    assert "DATE_SUB(CURDATE(), INTERVAL 29 DAY)" in prompt
    assert "DATE_SUB(CURDATE(), INTERVAL 1 DAY)" in prompt
    assert "禁止使用 `MAX(dt)`" in prompt


def test_xiuxian_date_skill_rejects_max_dt_partition_probe() -> None:
    """修仙日期口径禁止通过 MAX(dt) 全表扫描探测最大业务日期。"""
    prompt = _date_skill()["prompt"]
    message = "修仙数据源禁止使用 MAX(dt) 扫描最大业务日期；请根据用户时间范围或默认最近 28 天直接生成 dt 分区边界。"

    assert _data_skill_sql_validation_error(
        "查看近七天日活",
        "SELECT MAX(dt) AS max_dt FROM event",
        prompt,
    ) == message
    assert _data_skill_sql_validation_error(
        "查看近七天日活",
        "SELECT MAX(e.dt) AS max_dt FROM event e",
        prompt,
    ) == message


def test_xiuxian_date_skill_allows_non_partition_max_aggregate() -> None:
    """禁止分区探测不能误伤普通 MAX 聚合。"""
    prompt = _date_skill()["prompt"]
    sql = "SELECT e.dt, MAX(e.level) FROM event e WHERE e.dt = 20260714 GROUP BY e.dt"

    assert _data_skill_sql_validation_error("查看昨日最高等级", sql, prompt) is None


def test_xiuxian_payment_skill_rejects_cumulative_snapshot_arppu_sql() -> None:
    prompt = _payment_skill()["prompt"]
    wrong_sql = """
    SELECT dt,
           SUM(JSON_EXTRACT(pay, '$.paytotal'))
             / NULLIF(COUNT(DISTINCT uid), 0) AS ARPPU
    FROM `user`
    GROUP BY dt
    """

    assert _data_skill_sql_validation_error("查看近七天的 ARPPU", wrong_sql, prompt) == (
        "修仙付费趋势必须使用 PayBuyRet 的成功事件、personal.ed_money 和去重 uid；"
        "paytotal 是累计快照，不能计算当日收入、当日付费人数或 ARPPU。"
    )


def test_xiuxian_payment_skill_rejects_non_distinct_arppu_denominator() -> None:
    prompt = _payment_skill()["prompt"]
    wrong_sql = """
    SELECT e.dt,
           SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_money')) AS DECIMAL(18, 4)))
             / NULLIF(COUNT(*), 0) AS ARPPU
    FROM `event` e
    WHERE e.event = 'PayBuyRet'
      AND JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_isSuccess')) IN ('true', '1')
    GROUP BY e.dt
    """

    assert _data_skill_sql_validation_error("查看近七天的 ARPPU", wrong_sql, prompt) == (
        "修仙付费趋势必须使用 PayBuyRet 的成功事件、personal.ed_money 和去重 uid；"
        "paytotal 是累计快照，不能计算当日收入、当日付费人数或 ARPPU。"
    )


def test_xiuxian_payment_skill_allows_verified_paybuyret_arppu_sql() -> None:
    prompt = _payment_skill()["prompt"]
    correct_sql = """
    SELECT e.dt,
           SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_money')) AS DECIMAL(18, 4)))
             / NULLIF(COUNT(DISTINCT e.uid), 0) AS ARPPU
    FROM `event` e
    WHERE e.event = 'PayBuyRet'
      AND JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_isSuccess')) IN ('true', '1')
      AND CAST(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_money')) AS DECIMAL(18, 4)) > 0
    GROUP BY e.dt
    """

    assert _data_skill_sql_validation_error("查看近七天的 ARPPU", correct_sql, prompt) is None
