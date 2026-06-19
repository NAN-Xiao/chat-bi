import os
import re
from pathlib import Path

from apps.chat.curd.chat import format_record
from apps.chat.models.chat_model import ChatRecordResult

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_chat_record_frontend_fields_are_backed_by_backend_contract():
    frontend = (REPO_ROOT / "frontend/src/api/chat.ts").read_text(encoding="utf-8")
    to_record_match = re.search(r"const toChatRecord = .*?return new ChatRecord\((.*?)\n  \)", frontend, re.S)
    assert to_record_match is not None
    mapped_fields = set(re.findall(r"\bdata\.([A-Za-z_][A-Za-z0-9_]*)", to_record_match.group(1)))
    sample = ChatRecordResult(
        id=1,
        chat_id=2,
        question="show revenue",
        sql_answer="sql thinking",
        sql="select 1",
        datasource=3,
        data='{"fields":["x"],"data":[{"x":1}]}',
        chart_answer="chart thinking",
        chart="{}",
        analysis='{"reasoning_content":"analysis thinking","content":"analysis"}',
        predict='{"reasoning_content":"predict thinking","content":"predict content"}',
        predict_data='[]',
        recommended_question="[]",
        datasource_select_answer="project",
        finish=True,
        custom_prompt_id=9,
        duration=1.234,
        total_tokens=42,
    )

    backend_fields = set(format_record(sample).keys())

    missing = mapped_fields - backend_fields
    assert not missing, f"frontend ChatRecord maps fields not emitted by backend: {sorted(missing)}"


def test_analysis_assistant_block_wire_shape_matches_frontend_usage():
    backend = (REPO_ROOT / "backend/apps/analysis_assistant/api/analysis_assistant.py").read_text(encoding="utf-8")
    frontend = (REPO_ROOT / "frontend/src/views/analysis-assistant/AnalysisAssistantDock.vue").read_text(
        encoding="utf-8"
    )

    expected_block_fields = {"id", "title", "purpose", "sql", "fields", "data", "chart", "summary"}
    for field in expected_block_fields:
        assert f'"{field}"' in backend or f"'{field}'" in backend

    frontend_block_fields = set(re.findall(r"\bblock\.([A-Za-z_][A-Za-z0-9_]*)", frontend))
    assert expected_block_fields.issubset(frontend_block_fields)
    assert "block" in backend and '"type": "block"' in backend
    assert '"type": "final"' in backend
    assert '"type": "finish"' in backend
    assert '"type": "error"' in backend
