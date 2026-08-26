from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from apps.chat.task import llm
from apps.knowledge_base.context import (
    KNOWLEDGE_CONTEXT_SYSTEM_RULES,
    KnowledgeContext,
    KnowledgeDocumentContext,
    empty_knowledge_context,
)


def test_init_messages_injects_knowledge_into_sql_but_not_chart_mapping() -> None:
    prompt = (
        '<knowledge-context version="1"><workspace-knowledge tenant-id="23">'
        "业务背景正文</workspace-knowledge></knowledge-context>"
    )
    service = llm.LLMService.__new__(llm.LLMService)
    service.ds = SimpleNamespace(type="postgresql")
    service.chat_question = SimpleNamespace(
        regenerate_record_id=None,
        knowledge_context=prompt,
        sql_sys_question=lambda _db_type, _limit: {
            "system": "SQL 系统规则",
            "rules": "SQL 生成规则",
            "schema": "当前 Schema",
            "data_skill": "当前 Data Skill",
        },
        chart_sys_question=lambda: {
            "system": "图表系统规则",
            "rules": "图表映射规则",
        },
    )
    service.choose_table_schema = lambda _session: []
    service.generate_sql_logs = []
    service.generate_chart_logs = []
    service.base_message_round_count_limit = 3
    service.enable_sql_row_limit = True
    service.dashboard_date_filter_enabled = True

    service.init_messages(object())

    sql_contents = [str(message.content) for message in service.sql_message]
    chart_contents = [str(message.content) for message in service.chart_message]
    assert KNOWLEDGE_CONTEXT_SYSTEM_RULES in sql_contents
    assert prompt in sql_contents
    assert sql_contents.index("当前 Data Skill") < sql_contents.index(prompt)
    assert all("knowledge-context" not in content for content in chart_contents)
    assert all("业务背景正文" not in content for content in chart_contents)


def test_smart_qa_snapshot_records_knowledge_metadata_without_content(monkeypatch) -> None:
    secret_content = "快照中不得保存的知识正文"
    document = KnowledgeDocumentContext(
        id=31,
        name="工作空间知识",
        usage_instruction="用于回答流程问题。",
        content=secret_content,
        scope="ADMIN_PUBLIC",
        updated_at=datetime(2026, 8, 26, 10, 0, 0),
    )
    knowledge_context = KnowledgeContext(
        prompt=f"<knowledge-context>{secret_content}</knowledge-context>",
        platform_documents=(),
        workspace_documents=(document,),
        tenant_id=23,
        surface="smart_qa",
        datasource_id=7,
    )
    service = llm.LLMService.__new__(llm.LLMService)
    service.record = SimpleNamespace(id=9001)
    service.ds = SimpleNamespace(id=7, name="测试数据源")
    service.chat_question = SimpleNamespace(
        datasource_id=7,
        custom_prompt_id=None,
        custom_prompt="",
        data_skill_id=88,
        data_skill="Data Skill 正文",
        ai_modal_id=9,
        ai_modal_name="test-model",
    )
    service.business_sql_context = None
    service.knowledge_context = knowledge_context
    saved: list[dict] = []
    monkeypatch.setattr(
        llm,
        "save_agent_context_snapshot",
        lambda _session, record_id, snapshot: saved.append(
            {"record_id": record_id, "snapshot": snapshot}
        ),
    )

    service.save_agent_context_snapshot(
        object(),
        llm.CustomPromptTargetScopeEnum.SMART_QA,
    )

    assert saved[0]["record_id"] == 9001
    metadata = saved[0]["snapshot"]["knowledge_context"]
    assert metadata["workspace_documents"][0]["id"] == "31"
    assert metadata["workspace_documents"][0]["content_sha256"] == document.content_sha256
    assert secret_content not in str(saved[0]["snapshot"])


def test_external_assistant_datasource_still_loads_tenant_knowledge(monkeypatch) -> None:
    service = llm.LLMService.__new__(llm.LLMService)
    service.current_user = SimpleNamespace(tenant_id=23)
    service.ds = SimpleNamespace(id="external-datasource")
    service.chat_question = SimpleNamespace(knowledge_context="")
    service.knowledge_context = None
    expected = empty_knowledge_context(
        tenant_id=23,
        surface="smart_qa",
        datasource_id=None,
    )
    calls: list[dict] = []

    def _build(_session, **kwargs):
        calls.append(kwargs)
        return expected

    monkeypatch.setattr(llm, "build_knowledge_context", _build)

    result = service.load_knowledge_context(object(), surface="smart_qa")

    assert result is expected
    assert calls == [
        {
            "tenant_id": 23,
            "surface": "smart_qa",
            "datasource_id": None,
        }
    ]
