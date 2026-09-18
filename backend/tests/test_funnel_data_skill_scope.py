"""Regression tests for model-scoped platform funnel Data Skill retrieval."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.chat.curd import custom_prompt


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *_args, **_kwargs):
        return _Result(self.rows)


def _row(skill_id: int, prompt: str, *, name: str | None = None) -> dict:
    return {
        "id": skill_id,
        "tenant_id": 1,
        "name": name or f"skill-{skill_id}",
        "description": "test skill",
        "prompt": prompt,
        "embedding": None,
        "embedding_signature": None,
        "specific_ds": False,
        "datasource_ids": [],
        "ai_model_id": None,
        "create_by": None,
        "visibility_scope": "PLATFORM_PUBLIC",
        "excluded_tenant_ids": None,
    }


def _find(rows, *, analysis_model=None, skill_id=None):
    return custom_prompt.find_data_skills(
        _Session(rows),
        datasource=1,
        target_scope=custom_prompt.CustomPromptTargetScopeEnum.ALL,
        skill_id=skill_id,
        tenant_id=1,
        question="漏斗转化",
        analysis_model=analysis_model,
    )


def test_model_metadata_is_filtered_before_ranking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(custom_prompt.settings, "EMBEDDING_ENABLED", False)
    rows = [
        _row(1, '<!-- data-skill-analysis-models: ["funnel"] -->\nfunnel'),
        _row(2, '<!-- data-skill-analysis-models: ["retention"] -->\nretention'),
        _row(3, "generic"),
        _row(4, "<!-- data-skill-analysis-models: [broken] -->\nmalformed"),
    ]

    _text, skill_list, _model_id = _find(rows, analysis_model="funnel")
    assert ["skill-1" in item for item in skill_list].count(True) == 1
    assert any("skill-3" in item for item in skill_list)
    assert all("skill-2" not in item and "skill-4" not in item for item in skill_list)

    _text, skill_list, _model_id = _find(rows)
    assert all("skill-1" not in item and "skill-2" not in item and "skill-4" not in item for item in skill_list)
    assert any("skill-3" in item for item in skill_list)


@pytest.mark.parametrize(
    "prompt",
    [
        '<!-- data-skill-analysis-models ["funnel"] -->\nmalformed',
        '<!-- data-skill-analysis-models: ["funnel"] -->\nvalid-looking\n<!-- data-skill-analysis-models:',
    ],
)
def test_reserved_model_metadata_name_requires_one_complete_declaration(prompt: str) -> None:
    text, skill_list, _model_id = _find([_row(1, prompt)], analysis_model="funnel")

    assert text == ""
    assert skill_list == []


def test_explicit_skill_selection_cannot_bypass_model_scope() -> None:
    rows = [
        _row(1, '<!-- data-skill-analysis-models: ["funnel"] -->\nfunnel'),
        _row(2, '<!-- data-skill-analysis-models: ["retention"] -->\nretention'),
    ]

    text, skill_list, _model_id = _find(rows, skill_id=1, analysis_model="retention")
    assert text == ""
    assert skill_list == []

    text, skill_list, _model_id = _find(rows, skill_id=1, analysis_model="funnel")
    assert "funnel" in text
    assert len(skill_list) == 1


def test_direct_filter_preserves_data_skills_closing_tag() -> None:
    prompt = (
        '<Data-Skills>\n'
        '\n---\n## Funnel\n<!-- data-skill-analysis-models: ["funnel"] -->\nkeep\n'
        '\n---\n## Retention\n<!-- data-skill-analysis-models: ["retention"] -->\ndrop\n'
        '</Data-Skills>\n'
    )

    filtered = custom_prompt.filter_data_skill_for_analysis_model(prompt, "funnel")
    assert "keep" in filtered
    assert "drop" not in filtered
    assert filtered.rstrip().endswith("</Data-Skills>")


def test_direct_filter_drops_nested_sections_of_non_matching_skill() -> None:
    prompt = (
        '<Data-Skills>\n'
        '\n---\n## Funnel\n<!-- data-skill-analysis-models: ["funnel"] -->\nroot\n'
        '\n---\n## SQL example\nwindow_funnel(...)\n'
        '\n---\n## Generic\n作用域：平台通用（所有项目）\n约束：通用规则\nkeep generic\n'
        '</Data-Skills>\n'
    )

    filtered = custom_prompt.filter_data_skill_for_analysis_model(prompt, "event")

    assert "root" not in filtered
    assert "window_funnel" not in filtered
    assert "keep generic" in filtered
    assert filtered.rstrip().endswith("</Data-Skills>")


def test_platform_funnel_migration_contains_complete_reference_contract() -> None:
    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "168_platform_funnel_data_skill.py"
    spec = importlib.util.spec_from_file_location("platform_funnel_data_skill", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.down_revision == "167platformzerofillexpression"
    assert migration.SKILL_VISIBILITY_SCOPE == "PLATFORM_PUBLIC"
    assert '<!-- data-skill-analysis-models: ["funnel"] -->' in migration.SKILL_PROMPT
    for token in ("event.uid", "event.event", "event.time", "event.dt", "event.prod"):
        assert token in migration.SKILL_PROMPT
    assert "{{dashboard_start_yyyymmdd}}" in migration.SKILL_PROMPT
    assert "{{dashboard_end_yyyymmdd}}" in migration.SKILL_PROMPT
    assert "window_funnel" in migration.SKILL_PROMPT
    assert "step_order" in migration.SKILL_PROMPT
    assert "step_dropoff_rate" in migration.SKILL_PROMPT
    assert "AnalyticDB MySQL" in migration.SKILL_PROMPT
    assert "BIGINT 秒" in migration.SKILL_PROMPT
    assert "CAST(<毫秒事件时间> / 1000 AS SIGNED)" in migration.SKILL_PROMPT
    assert "启用关联属性" in migration.SKILL_PROMPT
    assert "不能使用原生 `window_funnel`" in migration.SKILL_PROMPT
    assert "主体最大深度聚合层" in migration.SKILL_PROMPT
    for keyword in ("HAVING", "QUALIFY", "LIMIT", "OFFSET"):
        assert keyword in migration.SKILL_PROMPT
    assert "step_counts" in migration.SKILL_PROMPT
    assert "必须使用 UNION ALL" in migration.SKILL_PROMPT
    assert migration.SKILL_PROMPT.count("WHEN first_step_count = 0 THEN NULL") == 2


def test_platform_funnel_skill_update_contains_positive_and_negative_examples() -> None:
    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "169_platform_funnel_data_skill_examples.py"
    spec = importlib.util.spec_from_file_location("platform_funnel_data_skill_examples", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.down_revision == "168platformfunnelskill"
    assert "MAX/LAG" in migration.NEW_RULE
    assert "SELECT first_sc.step_count" in migration.NEW_STEP_METRICS
    assert "GROUP BY entity_id" in migration.NEGATIVE_EXAMPLES
    assert "MIN(event_time) AS first_step_time" in migration.NEGATIVE_EXAMPLES


def test_platform_funnel_migration_rejects_marker_owned_by_non_platform_skill(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "168_platform_funnel_data_skill.py"
    spec = importlib.util.spec_from_file_location("platform_funnel_data_skill_identity", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    class _CountResult:
        def __init__(self, value: int) -> None:
            self.value = value

        def scalar_one(self) -> int:
            return self.value

    class _Bind:
        dialect = SimpleNamespace(name="postgresql")

        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement, _params):
            sql = str(statement)
            self.statements.append(sql)
            if "visibility_scope" in sql:
                return _CountResult(0)
            return _CountResult(1)

    bind = _Bind()
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)

    with pytest.raises(RuntimeError, match="平台作用域"):
        migration.upgrade()

    assert not any("UPDATE custom_prompt" in statement for statement in bind.statements)
    assert not any("INSERT INTO custom_prompt" in statement for statement in bind.statements)


def test_platform_funnel_migration_downgrade_deletes_only_platform_identity(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "168_platform_funnel_data_skill.py"
    spec = importlib.util.spec_from_file_location("platform_funnel_data_skill_downgrade", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", lambda statement: statements.append(str(statement)))

    migration.downgrade()

    assert len(statements) == 1
    statement = statements[0]
    assert "tenant_id = 1" in statement
    assert "visibility_scope = 'PLATFORM_PUBLIC'" in statement
    assert "create_by IS NULL" in statement
    assert "COALESCE(specific_ds, FALSE) = FALSE" in statement
