"""
脚本说明：验证 flam / first_zombie 数据源 Data Skill 种子包含关键性能口径。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SEED_SCRIPT = ROOT / "tools" / "seed_flam_first_zombie_data_skills.py"
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


OLD_DASHBOARD_VIEW_IDS = {
    "15da41b65ee64aba854e2de701a728bc",
    "e3fe7e4819e64b71b76d9329a3023359",
    "f113ac14e8994d12814452040b702424",
}
EXPECTED_CURRENT_CATALOG_SHA256 = (
    "15dd6c8870705858073d26fc4085d87ca2f6e1f690e440fc4e5f48360d10f51c"
)


def _seed_dashboard_sql() -> dict[str, str]:
    import seed_flam_first_zombie_data_skills as seed

    pattern = re.compile(
        r"<!-- dashboard-sql:(?P<view_id>[^ ]+?) -->\s*```sql\s*\n"
        r"(?P<sql>[\s\S]*?)\n```"
    )
    blocks: dict[str, str] = {}
    for skill in seed.DATA_SKILLS:
        for match in pattern.finditer(skill["prompt"]):
            view_id = match.group("view_id")
            assert view_id not in blocks
            blocks[view_id] = match.group("sql")
    return blocks


def test_dashboard_sql_directory_matches_current_recommended_dashboards() -> None:
    blocks = _seed_dashboard_sql()
    hashes = {
        view_id: hashlib.sha256(sql.encode("utf-8")).hexdigest()
        for view_id, sql in sorted(blocks.items())
    }
    catalog_sha256 = hashlib.sha256(
        json.dumps(
            hashes,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert len(blocks) == 84
    assert OLD_DASHBOARD_VIEW_IDS.isdisjoint(blocks)
    assert catalog_sha256 == EXPECTED_CURRENT_CATALOG_SHA256


@pytest.mark.parametrize("view_id", [
    "4fc570b4be7d406c9f648d9088f760bb",
    "2149b7abbc6c4cd7ad6f52379e69b15a",
])
def test_realtime_payment_components_use_realtime_event_table(view_id: str) -> None:
    sql = _seed_dashboard_sql()[view_id]
    assert "event_realtime" in sql
    assert re.search(r"\b(?:FROM|JOIN)\s+`?event`?\b", sql, re.I) is None
    assert "ServerPayLog" in sql


def test_realtime_skill_description_has_payment_retrieval_anchor() -> None:
    import seed_flam_first_zombie_data_skills as seed

    assert "今天实时付费趋势" in seed.DATA_SKILLS[0]["description"]


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


def test_new_user_skill_routes_current_day_to_realtime_table() -> None:
    import seed_flam_first_zombie_data_skills as seed

    skill = next(item for item in seed.DATA_SKILLS if item["name"] == "flam 新增与留存 cohort 口径")
    prompt = skill["prompt"]

    assert "今天、当天、今日、实时、当前小时、当前分钟、当前整点" in prompt
    assert "截至目前、当前或实时按小时" not in prompt
    assert "必须使用 `event_realtime`" in prompt
    assert "完整历史日和留存 cohort 使用 `event`" in prompt


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


def test_retention_skill_provides_mature_d7_cohort_sql_example() -> None:
    """七日留存生成 SQL 时必须参考已验证的 bounds + D7 快照范式。"""
    content = SEED_SCRIPT.read_text(encoding="utf-8")
    start = content.index('"name": "flam 留存流失与回流口径"')
    end = content.index('"name": "flam 用户分层与人群分析口径"', start)
    retention_section = content[start:end]

    assert "## 七日留存 SQL 示例（MySQL/StarRocks）" in retention_section
    assert "WITH bounds AS (" in retention_section
    assert "SELECT MAX(dt) AS max_dt" in retention_section
    assert "JSON_UNQUOTE(JSON_EXTRACT(r.remain, '$.remain7'))" in retention_section
    assert "不得在 `WHERE` 中直接使用 `MAX(dt)`" in retention_section


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
