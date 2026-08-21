"""unicorn 推荐看板产品条件修复入口配置测试。"""

from __future__ import annotations

import sys
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import repair_unicorn_recommended_dashboard_product_id as unicorn  # noqa: E402


def test_unicorn_profile_has_fixed_workspace_and_datasource_scope() -> None:
    profile = unicorn.PROFILE

    assert profile["tenant_id"] == 7493583885482070016
    assert profile["tenant_public_id"] == "WSWGCD2XXN"
    assert profile["target_product_id"] == "110000030"
    assert profile["bound_datasource"] == 9
    assert profile["roi_datasource"] == 16
    assert len(profile["dashboards"]) == 10
    assert sum(spec[2] for spec in profile["dashboards"].values()) == 55
    assert set(profile["excluded_user_dashboard_ids"]).isdisjoint(profile["dashboards"])
