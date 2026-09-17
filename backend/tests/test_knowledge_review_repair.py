"""知识裁决外部响应、证据和修复分流回归。"""
import json
from types import SimpleNamespace

import pytest

from apps.knowledge_base.authority import knowledge_resolves_business_conflict
from apps.knowledge_base.context import KnowledgeContextError


CONTEXT = '<knowledge-context><workspace-knowledge><document id="6"><knowledge-content>渠道使用 source_code。\n金额以退款后净额计算。</knowledge-content></document><document id="7"><knowledge-content>渠道使用 legacy_source。</knowledge-content></document></workspace-knowledge></knowledge-context>'


def verdict(status='not_applicable', **kwargs):
    return json.dumps(dict(status=status, relationship='unrelated', document_id=None,
                           quote=None, reason='没有覆盖当前规则的知识', **kwargs), ensure_ascii=False)


class Responses:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def invoke(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(content=response, usage_metadata={'input_tokens': 12, 'output_tokens': 4, 'total_tokens': 16})


def test_empty_review_is_regenerated_once_and_preserves_original_validation():
    model = Responses('', verdict())
    assert knowledge_resolves_business_conflict(model, CONTEXT, '补齐日期', 'SELECT day') is False
    assert len(model.calls) == 2


def test_invalid_json_exhaustion_is_typed_and_bounded():
    model = Responses('not JSON', '[]')
    with pytest.raises(KnowledgeContextError) as error:
        knowledge_resolves_business_conflict(model, CONTEXT, '补齐日期', 'SELECT day')
    assert error.value.code == 'knowledge_review_invalid_response'
    assert len(model.calls) == 2


def test_timeout_has_no_outer_network_retry_and_never_approves_sql():
    model = Responses(TimeoutError('private upstream details'))
    with pytest.raises(KnowledgeContextError) as error:
        knowledge_resolves_business_conflict(model, CONTEXT, '补齐日期', 'SELECT day')
    assert error.value.code == 'knowledge_review_unavailable'
    assert 'private upstream' not in str(error.value)
    assert len(model.calls) == 1


def test_rejection_needs_real_source_evidence_before_it_can_repair():
    wrong = json.dumps({'status':'invalid_output','output_complies':False,'relationship':'overrides','document_id':'6',
                        'quote':'根本不存在的规则','reason':'按此修复'})
    with pytest.raises(KnowledgeContextError) as error:
        knowledge_resolves_business_conflict(Responses(wrong, wrong), CONTEXT, '旧字段', 'SELECT legacy_source')
    assert error.value.code == 'knowledge_review_invalid_response'


def test_verified_knowledge_violation_carries_repair_evidence():
    response = json.dumps({'status':'invalid_output','output_complies':False,'relationship':'overrides','document_id':'6',
                           'quote':'渠道使用 source_code。','reason':'SQL使用了旧渠道字段'})
    with pytest.raises(KnowledgeContextError) as error:
        knowledge_resolves_business_conflict(Responses(response), CONTEXT, '使用old_source', 'SELECT legacy_source')
    assert error.value.code == 'knowledge_output_invalid'
    assert error.value.repairable is True
    assert '渠道使用 source_code。' in error.value.repair_message


def test_knowledge_supporting_original_rule_returns_ordinary_violation():
    response = json.dumps({'status':'invalid_output','output_complies':False,'relationship':'supports','document_id':'6',
                           'quote':'渠道使用 source_code。','reason':'仍然应遵循原规则'})
    assert knowledge_resolves_business_conflict(Responses(response), CONTEXT, '渠道使用source_code', 'SELECT legacy_source') is False


def test_actual_same_scope_conflict_never_enters_sql_repair():
    response = json.dumps({'status':'conflict','relationship':'overrides','document_id':'6',
                           'quote':'渠道使用 source_code。','conflicting_document_id':'7',
                           'conflicting_quote':'渠道使用 legacy_source。','reason':'同层渠道规则冲突'})
    with pytest.raises(KnowledgeContextError) as error:
        knowledge_resolves_business_conflict(Responses(response), CONTEXT, '渠道字段', 'SELECT source_code')
    assert error.value.code == 'knowledge_conflict'
    assert not getattr(error.value, 'repairable', False)


def test_review_records_both_protocol_attempts_and_usage():
    events = []
    model = Responses('', verdict())
    assert not knowledge_resolves_business_conflict(model, CONTEXT, '补齐日期', 'SELECT day', observer=events.append)
    assert [e['event'] for e in events] == ['start', 'finish', 'start', 'finish']
    finishes = [e for e in events if e['event']=='finish']
    assert [e['status'] for e in finishes] == ['invalid_response', 'not_applicable']
    assert [e['attempt'] for e in finishes] == [1, 2]
    assert all(e['usage']['total_tokens']==16 for e in finishes)


def test_workflow_exposes_safe_review_error_not_internal_traceback():
    from apps.chat.task.assistant_workflow import format_workflow_error
    error = KnowledgeContextError('knowledge_review_unavailable', '知识规则校验服务暂时不可用，请重试。')
    payload = json.loads(format_workflow_error(error, service=SimpleNamespace(), log_prefix='test'))
    assert payload['error_type']=='knowledge_review_unavailable'
    assert 'traceback' not in payload
    assert 'type' not in payload  # 未注册的展示类型会把中文原因折叠成“错误”。


def test_verified_knowledge_violation_is_a_repair_reason_but_conflict_is_not():
    from apps.chat.task.sql_repair import classify_prepare_sql_error, SqlRepairReason
    response = json.dumps({'status':'invalid_output','output_complies':False,'relationship':'overrides','document_id':'6',
                           'quote':'渠道使用 source_code。','reason':'错误字段'})
    with pytest.raises(KnowledgeContextError) as error:
        knowledge_resolves_business_conflict(Responses(response), CONTEXT, '渠道字段', 'SELECT legacy_source')
    assert classify_prepare_sql_error(error.value) == SqlRepairReason.KNOWLEDGE_VALIDATION
    assert classify_prepare_sql_error(KnowledgeContextError('knowledge_conflict','知识冲突')) is None


def test_resolved_status_cannot_approve_an_output_marked_noncompliant():
    response=json.dumps({'status':'resolved','relationship':'overrides','document_id':'6',
                         'quote':'渠道使用 source_code。','output_complies':False,'reason':'输出不符合，必须修复'})
    corrected=json.dumps({'status':'invalid_output','output_complies':False,'relationship':'overrides','document_id':'6',
                          'quote':'渠道使用 source_code。','output_complies':False,'reason':'输出不符合，必须修复'})
    with pytest.raises(KnowledgeContextError) as error:
        knowledge_resolves_business_conflict(Responses(response,corrected),CONTEXT,'渠道字段','SELECT legacy_source')
    assert error.value.code=='knowledge_output_invalid'


def test_analysis_identifier_does_not_adjudicate_knowledge_conflict():
    from langchain_core.messages import HumanMessage
    from apps.analysis_assistant.api import analysis_assistant as api
    context = CONTEXT.replace('渠道使用 source_code。', "事件使用 'PaidNet'。")
    review = json.dumps({'status':'invalid_output','output_complies':False,'relationship':'overrides','document_id':'6',
                         'quote':"事件使用 'PaidNet'。",'reason':'使用了旧事件'})
    approved = json.loads(review)
    approved['status'] = 'resolved'
    approved['output_complies'] = True
    model = Responses(review, "SELECT amount FROM events WHERE event = 'PaidNet'", json.dumps(approved))
    result = api._llm_text_for_executable_sql(
        model, [HumanMessage(content=context)], "event = 'LegacyPaid'", initial_text="SELECT amount FROM events WHERE event = 'Paid'",
    )
    assert "'Paid'" in result
    assert model.calls == []


def test_analysis_semantic_error_returns_verified_rule_for_repair():
    from apps.analysis_assistant.api import analysis_assistant as api
    from apps.knowledge_base.authority import KnowledgeOutputValidationError, KnowledgeVerdict
    def review(*args):
        raise KnowledgeOutputValidationError(KnowledgeVerdict(
            status='invalid_output', relationship='overrides', document_id='6',
            quote='金额以退款后净额计算。', reason='请按净额计算'))
    error = api._semantic_validation_error({}, {'fields':['expense_ratio'], 'data':[{'expense_ratio':125}]}, resolve_conflict=review)
    assert '金额以退款后净额计算。' in error


def test_sdk_retry_count_is_request_local_and_separate_from_format_attempts():
    from common.utils.llm_attempts import record_llm_retry
    class RetryModel(Responses):
        def invoke(self, messages, **kwargs):
            record_llm_retry()
            return super().invoke(messages, **kwargs)
    events=[]
    assert not knowledge_resolves_business_conflict(RetryModel(verdict()), CONTEXT, '规则', 'SELECT x', observer=events.append)
    record_llm_retry()
    assert events[-1]['sdk_retries']==1
    assert events[-1]['attempt']==1


def test_json_mode_is_explicit_and_does_not_leak_to_normal_generation():
    from apps.knowledge_base.review_audit import ReviewedModel
    model = Responses(verdict(), 'normal response')
    wrapped = ReviewedModel(model, json_mode=True, extra_body={'enable_thinking':False})
    assert not knowledge_resolves_business_conflict(wrapped, CONTEXT, '规则', 'SELECT x')
    wrapped.invoke([])
    assert model.calls[0][1]['response_format']=={'type':'json_object'}
    assert model.calls[0][1]['extra_body']=={'enable_thinking':False}
    assert model.calls[1][1]=={}


def test_review_audit_persists_attempts_usage_and_tenant_boundaries(monkeypatch):
    from sqlalchemy import create_engine, text
    from sqlmodel import Session, select
    from apps.chat.models.chat_model import ChatLog, OperationEnum
    from apps.chat.curd import chat
    from apps.knowledge_base.review_audit import KnowledgeReviewAudit
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE chat_log (id INTEGER PRIMARY KEY, tenant_id BIGINT NOT NULL, type VARCHAR, operate VARCHAR, pid BIGINT, ai_modal_id BIGINT, base_modal VARCHAR, messages JSON, reasoning_content TEXT, start_time DATETIME, finish_time DATETIME, token_usage JSON, local_operation BOOLEAN, error BOOLEAN)'))
    usage=[]
    monkeypatch.setattr(chat, 'record_tenant_usage_detached', lambda **kw: usage.append(kw))
    audit=KnowledgeReviewAudit(tenant_id=23,datasource_id=42,model_id=7,model_name='test',surface='analysis_assistant',session_factory=lambda:Session(engine))
    assert not knowledge_resolves_business_conflict(Responses('',verdict()),CONTEXT,'规则','SELECT x',observer=audit)
    with Session(engine) as session:
        logs=session.exec(select(ChatLog).order_by(ChatLog.id)).all()
        assert len(logs)==2
        assert all(l.tenant_id==23 and l.operate==OperationEnum.KNOWLEDGE_REVIEW for l in logs)
        assert [l.error for l in logs]==[True,False]
        assert all(l.finish_time and l.token_usage['total_tokens']==16 for l in logs)
        assert all(l.messages[0]['datasource_id']==42 for l in logs)
    assert len(usage)==2
    assert sum(u['request_count'] for u in usage)==2
    assert all(u['tenant_id']==23 for u in usage)


def test_model_config_extracts_review_options_for_every_construction_path():
    from apps.ai_model.model_factory import LLMConfig
    params={'temperature':0,'knowledge_review_json_mode':True,'knowledge_review_extra_body':{'enable_thinking':False}}
    config=LLMConfig(model_type='openai',model_name='test',additional_params=params)
    assert config.additional_params=={'temperature':0}
    assert config.knowledge_review_json_mode is True
    assert config.knowledge_review_extra_body=={'enable_thinking':False}
    assert params['knowledge_review_json_mode'] is True


def test_repaired_sql_cannot_escape_a_previously_required_knowledge_rule():
    from apps.knowledge_base.authority import KnowledgeReviewGuard, KnowledgeOutputValidationError, KnowledgeVerdict
    checked=[]
    def review(rule, output):
        checked.append(output)
        complies = 'net_amount' in output
        return KnowledgeVerdict(status='resolved' if complies else 'invalid_output',relationship='overrides',
            output_complies=complies,document_id='6',quote='金额以退款后净额计算。',reason='必须使用净额')
    guard=KnowledgeReviewGuard(review, review)
    with pytest.raises(KnowledgeOutputValidationError):guard.resolve('旧金额规则','SELECT wrong_amount')
    with pytest.raises(KnowledgeOutputValidationError):guard.revalidate('SELECT old_amount')
    guard.revalidate('SELECT net_amount')
    assert checked==['SELECT wrong_amount','SELECT old_amount','SELECT net_amount']
