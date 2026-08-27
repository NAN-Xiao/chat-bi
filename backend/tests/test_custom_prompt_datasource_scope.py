"""
脚本说明：这个脚本是测试文件，用来验证 Data Skills 的项目生效范围。
"""
from __future__ import annotations

from typing import Any

from apps.chat.curd import custom_prompt as custom_prompt_crud
from apps.chat.curd.custom_prompt import find_data_skills


class _FakeMappings:
    """
    类说明：_FakeMappings 是测试用的轻量结果对象，模拟 SQLAlchemy mappings 结果。
    """

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeResult:
    """
    类说明：_FakeResult 是测试用的轻量结果对象，模拟 SQLAlchemy execute 结果。
    """

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self._rows)


class _FakeSession:
    """
    类说明：_FakeSession 让 find_data_skills 能在不连接数据库的情况下测试过滤逻辑。
    """

    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        table_names: list[str] | None = None,
    ) -> None:
        self._rows = rows
        self._table_names = table_names or []

    def execute(self, statement, *args, **kwargs) -> _FakeResult:
        if "FROM core_table" in str(statement):
            return _FakeResult(
                [{"table_name": table_name} for table_name in self._table_names]
            )
        return _FakeResult(self._rows)


def _skill_row(
        *,
        skill_id: int,
        name: str,
        visibility_scope: str = "PLATFORM_PUBLIC",
        specific_ds: bool = False,
        datasource_ids: list[int] | None = None,
        prompt: str | None = None,
) -> dict[str, Any]:
    """
    是什么：_skill_row 是一段测试代码，用来构造 custom_prompt 查询结果。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    return {
        "id": skill_id,
        "tenant_id": 1,
        "name": name,
        "description": "",
        "prompt": prompt or f"{name} prompt",
        "embedding": None,
        "embedding_signature": None,
        "specific_ds": specific_ds,
        "datasource_ids": datasource_ids or [],
        "ai_model_id": None,
        "create_by": 1,
        "visibility_scope": visibility_scope,
    }


def _external_mcp_skill_prompt(name: str) -> str:
    return f'''<!-- saas-skill:{{
  "id": "external_mcp_skill",
  "name": "{name}",
  "intent": ["告警数量"],
  "sources": [{{"name": "alerts", "type": "external_mcp", "tool": "alerts.count"}}]
}} -->
{name} prompt'''


def _required_tables_skill_prompt() -> str:
    return '''<!-- data-skill-requires-tables:["event","event_realtime"] -->
当天实时事件选表规则'''


def test_find_data_skills_can_temporarily_exclude_workspace_skills() -> None:
    workspace_skill = _skill_row(
        skill_id=1,
        name="工作空间口径",
        visibility_scope="ADMIN_PUBLIC",
    )
    platform_skill = _skill_row(
        skill_id=2,
        name="平台通用规则",
        visibility_scope="PLATFORM_PUBLIC",
    )

    skill_text, skill_list, _ = find_data_skills(
        _FakeSession([workspace_skill, platform_skill]),
        datasource=7,
        tenant_id=10,
        current_user_id=1,
        current_user=object(),
        question="查看收入",
        include_workspace_data_skills=False,
    )

    assert "工作空间口径 prompt" not in skill_text
    assert "平台通用规则 prompt" in skill_text
    assert [item.split("\n", 1)[0] for item in skill_list] == ["名称：平台通用规则"]


def test_find_data_skills_excludes_platform_skill_when_required_table_is_missing(
    monkeypatch,
) -> None:
    realtime_skill = _skill_row(
        skill_id=1,
        name="平台实时事件选表",
        prompt=_required_tables_skill_prompt(),
    )

    current_user = object()
    monkeypatch.setattr(
        custom_prompt_crud,
        "_authorized_datasource_tables",
        lambda *_args: {"event"},
    )

    skill_text, skill_list, _ = find_data_skills(
        _FakeSession([realtime_skill]),
        datasource=7,
        tenant_id=10,
        current_user_id=1,
        current_user=current_user,
        question="今天按小时收入",
    )

    assert "当天实时事件选表规则" not in skill_text
    assert skill_list == []


def test_find_data_skills_keeps_platform_skill_when_all_required_tables_exist(
    monkeypatch,
) -> None:
    realtime_skill = _skill_row(
        skill_id=1,
        name="平台实时事件选表",
        prompt=_required_tables_skill_prompt(),
    )

    current_user = object()
    monkeypatch.setattr(
        custom_prompt_crud,
        "_authorized_datasource_tables",
        lambda *_args: {"event", "event_realtime"},
    )

    skill_text, skill_list, _ = find_data_skills(
        _FakeSession([realtime_skill]),
        datasource=7,
        tenant_id=10,
        current_user_id=1,
        current_user=current_user,
        question="今天按小时收入",
    )

    assert "当天实时事件选表规则" in skill_text
    assert [item.split("\n", 1)[0] for item in skill_list] == [
        "名称：平台实时事件选表"
    ]


def test_find_data_skills_fails_closed_without_user_for_required_tables() -> None:
    realtime_skill = _skill_row(
        skill_id=1,
        name="平台实时事件选表",
        prompt=_required_tables_skill_prompt(),
    )

    skill_text, skill_list, _ = find_data_skills(
        _FakeSession([realtime_skill]),
        datasource=7,
        tenant_id=10,
        current_user_id=1,
        current_user=None,
        question="今天按小时收入",
    )

    assert "当天实时事件选表规则" not in skill_text
    assert skill_list == []


def test_find_data_skills_excludes_external_mcp_skill_without_workspace_binding(monkeypatch) -> None:
    external_skill = _skill_row(
        skill_id=1,
        name="平台外部 MCP 告警 Skill",
        prompt=_external_mcp_skill_prompt("平台外部 MCP 告警 Skill"),
    )
    foundation = _skill_row(skill_id=2, name="平台通用 SQL 规范")
    foundation["prompt"] = "<!-- platform-foundation-skill:sql:v1 -->\n平台 SQL 规范"
    monkeypatch.setattr(
        custom_prompt_crud,
        "get_bound_external_mcp_id_for_tenant",
        lambda *_args, **_kwargs: None,
        raising=False,
    )

    skill_text, skill_list, _ = find_data_skills(
        _FakeSession([external_skill, foundation]),
        datasource=7,
        tenant_id=10,
        current_user_id=1,
        question="查看收入和告警数量",
    )

    assert "平台外部 MCP 告警 Skill prompt" not in skill_text
    assert "平台 SQL 规范" in skill_text
    assert [item.split("\n", 1)[0] for item in skill_list] == ["名称：平台通用 SQL 规范"]


def test_find_data_skills_keeps_external_mcp_skill_with_workspace_binding(monkeypatch) -> None:
    external_skill = _skill_row(
        skill_id=1,
        name="平台外部 MCP 告警 Skill",
        prompt=_external_mcp_skill_prompt("平台外部 MCP 告警 Skill"),
    )
    monkeypatch.setattr(
        custom_prompt_crud,
        "get_bound_external_mcp_id_for_tenant",
        lambda *_args, **_kwargs: 201,
        raising=False,
    )

    skill_text, skill_list, _ = find_data_skills(
        _FakeSession([external_skill]),
        datasource=7,
        tenant_id=10,
        current_user_id=1,
        question="查看告警数量",
    )

    assert "平台外部 MCP 告警 Skill prompt" in skill_text
    assert [item.split("\n", 1)[0] for item in skill_list] == ["名称：平台外部 MCP 告警 Skill"]


def test_platform_foundation_skill_is_not_dropped_by_auto_ranking_limit() -> None:
    foundation = _skill_row(skill_id=1, name="平台通用 SQL 日期与分组规范")
    foundation["prompt"] = (
        "<!-- platform-foundation-skill:sql-date-grouping:v1 -->\n"
        "SELECT 与 GROUP BY 日期表达式必须完全一致。"
    )
    ranked_rows = [
        _skill_row(skill_id=100 + index, name=f"收入趋势分析 {index}")
        for index in range(13)
    ]

    skill_text, _logs, _model = find_data_skills(
        _FakeSession([foundation, *ranked_rows]),
        datasource=501,
        question="收入趋势分析",
        tenant_id=10,
        current_user_id=3,
    )

    assert "platform-foundation-skill:sql-date-grouping:v1" in skill_text


def test_find_data_skills_filters_platform_skill_by_datasource_scope() -> None:
    """
    是什么：test_find_data_skills_filters_platform_skill_by_datasource_scope 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    session = _FakeSession([
        _skill_row(skill_id=1, name="global-platform"),
        _skill_row(skill_id=2, name="project-7-platform", specific_ds=True, datasource_ids=[7]),
        _skill_row(skill_id=3, name="project-8-platform", specific_ds=True, datasource_ids=[8]),
    ])

    skill_text, skill_list, _ = find_data_skills(
        session,
        datasource=7,
        tenant_id=1,
        current_user_id=1,
    )

    assert "global-platform prompt" in skill_text
    assert "project-7-platform prompt" in skill_text
    assert "project-8-platform prompt" not in skill_text
    assert [item.split("\n", 1)[0] for item in skill_list] == [
        "名称：global-platform",
        "名称：project-7-platform",
    ]


def test_find_data_skills_excludes_datasource_scoped_skill_without_current_datasource() -> None:
    """
    是什么：test_find_data_skills_excludes_datasource_scoped_skill_without_current_datasource 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    session = _FakeSession([
        _skill_row(skill_id=1, name="global-platform"),
        _skill_row(skill_id=2, name="project-7-platform", specific_ds=True, datasource_ids=[7]),
    ])

    skill_text, skill_list, _ = find_data_skills(
        session,
        datasource=None,
        tenant_id=1,
        current_user_id=1,
    )

    assert "global-platform prompt" in skill_text
    assert "project-7-platform prompt" not in skill_text
    assert len(skill_list) == 1


def test_find_data_skills_platform_overrides_similar_workspace_and_personal_skills() -> None:
    """
    是什么：test_find_data_skills_platform_overrides_similar_workspace_and_personal_skills 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    session = _FakeSession([
        _skill_row(
            skill_id=1,
            name="收入健康度",
            visibility_scope="PLATFORM_PUBLIC",
        ),
        _skill_row(
            skill_id=2,
            name="工作空间-收入健康度",
            visibility_scope="ADMIN_PUBLIC",
        ),
        _skill_row(
            skill_id=3,
            name="个人-收入健康度",
            visibility_scope="USER_PRIVATE",
        ),
    ])

    skill_text, skill_list, _ = find_data_skills(
        session,
        datasource=7,
        tenant_id=1,
        current_user_id=1,
        question="收入健康度",
    )

    assert "收入健康度 prompt" in skill_text
    assert "工作空间-收入健康度 prompt" not in skill_text
    assert "个人-收入健康度 prompt" not in skill_text
    assert [item.split("\n", 1)[0] for item in skill_list] == ["名称：收入健康度"]


def test_find_data_skills_workspace_overrides_similar_personal_skill_without_platform() -> None:
    """
    是什么：test_find_data_skills_workspace_overrides_similar_personal_skill_without_platform 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    session = _FakeSession([
        _skill_row(
            skill_id=2,
            name="工作空间-留存分析",
            visibility_scope="ADMIN_PUBLIC",
        ),
        _skill_row(
            skill_id=3,
            name="个人-留存分析",
            visibility_scope="USER_PRIVATE",
        ),
    ])

    skill_text, skill_list, _ = find_data_skills(
        session,
        datasource=7,
        tenant_id=1,
        current_user_id=1,
        question="留存分析",
    )

    assert "工作空间-留存分析 prompt" in skill_text
    assert "个人-留存分析 prompt" not in skill_text
    assert [item.split("\n", 1)[0] for item in skill_list] == ["名称：工作空间-留存分析"]


def test_find_data_skills_prefers_datasource_scoped_skill_within_same_scope() -> None:
    """
    是什么：test_find_data_skills_prefers_datasource_scoped_skill_within_same_scope 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    session = _FakeSession([
        _skill_row(
            skill_id=1,
            name="收入健康度",
            visibility_scope="PLATFORM_PUBLIC",
        ),
        _skill_row(
            skill_id=2,
            name="SaaS-收入健康度",
            visibility_scope="PLATFORM_PUBLIC",
            specific_ds=True,
            datasource_ids=[7],
        ),
    ])

    skill_text, skill_list, _ = find_data_skills(
        session,
        datasource=7,
        tenant_id=1,
        current_user_id=1,
        question="收入健康度",
    )

    assert "SaaS-收入健康度 prompt" in skill_text
    assert "收入健康度 prompt" not in skill_text.replace("SaaS-收入健康度 prompt", "")
    assert [item.split("\n", 1)[0] for item in skill_list] == ["名称：SaaS-收入健康度"]


def test_find_data_skills_explicit_personal_selection_is_overridden_by_platform_peer() -> None:
    """
    是什么：test_find_data_skills_explicit_personal_selection_is_overridden_by_platform_peer 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    session = _FakeSession([
        _skill_row(
            skill_id=1,
            name="SaaS-收入健康度",
            visibility_scope="PLATFORM_PUBLIC",
        ),
        _skill_row(
            skill_id=2,
            name="个人-收入健康度",
            visibility_scope="USER_PRIVATE",
        ),
    ])

    skill_text, skill_list, _ = find_data_skills(
        session,
        datasource=7,
        tenant_id=1,
        current_user_id=1,
        skill_id=2,
        question="收入健康度",
    )

    assert "SaaS-收入健康度 prompt" in skill_text
    assert "个人-收入健康度 prompt" not in skill_text
    assert [item.split("\n", 1)[0] for item in skill_list] == ["名称：SaaS-收入健康度"]
