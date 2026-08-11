"""验证 SLG BI Mock 看板 Data Skill 的关键字段约束。"""

import sys
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from seed_slg_bi_dashboard_skills import DASHBOARD_SKILLS  # noqa: E402


def test_payment_overview_skill_uses_real_payment_channel_fields() -> None:
    skill = next(item for item in DASHBOARD_SKILLS if item["slug"] == "payment-overview-ltv")
    prompt = skill["prompt"]

    assert "fact_payments.payment_source_channel" in prompt
    assert "fact_payments.bi_channel_name" in prompt
    assert "fact_payments.bi_channel_group" in prompt
    assert "fact_payments` 不存在裸 `channel" in prompt
    assert "payment_source_channel`，图表用表格" in prompt
