"""
脚本说明：验证 flam / first_zombie 数据源 Data Skill 种子包含关键性能口径。
"""
from __future__ import annotations

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

REALTIME_CURRENT_DATE_VIEW_IDS = {
    "4fc570b4be7d406c9f648d9088f760bb",
    "2149b7abbc6c4cd7ad6f52379e69b15a",
}

METRIC_CURRENT_DATE_VIEW_IDS = {
    "9d4add7a8be048ea9c7beb62a43e50cc",
    "9325211a9f594376bf818cec639aa103",
    "440303dfdf39408ba86ffb222f3334f2",
    "0b849c96c0a3480c9e940b92995d5e3e",
    "4608fb0831cd4845ba881678fb778b2f",
    "dbc481fea69d4314af8535600fa4f8c8",
    "48f02edf9a364e1082cd67008cd60b2b",
    "8f6dcec8cfdb40b4a7c02139b7d35f56",
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


def _assert_dashboard_date_contract(prompt: str) -> None:
    assert "{{dashboard_start_yyyymmdd}}" in prompt
    assert "{{dashboard_end_yyyymmdd}}" in prompt
    assert "固定语义 `metric`" in prompt
    assert "不得返回 `date_filter`" in prompt
    assert "`time_field` 必须对应 SQL 中实际参数化字段" in prompt
    assert "返回 `date_filter` 时不得使用 `CURDATE()`" in prompt


def test_all_flam_skills_contain_dashboard_date_contract() -> None:
    import seed_flam_first_zombie_data_skills as seed

    for skill in seed.DATA_SKILLS:
        _assert_dashboard_date_contract(skill["prompt"])


def test_dashboard_sql_directory_matches_current_recommended_dashboards() -> None:
    blocks = _seed_dashboard_sql()

    assert len(blocks) == 84
    assert OLD_DASHBOARD_VIEW_IDS.isdisjoint(blocks)


@pytest.mark.parametrize("view_id", [
    "4fc570b4be7d406c9f648d9088f760bb",
    "2149b7abbc6c4cd7ad6f52379e69b15a",
])
def test_realtime_payment_components_use_realtime_event_table(view_id: str) -> None:
    sql = _seed_dashboard_sql()[view_id]
    assert "event_realtime" in sql
    assert re.search(r"\b(?:FROM|JOIN)\s+`?event`?\b", sql, re.I) is None
    assert "ServerPayLog" in sql


def test_realtime_payment_components_keep_explicit_utc8_business_date() -> None:
    blocks = _seed_dashboard_sql()

    for view_id in REALTIME_CURRENT_DATE_VIEW_IDS:
        sql = blocks[view_id]
        assert "{{dashboard_start_yyyymmdd}}" not in sql
        assert "{{dashboard_end_yyyymmdd}}" not in sql
        assert "DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR)" in sql


def test_metric_components_use_fixed_example_date_without_dashboard_tokens() -> None:
    import seed_flam_first_zombie_data_skills as seed

    blocks = _seed_dashboard_sql()

    for view_id in METRIC_CURRENT_DATE_VIEW_IDS:
        sql = blocks[view_id]
        assert "{{dashboard_start_yyyymmdd}}" not in sql
        assert "{{dashboard_end_yyyymmdd}}" not in sql
        assert "STR_TO_DATE('20260730', '%Y%m%d')" in sql

    prompt = next(
        skill["prompt"]
        for skill in seed.DATA_SKILLS
        if skill["name"] == "flam 主城建设与成长口径"
    )
    assert "`20260730` 仅表示已由调用方确定的当前业务日" in prompt
    assert "UTC+8 当前业务日" not in prompt


def test_unknown_dashboard_current_date_usage_fails_closed() -> None:
    import seed_flam_first_zombie_data_skills as seed

    for expression in (
        "curdate ( )",
        "NOW()",
        "CURRENT_DATE",
        "CURRENT_TIMESTAMP()",
    ):
        prompt = f"<!-- dashboard-sql:unknown-view -->\n```sql\nSELECT {expression}\n```"
        with pytest.raises(ValueError, match="unknown-view"):
            seed._tokenize_dashboard_sql_current_date(prompt)


def test_month_card_retention_observation_window_tracks_selected_cohort_range() -> None:
    sql = _seed_dashboard_sql()["97337c8b63544de89f26d2719cc45e75"]

    assert "INTERVAL 60 DAY" not in sql
    assert (
        "DATE_SUB(STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), "
        "'%Y%m%d'), INTERVAL 30 DAY)"
    ) in sql
    assert "STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d')" in sql


def test_realtime_skill_description_has_payment_retrieval_anchor() -> None:
    import seed_flam_first_zombie_data_skills as seed

    assert "今天实时付费趋势" in seed.DATA_SKILLS[0]["description"]


def test_platform_data_skills_do_not_expose_explicit_timezone_guidance() -> None:
    import seed_flam_first_zombie_data_skills as seed

    text = "\n".join(
        f"{skill['name']}\n{skill['description']}\n{skill['prompt']}"
        for skill in seed.DATA_SKILLS
    )

    assert "UTC+8" not in text
    assert "Asia/Shanghai" not in text
    assert "业务时区" not in text


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


def test_flam_generic_default_date_ranges_defer_to_platform_rule() -> None:
    import seed_flam_first_zombie_data_skills as seed

    names = {
        "flam 历史看板日期窗口口径",
        "flam 活跃用户口径",
        "flam 礼包购买结构口径",
        "flam 新手引导漏斗口径",
        "flam 渠道投放注册与付费口径",
        "flam 钻石经济口径",
    }
    prompts = {
        skill["name"]: skill["prompt"]
        for skill in seed.DATA_SKILLS
        if skill["name"] in names
    }

    assert set(prompts) == names
    for prompt in prompts.values():
        assert "未指定日期范围时，遵循平台通用 Data Skill 的过去 7 个完整自然日默认范围" in prompt


def test_data_skills_do_not_proactively_recommend_database_current_date() -> None:
    """仅保留明确否定数据库当前日期函数的说明，不能把它作为 SQL 日期边界。"""
    import seed_flam_first_zombie_data_skills as seed

    negative_markers = ("不要", "不能", "不得", "禁止", "不应")
    proactive_lines = [
        f"{skill['name']}: {line.strip()}"
        for skill in seed.DATA_SKILLS
        for line in skill["prompt"].splitlines()
        if "CURDATE()" in line
        and not any(marker in line for marker in negative_markers)
    ]

    assert proactive_lines == []


def test_data_skills_document_complete_date_filter_contract() -> None:
    import seed_flam_first_zombie_data_skills as seed

    prompt = next(
        skill["prompt"]
        for skill in seed.DATA_SKILLS
        if skill["name"] == "flam 历史看板日期窗口口径"
    )

    assert '"time_field":"dt"' in prompt
    assert '"date_parameter_type":"yyyymmdd_number"' in prompt
    assert '"date_expression":{"version":1,"mode":"preset","preset":"past_7_days"}' in prompt
    assert '"start":"{{dashboard_start_yyyymmdd}}"' not in prompt


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
