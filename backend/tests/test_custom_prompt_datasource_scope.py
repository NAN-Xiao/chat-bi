"""
脚本说明：这个脚本是测试文件，用来验证 Data Skills 的项目生效范围。
"""
from __future__ import annotations

from typing import Any

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

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def execute(self, *args, **kwargs) -> _FakeResult:
        return _FakeResult(self._rows)


def _skill_row(
        *,
        skill_id: int,
        name: str,
        visibility_scope: str = "PLATFORM_PUBLIC",
        specific_ds: bool = False,
        datasource_ids: list[int] | None = None,
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
        "prompt": f"{name} prompt",
        "embedding": None,
        "embedding_signature": None,
        "specific_ds": specific_ds,
        "datasource_ids": datasource_ids or [],
        "ai_model_id": None,
        "create_by": 1,
        "visibility_scope": visibility_scope,
    }


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
