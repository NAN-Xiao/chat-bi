"""Data Skill 冲突修复的真实召回与 SQL 校验组合回归。"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from apps.chat.curd import custom_prompt as custom_prompt_crud
from apps.chat.curd.custom_prompt import find_data_skills
from apps.chat.task.llm import _data_skill_sql_validation_violation


ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import seed_flam_first_zombie_data_skills as flam_seed  # noqa: E402
import seed_platform_date_field_usage_skill as date_field_seed  # noqa: E402
import seed_platform_realtime_event_table_skill as realtime_seed  # noqa: E402
import seed_xiuxian_data_skills as xiuxian_seed  # noqa: E402
from xiuxian_dashboard_skill_catalog import EXPECTED_VIEW_IDS  # noqa: E402
from xiuxian_dashboard_snapshot import DashboardSnapshot  # noqa: E402


FLAM_TENANT_ID = flam_seed.TENANT_ID
XIUXIAN_TENANT_ID = xiuxian_seed.TENANT_ID
XIUXIAN_OWNER_ID = 7482253745313550336


class _FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self.rows)


class _QueryAwareFakeSession:
    """模拟 custom_prompt SQL 的可见性过滤，排序与召回仍走真实函数。"""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def execute(self, statement, params=None, *args, **kwargs) -> _FakeResult:
        sql = str(statement)
        params = params or {}
        if "FROM core_table" in sql:
            return _FakeResult([])
        if "FROM custom_prompt" not in sql:
            return _FakeResult([])

        tenant_id = int(params["tenant_id"])
        current_user_id = params.get("current_user_id")
        target_scope = params.get("target_scope")
        selected = []
        for row in self.rows:
            if row.get("type") != "DATA_SKILL" or not row.get("active", False):
                continue
            visibility = row.get("visibility_scope")
            visible = bool(row.get("visible", True))
            allowed = (
                visibility == "PLATFORM_PUBLIC" and visible
                or visibility == "ADMIN_PUBLIC"
                and int(row.get("tenant_id")) == tenant_id
                and visible
                or visibility == "USER_PRIVATE"
                and current_user_id is not None
                and str(row.get("create_by")) == str(current_user_id)
            )
            if not allowed:
                continue
            row_scope = row.get("target_scope")
            if row_scope not in {target_scope, "ALL", None}:
                continue
            selected.append(row)
        return _FakeResult(selected)


def _row(
    skill_id: int,
    skill: dict[str, str],
    *,
    tenant_id: int,
    visibility_scope: str,
    specific_ds: bool,
    datasource_ids: list[int],
    create_by: int | None = None,
    active: bool = True,
    visible: bool = True,
) -> dict[str, Any]:
    return {
        "id": skill_id,
        "tenant_id": tenant_id,
        "name": skill["name"],
        "description": skill.get("description", ""),
        "prompt": skill["prompt"],
        "embedding": None,
        "embedding_signature": None,
        "specific_ds": specific_ds,
        "datasource_ids": datasource_ids,
        "ai_model_id": None,
        "create_by": create_by,
        "visibility_scope": visibility_scope,
        "target_scope": "ALL",
        "type": "DATA_SKILL",
        "active": active,
        "visible": visible,
    }


@lru_cache(maxsize=1)
def _xiuxian_skills() -> tuple[dict[str, str], ...]:
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
                    XIUXIAN_TENANT_ID,
                    6,
                    json.dumps(canvas, ensure_ascii=False),
                )
            )
        )
    return tuple(xiuxian_seed.build_data_skills(dashboards))


def _skill_with_marker(skills: tuple[dict[str, str], ...], marker: str) -> dict[str, str]:
    return next(skill for skill in skills if marker in skill["prompt"])


def _fixture_rows() -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    name_to_id: dict[str, int] = {}

    for index, skill in enumerate(flam_seed.DATA_SKILLS):
        skill_id = 225 if index == 0 else 1000 + index
        rows.append(
            _row(
                skill_id,
                skill,
                tenant_id=FLAM_TENANT_ID,
                visibility_scope="ADMIN_PUBLIC",
                specific_ds=True,
                datasource_ids=[3],
            )
        )
        name_to_id[skill["name"]] = skill_id

    xiuxian_skills = _xiuxian_skills()
    marker_ids = {
        "data-skill-source:xiuxian:date-partition-aggregation": 255,
        "data-skill-source:xiuxian:serverpaylog-monetization-arppu": 257,
        "data-skill-source:xiuxian:dashboard:payer-penetration": 276,
        "data-skill-source:xiuxian:dashboard:player-snapshot": 278,
    }
    next_id = 1100
    for skill in xiuxian_skills:
        skill_id = next(
            (target_id for marker, target_id in marker_ids.items() if marker in skill["prompt"]),
            next_id,
        )
        if skill_id == next_id:
            next_id += 1
        rows.append(
            _row(
                skill_id,
                skill,
                tenant_id=XIUXIAN_TENANT_ID,
                visibility_scope="ADMIN_PUBLIC",
                specific_ds=True,
                datasource_ids=[6],
            )
        )
        name_to_id[skill["name"]] = skill_id

    rows.append(
        _row(
            282,
            realtime_seed.SKILL,
            tenant_id=1,
            visibility_scope="PLATFORM_PUBLIC",
            specific_ds=False,
            datasource_ids=[],
        )
    )
    name_to_id[realtime_seed.SKILL["name"]] = 282

    rows.append(
        _row(
            234,
            {
                "name": "平台通用 Data Skill：取数据的约束",
                "description": "取数的优化",
                "prompt": "不要全表扫描 应该先用时间过滤再查询对应数据",
            },
            tenant_id=1,
            visibility_scope="PLATFORM_PUBLIC",
            specific_ds=False,
            datasource_ids=[],
            create_by=1,
            active=False,
            visible=False,
        )
    )
    name_to_id["平台通用 Data Skill：取数据的约束"] = 234

    rows.append(
        _row(
            280,
            {
                "name": "示例：修仙 资源获取与消耗统计口径",
                "description": "定义 ResourceChange 资源获取、消耗和净变化统计口径。",
                "prompt": "ResourceChange 资源获取量、消耗量与净变化；资源分析仅适用于修仙。",
            },
            tenant_id=XIUXIAN_TENANT_ID,
            visibility_scope="USER_PRIVATE",
            specific_ds=True,
            datasource_ids=[6],
            create_by=XIUXIAN_OWNER_ID,
        )
    )
    name_to_id["示例：修仙 资源获取与消耗统计口径"] = 280
    return rows, name_to_id


def _selected_ids(skill_logs: list[str], name_to_id: dict[str, int]) -> set[int]:
    selected = set()
    for log in skill_logs:
        name = log.split("\n", 1)[0].removeprefix("名称：")
        selected.add(name_to_id[name])
    return selected


def test_realtime_selection_skill_requires_today_date_template_for_time_series() -> None:
    prompt = realtime_seed.SKILL["prompt"]

    assert "{{dashboard_start_yyyymmdd}}" in prompt
    assert "{{dashboard_end_yyyymmdd}}" in prompt
    assert '"preset":"today"' in prompt
    assert "非 `metric`" in prompt
    assert "执行阶段" in prompt


def test_date_field_skill_parameterizes_partition_roles_without_policy_prerequisite() -> None:
    prompt = date_field_seed.SKILL["prompt"]

    assert "`partition_date`" in prompt
    assert "`realtime_partition`" in prompt
    assert "{{dashboard_start_yyyymmdd}}" in prompt
    assert "{{dashboard_end_yyyymmdd}}" in prompt
    assert "默认实时查询不套用历史日期 pivot" not in prompt
    assert "不是使用日期 token 或返回 `date_filter` 的前置条件" in prompt


SCENARIOS = (
    (
        3,
        FLAM_TENANT_ID,
        "今天实时付费趋势",
        {225, 282},
        """
        SELECT e.dt, HOUR(FROM_UNIXTIME(e.event_time / 1000 + 28800)) AS hour_no,
               SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')) AS DECIMAL(18, 4))) AS pay_amount
        FROM event_realtime e
        WHERE e.event = 'ServerPayLog' AND e.dt = 20260727
        GROUP BY e.dt, HOUR(FROM_UNIXTIME(e.event_time / 1000 + 28800))
        """,
    ),
    (
        6,
        XIUXIAN_TENANT_ID,
        "按渠道统计累计付费用户数",
        {257, 276, 282},
        """
        SELECT JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.mediaSource')) AS channel,
               COUNT(DISTINCT e.uid) AS payer_users
        FROM event e
        WHERE e.dt BETWEEN 20260701 AND 20260726
          AND e.event = 'ServerPayLog'
        GROUP BY JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.mediaSource'))
        """,
    ),
    (
        6,
        XIUXIAN_TENANT_ID,
        "统计昨天的付费用户数",
        {257, 282},
        """
        SELECT COUNT(DISTINCT e.uid) AS payer_users
        FROM event e
        WHERE e.dt = 20260726 AND e.event = 'ServerPayLog'
        """,
    ),
    (
        6,
        XIUXIAN_TENANT_ID,
        "当前等级的活跃用户分布",
        {255, 278, 282},
        """
        SELECT JSON_UNQUOTE(JSON_EXTRACT(u.personal, '$.level')) AS level_no,
               COUNT(DISTINCT e.uid) AS active_users
        FROM event e
        JOIN user u ON u.uid = e.uid AND u.dt = e.dt
        WHERE e.dt = 20260726 AND e.event = 'UserActive'
        GROUP BY JSON_UNQUOTE(JSON_EXTRACT(u.personal, '$.level'))
        """,
    ),
)


@pytest.mark.parametrize(
    ("datasource", "tenant_id", "question", "expected_ids", "sql"), SCENARIOS
)
def test_conflict_scenarios_use_expected_recall_and_pass_sql_validation(
    monkeypatch,
    datasource: int,
    tenant_id: int,
    question: str,
    expected_ids: set[int],
    sql: str,
) -> None:
    rows, name_to_id = _fixture_rows()
    monkeypatch.setattr(custom_prompt_crud.settings, "EMBEDDING_ENABLED", False)
    monkeypatch.setattr(
        custom_prompt_crud,
        "_authorized_datasource_tables",
        lambda *_args: {"event", "event_realtime", "user"},
    )

    skill_text, skill_logs, _model = find_data_skills(
        _QueryAwareFakeSession(rows),
        datasource=datasource,
        tenant_id=tenant_id,
        current_user_id=XIUXIAN_OWNER_ID,
        current_user=SimpleNamespace(id=XIUXIAN_OWNER_ID),
        question=question,
    )
    selected_ids = _selected_ids(skill_logs, name_to_id)

    assert expected_ids.issubset(selected_ids)
    assert 234 not in selected_ids
    if datasource == 3:
        assert 280 not in selected_ids
    assert _data_skill_sql_validation_violation(question, sql, skill_text) is None


def test_realtime_payment_conflict_sql_is_rejected(monkeypatch) -> None:
    rows, _name_to_id = _fixture_rows()
    monkeypatch.setattr(custom_prompt_crud.settings, "EMBEDDING_ENABLED", False)
    monkeypatch.setattr(
        custom_prompt_crud,
        "_authorized_datasource_tables",
        lambda *_args: {"event", "event_realtime", "user"},
    )
    question = "今天实时付费趋势"
    skill_text, _logs, _model = find_data_skills(
        _QueryAwareFakeSession(rows),
        datasource=3,
        tenant_id=FLAM_TENANT_ID,
        current_user_id=XIUXIAN_OWNER_ID,
        current_user=SimpleNamespace(id=XIUXIAN_OWNER_ID),
        question=question,
    )

    violation = _data_skill_sql_validation_violation(
        question,
        "SELECT COUNT(*) FROM event e WHERE e.event='ServerPayLog' AND e.dt=20260727",
        skill_text,
    )
    assert violation is not None
    assert "event_realtime" in violation.message


def test_explicit_historical_realtime_query_keeps_history_table(monkeypatch) -> None:
    rows, name_to_id = _fixture_rows()
    monkeypatch.setattr(custom_prompt_crud.settings, "EMBEDDING_ENABLED", False)
    monkeypatch.setattr(
        custom_prompt_crud,
        "_authorized_datasource_tables",
        lambda *_args: {"event", "event_realtime", "user"},
    )

    question = "昨天实时付费趋势"
    skill_text, skill_logs, _model = find_data_skills(
        _QueryAwareFakeSession(rows),
        datasource=6,
        tenant_id=XIUXIAN_TENANT_ID,
        current_user_id=XIUXIAN_OWNER_ID,
        current_user=SimpleNamespace(id=XIUXIAN_OWNER_ID),
        question=question,
    )

    assert 282 in _selected_ids(skill_logs, name_to_id)
    assert (
        _data_skill_sql_validation_violation(
            question,
            "SELECT e.dt, COUNT(*) FROM event e "
            "WHERE e.dt = 20260804 GROUP BY e.dt",
            skill_text,
        )
        is None
    )


@pytest.mark.parametrize("datasource, expected_visible", [(6, True), (3, False), (1, False)])
def test_private_skill_280_is_visible_only_to_owner_on_datasource_6(
    monkeypatch, datasource: int, expected_visible: bool
) -> None:
    rows, name_to_id = _fixture_rows()
    monkeypatch.setattr(custom_prompt_crud.settings, "EMBEDDING_ENABLED", False)

    _skill_text, skill_logs, _model = find_data_skills(
        _QueryAwareFakeSession(rows),
        datasource=datasource,
        tenant_id=XIUXIAN_TENANT_ID,
        current_user_id=XIUXIAN_OWNER_ID,
        question="统计资源获取与消耗",
    )

    assert (280 in _selected_ids(skill_logs, name_to_id)) is expected_visible
