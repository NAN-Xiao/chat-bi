from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def _module():
    sys.modules.pop("publish_xiuxian_conflict_data_skills", None)
    return importlib.import_module("publish_xiuxian_conflict_data_skills")


def _target_dashboards(module, *, omit: str | None = None):
    required = {
        view_id
        for topic in module.TOPICS
        if topic.slug in module.TARGET_TOPIC_SLUGS
        for view_id in topic.view_ids
        if view_id != module.EMPTY_DASHBOARD_VIEW_ID
    }
    drawers = [
        SimpleNamespace(view_id=view_id, sql=f"SELECT '{view_id}' AS view_id")
        for view_id in sorted(required)
        if view_id != omit
    ]
    return [
        SimpleNamespace(
            tenant_id=module.TENANT_ID,
            datasource=module.DATASOURCE_ID,
            drawers=drawers,
        )
    ]


def test_expected_live_prompt_hashes_are_fixed() -> None:
    module = _module()
    assert module.EXPECTED_PROMPT_SHA256 == {
        255: "7cd08a4e2eb004da53c2f7c4cbb4d51e876e135102f7bd8f15c185e24152e698",
        257: "3f4e71604bc26aef9489b7ef5abf0f9bcc9c813c8b82c2d4031968179206116a",
        276: "21028189d3e6bb09a1e4e19be21a0e5457d6322b687de722a7d3353c6a60d669",
    }
    assert module.EXPECTED_MANAGED_PROMPT_SHA256 == {
        255: frozenset(
            {"c6bb80e11e23b974e314848b12cf60275bd87a742f51e995c8de454c0b27f8f0"}
        ),
        257: frozenset(
            {
                "cab8dd8f0e86d5fcfaf91ba7c2e94b4601fbbc6ab2e5ecae61bec119ebd09ee9",
                "f10f5eeacabc878c25f041a66d0762cae45e9552a710db8870b0e546aef9babd",
            }
        ),
        276: frozenset(
            {
                "9bbfd4ab33b1f78a6db5c5c9182f7781a4d46f84ef4c8cb3e27508b6f84fa2c4",
                "cc37009eb7aff627ac83ddd04c219e8ea958e82fdb1ee5d7513259479d981145",
                "c3e8b93933999b5b2f34eb12a487ca56a9062c4cbf033b9560da7ef443051051",
            }
        ),
    }


def test_build_target_skills_ignores_missing_unrelated_drawers() -> None:
    module = _module()

    skills = module.build_target_skills(_target_dashboards(module))

    assert len(skills) == 3
    markers = [skill["prompt"].splitlines()[0] for skill in skills]
    assert markers == list(module.TARGET_MARKERS)
    assert "当前等级与活跃用户分布" in skills[0]["description"]
    assert "COUNT(DISTINCT ServerPayLog.uid)" in skills[2]["prompt"]
    assert "paytotal" not in module._target_topic("payer-penetration").guidance


def test_build_target_skills_rejects_missing_target_drawer() -> None:
    module = _module()
    required = next(
        view_id
        for topic in module.TOPICS
        if topic.slug == "payer-penetration"
        for view_id in topic.view_ids
    )

    with pytest.raises(ValueError, match="目标主题抽屉缺失"):
        module.build_target_skills(_target_dashboards(module, omit=required))


def test_validate_target_rows_rejects_name_and_description_drift() -> None:
    module = _module()
    skills = module.build_target_skills(_target_dashboards(module))
    rows = {
        skill_id: {
            "id": skill_id,
            "tenant_id": module.TENANT_ID,
            "type": "DATA_SKILL",
            "name": skill["name"],
            "description": skill["description"],
            "prompt": skill["prompt"],
            "create_by": None,
            "target_scope": "ALL",
            "active": True,
            "visible": True,
            "visibility_scope": "ADMIN_PUBLIC",
            "specific_ds": True,
            "datasource_ids": [module.DATASOURCE_ID],
        }
        for skill_id, skill in zip(module.TARGET_IDS, skills, strict=True)
    }
    module._validate_target_rows(rows, skills)

    name_drift = {skill_id: dict(row) for skill_id, row in rows.items()}
    name_drift[257]["name"] = "漂移名称"
    with pytest.raises(RuntimeError, match="前置名称漂移"):
        module._validate_target_rows(name_drift, skills)

    description_drift = {skill_id: dict(row) for skill_id, row in rows.items()}
    description_drift[276]["description"] = "漂移描述"
    with pytest.raises(RuntimeError, match="前置描述漂移"):
        module._validate_target_rows(description_drift, skills)


def test_validate_target_rows_accepts_previous_managed_prompt(monkeypatch) -> None:
    module = _module()
    skills = module.build_target_skills(_target_dashboards(module))
    rows = {
        skill_id: {
            "id": skill_id,
            "tenant_id": module.TENANT_ID,
            "type": "DATA_SKILL",
            "name": skill["name"],
            "description": skill["description"],
            "prompt": skill["prompt"],
            "create_by": None,
            "target_scope": "ALL",
            "active": True,
            "visible": True,
            "visibility_scope": "ADMIN_PUBLIC",
            "specific_ds": True,
            "datasource_ids": [module.DATASOURCE_ID],
        }
        for skill_id, skill in zip(module.TARGET_IDS, skills, strict=True)
    }
    previous_prompt = rows[257]["prompt"].replace(
        "按渠道统计累计付费用户数、", "", 1
    )
    rows[257]["prompt"] = previous_prompt
    rows[257]["description"] = module.EXPECTED_INITIAL_DESCRIPTIONS[257]
    monkeypatch.setitem(
        module.EXPECTED_MANAGED_PROMPT_SHA256,
        257,
        frozenset({module._prompt_hash(previous_prompt)}),
    )

    module._validate_target_rows(rows, skills)
