"""Executable SQL is the gate; semantic quality is reported, not adjudicated."""
import json
from types import SimpleNamespace

import pytest

from apps.chat.task import llm
from apps.chat.models.chat_model import OperationEnum
from apps.datasource.crud.permission_errors import SqlPermissionScopeError


def service_for(rule):
    service = llm.LLMService.__new__(llm.LLMService)
    service.current_logs = {OperationEnum.GENERATE_SQL: object()}
    service.dashboard_date_filter_enabled = False
    service.ds = SimpleNamespace(type='mysql')
    service.config = SimpleNamespace(knowledge_review_json_mode=False, knowledge_review_extra_body={})
    service._knowledge_review_observer = lambda: None
    class NeverReview:
        def invoke(self, *args, **kwargs):
            pytest.fail('executable SQL must not enter knowledge adjudication')
    service.llm = NeverReview()
    service.chat_question = SimpleNamespace(question='每日金额',
        data_skill='<!-- data-skill-sql-validation: ' + json.dumps(rule) + ' -->',
        knowledge_context='<knowledge-context><workspace-knowledge><document id="1">金额使用净额。</document></workspace-knowledge></knowledge-context>')
    return service


@pytest.mark.parametrize('rule', [
    {'required_zero_fill': True},
    {'required_hour_sequence': True},
    {'rule_type': 'business', 'required_sql_contains': ['net_amount']},
])
def test_executable_sql_survives_quality_mismatch_without_review(rule, monkeypatch):
    monkeypatch.setattr(llm, 'trigger_log_error', lambda *a, **kw: None)
    service = service_for(rule)
    sql = 'SELECT day, gross_amount FROM orders'
    actual, _ = service.check_sql(object(), json.dumps({'success': True, 'sql': sql}), OperationEnum.GENERATE_SQL)
    assert actual == sql
    assert service.sql_quality_warnings
    assert not hasattr(service, '_knowledge_review_guard')


def test_security_rule_is_not_downgraded_to_quality_warning(monkeypatch):
    monkeypatch.setattr(llm, 'trigger_log_error', lambda *a, **kw: None)
    service = service_for({'rule_type': 'security', 'required_sql_contains': ['authorized_scope']})
    with pytest.raises(SqlPermissionScopeError):
        service.check_sql(object(), json.dumps({'success': True, 'sql': 'SELECT amount FROM orders'}), OperationEnum.GENERATE_SQL)


def test_identifier_uncertainty_does_not_invoke_semantic_repair():
    from apps.analysis_assistant.api import analysis_assistant as api
    class NeverCall:
        def invoke(self, *args, **kwargs):
            pytest.fail('semantic mismatch must not cause an extra LLM call')
    text = 'SELECT amount FROM events WHERE event = \'Paid\''
    assert api._llm_text_for_executable_sql(
        NeverCall(), [], "event = 'LegacyPaid'", initial_text=text) == text
