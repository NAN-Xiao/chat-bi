"""
脚本说明：验证 flam / first_zombie 数据源 Data Skill 种子包含关键性能口径。
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SEED_SCRIPT = ROOT / "tools" / "seed_flam_first_zombie_data_skills.py"


def test_payment_ltv_skill_requires_fixed_snapshot_partition_bounds_in_cte_scope() -> None:
    """
    是什么：LTV 自连接快照时必须提示固定二次扫描分区边界，并在当前 CTE 引入 bounds 别名。
    """
    content = SEED_SCRIPT.read_text(encoding="utf-8")

    assert "snapshot_partition_bounds_required" in content
    assert "必须为回连快照别名 `s` 增加固定分区边界" in content
    assert "s.dt BETWEEN" in content
    assert "JOIN bounds b ON 1 = 1" in content
    assert "CTE 之间不会继承表别名作用域" in content
