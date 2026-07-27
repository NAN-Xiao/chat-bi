"""验证修仙数据源 Data Skill 种子的付费与 ARPPU 口径。"""
from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path

from apps.chat.task.llm import (
    _data_skill_sql_validation_error,
    _data_skill_sql_validation_violation,
)

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import seed_xiuxian_data_skills as seed  # noqa: E402


@lru_cache(maxsize=1)
def _skills() -> tuple[dict[str, str], ...]:
    from xiuxian_dashboard_skill_catalog import EXPECTED_VIEW_IDS
    from xiuxian_dashboard_snapshot import DashboardSnapshot

    view_ids = sorted(EXPECTED_VIEW_IDS)
    dashboards = []
    for dashboard_index in range(9):
        canvas = {
            view_id: {"sql": f"SELECT {index} AS metric_{index}"}
            for index, view_id in enumerate(
                view_ids[dashboard_index * 5 : dashboard_index * 5 + 5],
                start=dashboard_index * 5,
            )
        }
        dashboards.append(
            DashboardSnapshot.from_row(
                (
                    f"dashboard-{dashboard_index}",
                    f"推荐看板 {dashboard_index}",
                    seed.TENANT_ID,
                    seed.DATASOURCE_ID,
                    json.dumps(canvas, ensure_ascii=False),
                )
            )
        )
    return tuple(seed.build_data_skills(dashboards))


def _payment_skill() -> dict[str, str]:
    return next(
        skill
        for skill in _skills()
        if "data-skill-source:xiuxian:serverpaylog-monetization-arppu" in skill["prompt"]
    )


def _date_skill() -> dict[str, str]:
    return next(
        skill
        for skill in seed.DATA_SKILLS
        if "data-skill-source:xiuxian:date-partition-aggregation" in skill["prompt"]
    )


def _player_snapshot_skill() -> dict[str, str]:
    return next(
        skill
        for skill in _skills()
        if "data-skill-source:xiuxian:dashboard:player-snapshot" in skill["prompt"]
    )


def _payer_penetration_skill() -> dict[str, str]:
    return next(
        skill
        for skill in _skills()
        if "data-skill-source:xiuxian:dashboard:payer-penetration" in skill["prompt"]
    )


def _repair_example_sql(title: str) -> str:
    match = re.search(
        rf"-- 修复示例：{re.escape(title)}\n(?P<sql>.*?)(?=\n```)",
        seed.SERVERPAYLOG_REPAIR_EXAMPLES,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group("sql").strip()


def test_xiuxian_date_skill_uses_canonical_retrieval_description() -> None:
    expected = (
        "修仙 datasource_id=6 日期趋势口径："
        "最近15天补齐新增趋势、按日补零、固定非递归日期骨架；"
        "当前等级与活跃用户分布使用截至昨天的最新完整历史日。"
    )

    assert seed.DATE_PARTITION_SKILL_DESCRIPTION == expected
    assert seed.DATE_PARTITION_SKILL["description"] == expected
    assert _date_skill()["description"] == expected


def test_xiuxian_payment_skill_is_scoped_and_keeps_date_skill() -> None:
    assert seed.TENANT_ID == 7482727237662281728
    assert seed.DATASOURCE_ID == 6
    assert len(_skills()) == 13
    assert any(
        "data-skill-source:xiuxian:date-partition-aggregation" in skill["prompt"]
        for skill in seed.DATA_SKILLS
    )
    assert _payment_skill()["name"] == "修仙 ServerPayLog 收入与 ARPU/ARPPU"


def test_xiuxian_payment_skill_uses_serverpaylog_authority() -> None:
    prompt = _payment_skill()["prompt"]

    assert "event = 'ServerPayLog'" in prompt
    assert "personal.money" in prompt
    assert "personal.orderId" in prompt
    assert "personal.productid" in prompt
    assert "COUNT(DISTINCT uid)" in prompt
    assert "data-skill-source:xiuxian:paybuyret-monetization-arppu" not in prompt
    assert '"forbidden_sql_contains":["PayBuyRet","ed_money","paytotal"]' in prompt


def test_xiuxian_payment_skill_description_has_cumulative_payer_retrieval_anchor() -> None:
    assert "按渠道统计累计付费用户数" in _payment_skill()["description"]


def test_payer_penetration_description_has_cumulative_payer_retrieval_anchor() -> None:
    assert "按渠道统计累计付费用户数" in _payer_penetration_skill()["description"]


def test_payment_and_payer_skills_fit_runtime_prompt_budget_without_legacy_blocks() -> None:
    payment = _payment_skill()
    payer = _payer_penetration_skill()
    estimated_chars = sum(
        len(skill["name"])
        + len(skill["description"])
        + len(skill["prompt"])
        + 96
        for skill in (payment, payer)
    )

    assert estimated_chars <= 18_000
    assert "paytotal" not in payer["prompt"]
    for view_id in seed.PAYER_PROMPT_EXCLUDED_VIEW_IDS:
        assert f"<!-- dashboard-sql:{view_id} -->" not in payer["prompt"]


def test_payer_count_does_not_require_unrelated_money_field() -> None:
    prompt = _payment_skill()["prompt"]
    correct_sql = """
    SELECT COUNT(DISTINCT e.uid) AS `付费用户数`
    FROM `event` e
    WHERE e.dt = 20260726
      AND e.event = 'ServerPayLog'
    """

    assert _data_skill_sql_validation_violation(
        "统计昨天的付费用户数", correct_sql, prompt
    ) is None


def test_payment_amount_still_requires_money_field() -> None:
    prompt = _payment_skill()["prompt"]
    invalid_sql = """
    SELECT COUNT(*) AS `付费金额`
    FROM `event` e
    WHERE e.dt = 20260726
      AND e.event = 'ServerPayLog'
    """

    violation = _data_skill_sql_validation_violation(
        "统计昨天的付费金额", invalid_sql, prompt
    )
    assert violation is not None
    assert violation.missing_required_contains == ("$.money",)


def test_xiuxian_payment_skill_documents_first_day_payment_snapshot_semantics() -> None:
    prompt = _payment_skill()["prompt"]

    assert "新增首日付费金额" in prompt
    assert "UserRegister" in prompt
    assert "注册日 `user` 快照" in prompt
    assert "pay.pay1" in prompt
    assert "YYYYMMDD" in prompt
    assert "SIGNED" in prompt
    assert "UNSIGNED" in prompt


def test_xiuxian_payment_skill_allows_verified_first_day_payment_sql() -> None:
    prompt = _payment_skill()["prompt"]
    correct_sql = """
    SELECT e.dt,
           SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.pay1')) AS DECIMAL(18, 4)))
             AS `新增首日付费金额`
    FROM `event` e
    JOIN `user` u ON u.prod = e.prod AND u.dt = e.dt AND u.uid = e.uid
    WHERE e.event = 'UserRegister'
      AND CAST(JSON_UNQUOTE(JSON_EXTRACT(u.userinfo, '$.regdate')) AS SIGNED) = e.dt
    GROUP BY e.dt
    """

    assert _data_skill_sql_validation_error(
        "查看最近30天新增首日付费金额",
        correct_sql,
        prompt,
    ) is None


def test_xiuxian_payment_skill_rejects_unsigned_first_day_payment_sql() -> None:
    prompt = _payment_skill()["prompt"]
    wrong_sql = """
    SELECT e.dt,
           SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.pay1')) AS DECIMAL(18, 4)))
             AS `新增首日付费金额`
    FROM `event` e
    JOIN `user` u ON u.prod = e.prod AND u.dt = e.dt AND u.uid = e.uid
    WHERE e.event = 'UserRegister'
      AND CAST(JSON_UNQUOTE(JSON_EXTRACT(u.userinfo, '$.regdate')) AS UNSIGNED) = e.dt
    GROUP BY e.dt
    """

    assert _data_skill_sql_validation_error(
        "查看最近30天新增首日付费金额",
        wrong_sql,
        prompt,
    ) == (
        "修仙新增首日付费金额必须按 UserRegister 去重用户，读取注册日 user 快照的 "
        "pay.pay1；dt/regdate 为 YYYYMMDD，当前方言必须 CAST AS SIGNED，不能使用 UNSIGNED。"
    )


def test_xiuxian_date_skill_uses_dynamic_bounds_without_max_date_scan() -> None:
    """通用日期口径根据问题动态生成边界，不扫描最大分区。"""
    prompt = _date_skill()["prompt"]

    assert "SELECT MAX(" not in prompt.upper()
    assert "WITH bounds AS" not in prompt
    assert "CROSS JOIN bounds" not in prompt
    assert "## 标准聚合 SQL" not in prompt
    assert "未指定日期窗口时，默认查询截至昨天的最近 28 个自然日" in prompt
    assert "用户指定相对日期窗口" in prompt
    assert "用户指定绝对起止日期" in prompt
    assert "DATE_SUB(CURDATE(), INTERVAL 29 DAY)" in prompt
    assert "DATE_SUB(CURDATE(), INTERVAL 1 DAY)" in prompt
    assert "禁止使用 `MAX(dt)`" in prompt


def test_date_skill_contains_non_recursive_spine() -> None:
    prompt = seed.DATE_PARTITION_SKILL["prompt"]

    assert "day_offsets" in prompt
    assert "SELECT 0 AS day_offset" in prompt
    assert "UNION ALL SELECT 14" in prompt
    assert "WITH RECURSIVE" not in prompt
    assert "读取 `event`、`user` 时仍必须在各自表别名上直接写 `dt` 分区条件" in prompt
    assert "日期骨架只负责补齐输出日期" in prompt


def test_payment_skill_contains_three_repair_examples() -> None:
    prompt = _payment_skill()["prompt"]

    assert "修复示例：按渠道付费用户" in prompt
    assert "$.mediaSource" in prompt
    assert "修复示例：等级段人均付费" in prompt
    assert "JSON_EXTRACT(u.lastinfo, '$.level')" in prompt
    assert "LEFT JOIN user_payment" in prompt
    assert "修复示例：最新完整数据日核心指标" in prompt
    assert "event = 'ServerPayLog'" in prompt
    assert "$.money" in prompt


def test_repair_examples_use_only_authoritative_payment_fields() -> None:
    examples = seed.SERVERPAYLOG_REPAIR_EXAMPLES

    assert examples.count("修复示例：") == 3
    assert "PayBuyRet" not in examples
    assert "ed_money" not in examples
    assert "paytotal" not in examples
    assert "personal, '$.money'" in examples
    assert "COUNT(DISTINCT e.uid)" in examples
    assert "COUNT(DISTINCT ul.uid)" in examples


def test_repair_examples_pass_real_data_skill_sql_validator() -> None:
    prompt = _payment_skill()["prompt"]
    cases = (
        ("按渠道付费用户", "查看最近15天按渠道付费用户和付费金额"),
        ("等级段人均付费", "查看最新完整数据日各等级段人均付费金额"),
        (
            "最新完整数据日核心指标",
            "查看最新完整数据日 DAU、新增用户数、付费用户和付费金额",
        ),
    )

    for title, question in cases:
        sql = _repair_example_sql(title)
        assert _data_skill_sql_validation_violation(question, sql, prompt) is None
        assert _data_skill_sql_validation_error(question, sql, prompt) is None


def test_seed_prompts_use_single_managed_section_at_prompt_end() -> None:
    date_prompt = seed.DATE_PARTITION_SKILL["prompt"]
    payment_prompt = _payment_skill()["prompt"]

    assert date_prompt.endswith(seed.DATE_SECTION_END_MARKER)
    assert date_prompt.count(seed.DATE_SECTION_MARKER) == 1
    assert date_prompt.count(seed.DATE_SECTION_END_MARKER) == 1
    assert payment_prompt.endswith(seed.SERVERPAYLOG_SECTION_END_MARKER)
    assert payment_prompt.count(seed.SERVERPAYLOG_SECTION_MARKER) == 1
    assert payment_prompt.count(seed.SERVERPAYLOG_SECTION_END_MARKER) == 1
    assert payment_prompt.rfind("<!-- dashboard-sql:") < payment_prompt.index(
        seed.SERVERPAYLOG_SECTION_MARKER
    )


def test_xiuxian_date_skill_rejects_max_dt_partition_probe() -> None:
    """修仙日期口径禁止通过 MAX(dt) 全表扫描探测最大业务日期。"""
    prompt = _date_skill()["prompt"]
    message = "修仙数据源禁止使用 MAX(dt) 扫描最大业务日期；请根据用户时间范围或默认最近 28 天直接生成 dt 分区边界。"

    assert _data_skill_sql_validation_error(
        "查看近七天日活",
        "SELECT MAX(dt) AS max_dt FROM event",
        prompt,
    ) == message
    assert _data_skill_sql_validation_error(
        "查看近七天日活",
        "SELECT MAX(e.dt) AS max_dt FROM event e",
        prompt,
    ) == message


def test_xiuxian_date_skill_allows_non_partition_max_aggregate() -> None:
    """禁止分区探测不能误伤普通 MAX 聚合。"""
    prompt = _date_skill()["prompt"]
    sql = "SELECT e.dt, MAX(e.level) FROM event e WHERE e.dt = 20260714 GROUP BY e.dt"

    assert _data_skill_sql_validation_error("查看昨日最高等级", sql, prompt) is None


def test_xiuxian_date_skill_rejects_bounds_cte_join_for_partition_filter() -> None:
    """修仙日期口径禁止通过 bounds CTE 关联事件大表。"""
    prompt = _date_skill()["prompt"]
    wrong_sql = """
    WITH bounds AS (
        SELECT
            CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED) AS start_dt,
            CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS end_dt
    ),
    daily_active AS (
        SELECT e.dt, COUNT(DISTINCT e.uid) AS dau
        FROM event e
        CROSS JOIN bounds b
        WHERE e.dt BETWEEN b.start_dt AND b.end_dt
        GROUP BY e.dt
    )
    SELECT * FROM daily_active
    """

    assert _data_skill_sql_validation_error(
        "使用堆叠面积图展示近七天各平台的日活跃用户数变化",
        wrong_sql,
        prompt,
    ) == (
        "修仙数据源禁止使用 bounds CTE 关联事件或快照大表；"
        "请把动态日期表达式直接写入每个表别名自己的 dt 分区条件。"
    )


def test_xiuxian_date_skill_rejects_current_day_in_28_complete_day_spine() -> None:
    """最近 28 个完整自然日不得把今天放进日期骨架。"""
    prompt = _date_skill()["prompt"]
    wrong_sql = """
    WITH day_offsets AS (
        SELECT 0 AS day_offset UNION ALL SELECT 1 UNION ALL SELECT 27
    ), date_spine AS (
        SELECT CAST(
            DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL day_offset DAY), '%Y%m%d')
            AS SIGNED
        ) AS dt
        FROM day_offsets
    ), daily_active AS (
        SELECT e.dt, COUNT(DISTINCT e.uid) AS dau
        FROM event e
        WHERE e.dt BETWEEN
              CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 27 DAY), '%Y%m%d') AS SIGNED)
              AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
        GROUP BY e.dt
    )
    SELECT * FROM date_spine
    LEFT JOIN daily_active USING (dt)
    """

    assert _data_skill_sql_validation_error(
        "检查最近28个自然日新增、活跃、付费用户和付费金额是否存在缺失或全零日期",
        wrong_sql,
        prompt,
    ) == (
        "修仙最近 28 个完整自然日必须使用 CURDATE()-28 至 CURDATE()-1；"
        "日期骨架不得从今天开始，offset=0 必须锚定昨天。"
    )


def test_xiuxian_date_skill_allows_yesterday_anchored_28_complete_day_spine() -> None:
    """日期骨架锚定昨天且事实表覆盖完整 28 天时允许执行。"""
    prompt = _date_skill()["prompt"]
    correct_sql = """
    WITH day_offsets AS (
        SELECT 0 AS day_offset UNION ALL SELECT 1 UNION ALL SELECT 27
    ), date_spine AS (
        SELECT CAST(
            DATE_FORMAT(
                DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 DAY), INTERVAL day_offset DAY),
                '%Y%m%d'
            ) AS SIGNED
        ) AS dt
        FROM day_offsets
    ), daily_active AS (
        SELECT e.dt, COUNT(DISTINCT e.uid) AS dau
        FROM event e
        WHERE e.dt BETWEEN
              CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 28 DAY), '%Y%m%d') AS SIGNED)
              AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
        GROUP BY e.dt
    )
    SELECT * FROM date_spine
    LEFT JOIN daily_active USING (dt)
    """

    assert _data_skill_sql_validation_error(
        "检查最近28个自然日新增、活跃、付费用户和付费金额是否存在缺失或全零日期",
        correct_sql,
        prompt,
    ) is None


def test_xiuxian_player_snapshot_skill_rejects_snapshot_users_as_active_users() -> None:
    """user 快照只提供等级标签，不能直接充当活跃人群。"""
    prompt = _player_snapshot_skill()["prompt"]
    wrong_sql = """
    WITH user_level AS (
        SELECT u.uid,
               JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.level')) AS level_value
        FROM user u
        WHERE u.dt = 20260720
    )
    SELECT level_value AS 等级段,
           COUNT(DISTINCT uid) AS 活跃用户数
    FROM user_level
    GROUP BY level_value
    """

    assert _data_skill_sql_validation_error(
        "统计最新完整数据日各玩家等级段的活跃用户数",
        wrong_sql,
        prompt,
    ) == (
        "修仙按等级分析活跃用户时，活跃人群必须来自 UserActive 去重 uid；"
        "user 快照只提供目标日期的等级标签，不能直接统计为活跃用户。"
    )


def test_xiuxian_player_snapshot_skill_allows_useractive_joined_to_level_snapshot() -> None:
    """先固定 UserActive 人群，再关联同日等级快照时允许执行。"""
    prompt = _player_snapshot_skill()["prompt"]
    correct_sql = """
    WITH active_users AS (
        SELECT DISTINCT e.uid
        FROM event e
        WHERE e.dt = 20260720
          AND e.event = 'UserActive'
    ), user_level AS (
        SELECT u.uid,
               JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.level')) AS level_value
        FROM user u
        WHERE u.dt = 20260720
    )
    SELECT ul.level_value AS 等级段,
           COUNT(DISTINCT au.uid) AS 活跃用户数
    FROM active_users au
    JOIN user_level ul ON ul.uid = au.uid
    GROUP BY ul.level_value
    """

    assert _data_skill_sql_validation_error(
        "统计最新完整数据日各玩家等级段的活跃用户数",
        correct_sql,
        prompt,
    ) is None


def test_xiuxian_payment_skill_rejects_paybuyret_revenue_sql() -> None:
    prompt = _payment_skill()["prompt"]
    wrong_sql = """
    SELECT e.dt,
           SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_money')) AS DECIMAL(18, 4)))
             / NULLIF(COUNT(DISTINCT e.uid), 0) AS ARPPU
    FROM event e
    WHERE e.event = 'PayBuyRet'
    GROUP BY e.dt
    """

    assert _data_skill_sql_validation_error("查看近七天的 ARPPU", wrong_sql, prompt) == (
        "修仙收入、ARPU 和 ARPPU 必须使用 ServerPayLog 的 personal.money 与去重 uid；"
        "PayBuyRet、ed_money 和 paytotal 不能作为真实收入来源。"
    )


def test_xiuxian_payment_skill_rejects_non_distinct_arppu_denominator() -> None:
    prompt = _payment_skill()["prompt"]
    wrong_sql = """
    SELECT e.dt,
           SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')) AS DECIMAL(18, 4)))
             / NULLIF(COUNT(*), 0) AS ARPPU
    FROM `event` e
    WHERE e.event = 'ServerPayLog'
    GROUP BY e.dt
    """

    assert _data_skill_sql_validation_error("查看近七天的 ARPPU", wrong_sql, prompt) == (
        "修仙付费用户数以及 ARPU/ARPPU 分母必须使用 ServerPayLog 并按 uid 去重；"
        "仅统计人数时不要求读取金额字段，PayBuyRet、ed_money 和 paytotal "
        "不能作为付费用户来源。"
    )


def test_xiuxian_payment_skill_allows_verified_serverpaylog_arppu_sql() -> None:
    prompt = _payment_skill()["prompt"]
    correct_sql = """
    SELECT e.dt,
           SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')) AS DECIMAL(18, 4)))
             / NULLIF(COUNT(DISTINCT e.uid), 0) AS ARPPU
    FROM `event` e
    WHERE e.event = 'ServerPayLog'
      AND CAST(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')) AS DECIMAL(18, 4)) > 0
    GROUP BY e.dt
    """

    assert _data_skill_sql_validation_error("查看近七天的 ARPPU", correct_sql, prompt) is None


def test_xiuxian_payment_skill_allows_serverpaylog_revenue_without_payer_count() -> None:
    prompt = _payment_skill()["prompt"]
    correct_sql = """
    SELECT e.dt,
           SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')) AS DECIMAL(18, 4))) AS revenue
    FROM `event` e
    WHERE e.event = 'ServerPayLog'
    GROUP BY e.dt
    """

    assert _data_skill_sql_validation_error("查看近七天收入", correct_sql, prompt) is None
