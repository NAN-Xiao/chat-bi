"""j2000 推荐看板产品条件修复入口配置测试。"""

from __future__ import annotations

import sys
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import repair_j2000_recommended_dashboard_product_id as j2000  # noqa: E402


def test_j2000_profile_has_fixed_workspace_and_datasource_scope() -> None:
    profile = j2000.PROFILE

    assert profile["tenant_id"] == 7493583991958671360
    assert profile["tenant_public_id"] == "WSCWXDWV48"
    assert profile["target_product_id"] == "110000034"
    assert profile["bound_datasource"] == 11
    assert profile["roi_datasource"] == 15
    assert len(profile["dashboards"]) == 10
    assert sum(spec[2] for spec in profile["dashboards"].values()) == 55
    assert profile["excluded_user_dashboard_id"] not in profile["dashboards"]
