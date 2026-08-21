"""lds 推荐看板产品条件修复入口配置测试。"""

from __future__ import annotations

import sys
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import repair_lds_recommended_dashboard_product_id as lds  # noqa: E402


def test_lds_profile_has_fixed_workspace_and_datasource_scope() -> None:
    profile = lds.PROFILE

    assert profile["tenant_id"] == 7493272675721154560
    assert profile["tenant_public_id"] == "WS6MEJGDSA"
    assert profile["target_product_id"] == "110000039"
    assert profile["bound_datasource"] == 10
    assert profile["roi_datasource"] == 14
    assert len(profile["dashboards"]) == 10
    assert sum(spec[2] for spec in profile["dashboards"].values()) == 55
    assert profile["excluded_user_dashboard_id"] not in profile["dashboards"]
