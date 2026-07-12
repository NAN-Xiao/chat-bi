"""
脚本说明：验证 flam / first_zombie 数据源 Data Skill 种子包含关键性能口径。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED_SCRIPT = ROOT / "tools" / "seed_flam_first_zombie_data_skills.py"
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


class _StaleSkillCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.parameters: list[object] = []

    def execute(self, sql, params=None) -> None:
        self.executed.append(sql)
        self.parameters.append(params)

    def fetchall(self):
        return [(101,)]


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


def test_data_skill_seed_documents_verified_transaction_and_cohort_rules() -> None:
    content = SEED_SCRIPT.read_text(encoding="utf-8")

    assert "ServerPayLog.personal.money" in content
    assert "ServerPayLog.personal.orderId" in content
    assert "ServerPayLog.personal.productid" in content
    assert "userinfo.country" in content
    assert "pay.firstpaytime" in content
    assert "支付流程事件" in content
    assert "未成熟 cohort" in content
    assert "待补充字段映射" in content
    assert "CCU.personal.ed_ccu" in content


def test_data_skill_seed_limits_custom_prompt_lifecycle_to_exact_datasource_scope() -> None:
    content = SEED_SCRIPT.read_text(encoding="utf-8")
    upsert_section = content[content.index("def _upsert_skill") : content.index("def _delete_stale_skills")]
    delete_section = content[content.index("def _delete_stale_skills") : content.index("def _save_embeddings")]

    for section in (upsert_section, delete_section):
        assert "type = 'DATA_SKILL'" in section
        assert "specific_ds = TRUE" in section
        assert "datasource_ids = %s::jsonb" in section


def test_activity_quality_skill_uses_participation_cohort_observation_events() -> None:
    content = SEED_SCRIPT.read_text(encoding="utf-8")
    start = content.index('"name": "flam 活动参与与后续质量口径"')
    end = content.index('"name": "flam 钻石经济口径"', start)
    activity_section = content[start:end]

    assert "参与日后的精确 D1/D7 `UserActive`" in activity_section
    assert "参与日后的精确目标日 `ServerPayLog`" in activity_section
    assert "不得使用注册 cohort 的 `remain.remain1/remain7` 或 `pay1/pay7`" in activity_section


def test_stale_skill_deletion_locks_exact_datasource_scope_before_preferences(monkeypatch) -> None:
    import seed_flam_first_zombie_data_skills as seed

    cursor = _StaleSkillCursor()
    monkeypatch.setattr(seed, "STALE_SKILL_MARKERS", ("stale-marker",))

    assert seed._delete_stale_skills(cursor, tenant_id=11, datasource_id=3) == [101]

    select_sql = cursor.executed[0]
    select_params = cursor.parameters[0]
    assert "specific_ds = TRUE" in select_sql
    assert "datasource_ids = %s::jsonb" in select_sql
    assert "FOR UPDATE" in select_sql
    assert select_params[0] == 11
    assert select_params[1].obj == [3]
    assert select_params[2] == "stale-marker"
    assert "custom_prompt_user_preference" in cursor.executed[1]
