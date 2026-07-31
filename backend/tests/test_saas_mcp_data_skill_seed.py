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
