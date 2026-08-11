"""验证平台 SaaS MCP DataSkill 不暴露显式时区说明。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def test_saas_mcp_data_skills_do_not_expose_explicit_timezone_guidance() -> None:
    import seed_saas_mcp_data_skills as seed

    text = "\n".join(
        f"{skill['name']}\n{skill['description']}\n{skill['prompt']}"
        for skill in seed.DATA_SKILLS
    )

    assert "UTC+8" not in text
    assert "Asia/Shanghai" not in text
    assert "业务时区" not in text


def _chatmon_skill_prompt(skill_id: str) -> str:
    import seed_saas_mcp_data_skills as seed

    for skill in seed.DATA_SKILLS:
        if f'"id": "{skill_id}"' in skill["prompt"]:
            return skill["prompt"]
    raise AssertionError(f"missing SaaS Skill {skill_id}")


def test_chatmon_count_skill_does_not_match_generic_flam_trends() -> None:
    from apps.chat.task.saas_skill import find_matching_executable_saas_skill

    prompt = _chatmon_skill_prompt("saas_chatmon_alert_count")

    assert find_matching_executable_saas_skill(prompt, "最近 7 天升级次数按日趋势") is None
    assert find_matching_executable_saas_skill(prompt, "最近 30 天主城等级玩家分布趋势") is None


def test_chatmon_count_skill_still_matches_explicit_alert_trends() -> None:
    from apps.chat.task.saas_skill import find_matching_executable_saas_skill

    prompt = _chatmon_skill_prompt("saas_chatmon_alert_count")
    match = find_matching_executable_saas_skill(prompt, "最近 7 天告警趋势")

    assert match is not None
    assert match.definition["id"] == "saas_chatmon_alert_count"
