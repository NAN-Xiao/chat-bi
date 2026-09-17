import json
from types import SimpleNamespace

import pytest

from apps.knowledge_base.authority import knowledge_resolves_business_conflict


KNOWLEDGE = '<knowledge-context><workspace-knowledge><document id="6"><knowledge-content>渠道使用 adinfo.mediaSource。</knowledge-content></document></workspace-knowledge></knowledge-context>'


class ReviewModel:
    def __init__(self, verdict):
        self.verdict = {'output_complies': verdict.get('status') == 'resolved',
                        'relationship': 'unrelated' if verdict.get('status') == 'not_applicable' else 'overrides',
                        'reason': '测试中的业务规则判断', **verdict}
        self.messages = []

    def invoke(self, messages):
        self.messages = messages
        return SimpleNamespace(content=json.dumps(self.verdict))


def test_explicit_document_evidence_can_resolve_business_rule_conflict():
    model = ReviewModel({"status": "resolved", "document_id": "6", "quote": "渠道使用 adinfo.mediaSource。"})
    assert knowledge_resolves_business_conflict(model, KNOWLEDGE, "渠道必须使用 adinfo.channel", "SELECT adinfo.mediaSource")
    submitted = json.loads(model.messages[-1].content)
    assert '渠道使用 adinfo.mediaSource。' in submitted['documents']['6']['content']
    assert "渠道必须使用 adinfo.channel" == submitted["lower_priority_rule"]


@pytest.mark.parametrize("verdict", [
    {"status": "uncertain"},
    {"status": True, "document_id": "6", "quote": "渠道使用 adinfo.mediaSource。"},
    {"status": "resolved", "document_id": "7", "quote": "渠道使用 adinfo.mediaSource。"},
    {"status": "resolved", "document_id": "6", "quote": "文档未包含的规则"},
    {"status": "resolved", "document_id": "6", "quote": ""},
])
def test_missing_or_fabricated_evidence_does_not_override_validation(verdict):
    from apps.knowledge_base.context import KnowledgeContextError

    with pytest.raises(KnowledgeContextError):
        knowledge_resolves_business_conflict(ReviewModel(verdict), KNOWLEDGE, "计数要求", "SELECT 1")


@pytest.mark.parametrize("status", ["conflict", "invalid_output", "uncertain"])
def test_unresolved_knowledge_never_falls_back_to_skill(status):
    from apps.knowledge_base.context import KnowledgeContextError

    with pytest.raises(KnowledgeContextError):
        knowledge_resolves_business_conflict(ReviewModel({"status": status}), KNOWLEDGE, "旧规则", "SELECT 1")


def test_unrelated_knowledge_preserves_lower_priority_rule():
    assert not knowledge_resolves_business_conflict(
        ReviewModel({"status": "not_applicable"}), KNOWLEDGE, "无关规则", "SELECT 1",
    )


def test_no_documents_preserve_validation_without_model_call():
    model = ReviewModel({"overrides": True})
    assert not knowledge_resolves_business_conflict(model, "", "计数要求", "SELECT 1")
    assert not model.messages


def test_model_failure_is_explicit_and_does_not_drop_business_validation():
    from apps.knowledge_base.context import KnowledgeContextError

    class UnavailableModel:
        def invoke(self, messages):
            raise TimeoutError("unavailable")

    with pytest.raises(KnowledgeContextError, match="暂时不可用"):
        knowledge_resolves_business_conflict(UnavailableModel(), KNOWLEDGE, "业务校验", "SELECT 1")


def test_overriding_one_sql_rule_does_not_skip_other_skill_rules():
    from apps.chat.task.llm import _data_skill_sql_validation_violation

    rules = [
        {"rule_type": "business", "required_sql_contains": ["old_field"], "message": "旧字段口径"},
        {"rule_type": "business", "required_sql_contains": ["required_metric"], "message": "另一条校验"},
    ]
    skill = '<!-- data-skill-sql-validation: ' + json.dumps(rules) + ' -->'
    violation = _data_skill_sql_validation_violation(
        "业务查询", "SELECT new_field FROM events", skill,
        resolve_conflict=lambda rule, output: rule["message"] == "旧字段口径",
    )
    assert violation.message == "另一条校验"


def test_analysis_identifier_retry_accepts_document_override():
    from apps.analysis_assistant.api import analysis_assistant as analysis_api
    from langchain_core.messages import HumanMessage

    knowledge = KNOWLEDGE.replace("渠道使用 adinfo.mediaSource。", "事件使用 `Paid`。")
    model = ReviewModel({"status": "resolved", "document_id": "6", "quote": "事件使用 `Paid`。"})
    output = analysis_api._llm_text_for_executable_sql(
        model, [HumanMessage(content=knowledge)], "event = 'OldPaid'",
        initial_text="SELECT * FROM events WHERE event = 'Paid'",
    )
    assert "'Paid'" in output
    assert "OldPaid" not in output


def test_analysis_knowledge_can_override_ratio_guess_without_skipping_skill_rules():
    from apps.analysis_assistant.api import analysis_assistant as analysis_api

    result = {"fields": ["expense_ratio"], "data": [{"expense_ratio": 125}]}
    reviewed = []

    def resolve(rule, query, data):
        reviewed.append(rule)
        return True

    assert analysis_api._semantic_validation_error({}, result, resolve_conflict=resolve) is None
    assert reviewed
    skill = '<!-- data-skill-validation: {"required_fields":["sample_count"]} -->'
    error = analysis_api._semantic_validation_error(
        {}, result, skill, resolve_conflict=lambda rule, query, data: "expense_ratio" in rule,
    )
    assert "sample_count" in error


def test_dashboard_validation_does_not_consult_knowledge_or_override_config(monkeypatch):
    import asyncio
    from apps.dashboard.crud import ai_sql_generator as dashboard

    async def create_model(model_id):
        pytest.fail("图表配置校验不应调用知识库裁决模型")

    monkeypatch.setattr(dashboard, "_create_dashboard_ai_sql_llm", create_model)
    response = dashboard.DashboardAiSqlGenerateResponse(
        success=True, sql="SELECT JSON_EXTRACT(events.adinfo, '$.mediaSource') AS channel FROM events",
    )
    result = asyncio.run(dashboard._async_node_validate_sql({
        "response": response, "knowledge_context": KNOWLEDGE, "sql_dialect": "mysql",
        "json_subfield_requirements": [{"source_field": "adinfo", "json_path": "$.channel"}],
    }))
    assert not result["response"].success
    assert "JSON 字段映射" in result["response"].message


@pytest.mark.parametrize("readonly", [True, False])
def test_dashboard_preserves_readonly_validation(monkeypatch, readonly):
    from apps.dashboard.crud import ai_sql_generator as dashboard

    monkeypatch.setattr(dashboard, "check_sql_read", lambda *args: (readonly, "只读限制"))
    response = dashboard.DashboardAiSqlGenerateResponse(
        success=True, sql="SELECT JSON_EXTRACT(events.payload, '$.new_key') AS channel FROM events",
    )
    result = dashboard._node_validate_sql({
        "response": response,
        "datasource": SimpleNamespace(type="mysql"),
        "json_subfield_requirements": [{"source_table": "events", "source_field": "payload", "json_path": "$.new_key"}],
        "sql_dialect": "mysql",
    })
    assert result["response"].success is readonly


@pytest.mark.parametrize("node_name", ["_async_node_generate_sql", "_async_node_repair_sql"])
def test_dashboard_generation_and_repair_receive_skills_without_knowledge(node_name, monkeypatch):
    import asyncio
    from apps.dashboard.crud import ai_sql_generator as dashboard

    class CaptureModel:
        async def ainvoke(self, messages):
            assert "知识库" not in messages[0].content
            assert KNOWLEDGE not in messages[1].content
            assert "平台查询规则" in messages[1].content
            return SimpleNamespace(content='{"success":true,"sql":"SELECT 1"}')

    async def create_model(model_id):
        return CaptureModel()

    monkeypatch.setattr(dashboard, "_create_dashboard_ai_sql_llm", create_model)
    monkeypatch.setattr(dashboard, "_write_llm_output_debug_file", lambda **kwargs: None)
    state = {
        "request": dashboard.DashboardAiSqlGenerateRequest(datasource=1),
        "datasource": SimpleNamespace(name="业务库", type="mysql", type_name="MySQL"),
        "knowledge_context": KNOWLEDGE,
        "data_skill": "<Data-Skills>平台查询规则</Data-Skills>",
    }
    result = asyncio.run(getattr(dashboard, node_name)(state))
    assert result["response"].sql == "SELECT 1"
