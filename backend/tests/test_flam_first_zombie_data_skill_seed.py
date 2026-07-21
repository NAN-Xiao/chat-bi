"""
脚本说明：验证 flam / first_zombie 数据源 Data Skill 种子包含关键性能口径。
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

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
EXPECTED_CHANGED_SQL_SHA256 = {
    "2149b7abbc6c4cd7ad6f52379e69b15a": "f9db15590f5510ea34062f363e165d6c18d12f19dc4dcbb89edaaf195600e9e9",
    "2187432754973679616": "49aa5883b49242188e43d642c11cd1a67a933694cf9fb00029cea4d3ef5aba29",
    "22f0761ab59449189707aca09323810e": "74c8c45d23d2fd30476cff5841ed436b9457fee6ae9bfad874cafbfa2a1866a3",
    "3bb23e771d584610a2c88a38760163b6": "3d63ae7018684ec69c493c5d77756165223decfe11895af58194d6bbdb9daa5f",
    "4d250a8575cc4bcd84f7b9514abbf455": "e02956d0746e910d1a4bd569588ef83d5a853aa95a956d7a3db78365a3f49db6",
    "4fc570b4be7d406c9f648d9088f760bb": "7a63d560519a7c79054b0e2286bc87e0a5bdde5d4d9a86dda2ecd7ae47f63351",
    "531012d01f104a509da2d1926692ee1d": "039eb5012bf3f4a58c2956029483e08f0d0e9e947a28cd2537a06f7d8a92875f",
    "63e03c7e2ad34ad58321892998497a85": "112a33b31fc3ff51a90a798d132254a0e45c1684f7575c438003e11c8d227352",
    "97337c8b63544de89f26d2719cc45e75": "5e738ef4d573ffb70e1fc7139fd0cc787baacbf718fa4fba71470e1d17067b99",
    "b55382d46c664f1dbd465964cc5e8da2": "112a33b31fc3ff51a90a798d132254a0e45c1684f7575c438003e11c8d227352",
    "ba0dc1580f0d43c29c0d6cdf26a6239c": "666913e0f9857e759857df94144df03853a33ce9624d39691243ab6673473c4f",
    "ba48ea6e38e748ee9990b59324459b64": "71f7968b3d9e82238467da3514bab7881d7a6c1050359e5af63ed44584f414fe",
    "c23c019171804f608e92961dc06ae8b2": "67679b4379d938a4e3953eaf86bedd1f126959235000844cbc65dea94249da6f",
    "d84e234a7f3b4e728a8b02d61911d88f": "dbf2a7f6be2edf965a27b8c17e40a79d8ee2c858b62ca7f6c099b53d44b4b27c",
    "e3e716d42d654e61ab80c62c1915d0e8": "28e12cc68dbd83758a2a2fb080e182e357bf8307dfad81d6e055bf1d377d97fe",
    "f0d759307a304043883a23499a281b97": "0c1aa9ce3f88793ae0d1cb3ac5ada2089d0290a5ed052e187df21ca7d7125886",
    "f39bac6b01784ca5b92c60ffe4348756": "112a33b31fc3ff51a90a798d132254a0e45c1684f7575c438003e11c8d227352",
}


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

    assert len(blocks) == 84
    assert OLD_DASHBOARD_VIEW_IDS.isdisjoint(blocks)
    assert EXPECTED_CHANGED_SQL_SHA256.keys() <= blocks.keys()
    assert {
        view_id: hashlib.sha256(blocks[view_id].encode("utf-8")).hexdigest()
        for view_id in EXPECTED_CHANGED_SQL_SHA256
    } == EXPECTED_CHANGED_SQL_SHA256


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
