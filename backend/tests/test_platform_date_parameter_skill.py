"""验证平台日期字段 Skill 的受控 token 语法契约。"""

from __future__ import annotations

import sys
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import seed_platform_date_field_usage_skill as date_field_seed  # noqa: E402


def test_platform_date_skill_keeps_tokens_outside_sql_literals() -> None:
    prompt = date_field_seed.SKILL["prompt"]

    assert "`{{dashboard_start_date}}` 和 `{{dashboard_end_date}}`" in prompt
    assert "`{{dashboard_start_timestamp}}`" in prompt
    assert "不能放在单引号、双引号、标识符或注释中" in prompt
    assert "event_date BETWEEN {{dashboard_start_date}} AND {{dashboard_end_date}}" in prompt
    assert "TO_DATE({{dashboard_start_yyyymmdd}}, 'YYYYMMDD')" in prompt
    assert "禁止写成 `TO_DATE('{{dashboard_start_yyyymmdd}}', 'YYYYMMDD')`" in prompt
