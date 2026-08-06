"""Cross-surface safety contract for AI context snapshots."""

import json

import pytest

from apps.chat.curd.agent_context_snapshot import build_agent_context_snapshot


@pytest.mark.parametrize(
    "surface",
    ["SMART_QA", "DASHBOARD_AI_SQL", "ANALYSIS_ASSISTANT", "REPORT_INTERPRETATION"],
)
def test_surface_snapshot_keeps_security_metadata_without_prompt_bodies(surface: str):
    snapshot = build_agent_context_snapshot(
        surface=surface,
        datasource_id=10,
        datasource_name="业务库",
        data_skill_id=7,
        data_skill_text="不应进入快照正文",
        target_scope=surface,
        business_context={
            "permission_version": "permission-1",
            "schema_hash": "schema-1",
            "selected_skills": [{"id": "7", "selection_mode": "AUTOMATIC"}],
            "knowledge_version_hash": "knowledge-1",
            "knowledge_citations": [
                {"knowledge_base_id": "20", "version_id": "21", "content": "机密正文"}
            ],
            "warnings": ["检索告警"],
            "knowledge_context": "机密知识正文",
            "skill_text": "机密 Skill 正文",
            "tracking_config": "机密事件正文",
        },
    )

    business = snapshot["business_context"]
    assert snapshot["version"] == 2
    assert business["permission_version"] == "permission-1"
    assert business["schema_hash"] == "schema-1"
    assert business["selected_skills"] == [{"id": "7", "selection_mode": "AUTOMATIC"}]
    assert business["knowledge_citations"] == [{"knowledge_base_id": "20", "version_id": "21"}]
    assert business["warnings"] == ["检索告警"]
    serialized = json.dumps(snapshot, ensure_ascii=False)
    assert "机密知识正文" not in serialized
    assert "机密 Skill 正文" not in serialized
    assert "机密事件正文" not in serialized
    assert "content" not in business["knowledge_citations"][0]
