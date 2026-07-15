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
