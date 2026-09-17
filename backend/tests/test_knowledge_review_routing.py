"""Structural contracts must be repaired locally, without semantic arbitration."""
import json

import pytest

from apps.chat.task.llm import _data_skill_sql_validation_violation
from apps.knowledge_base.authority import KnowledgeReviewGuard, KnowledgeVerdict, KnowledgeOutputValidationError


def skill(*rules):
    return '<!-- data-skill-sql-validation: ' + json.dumps(rules) + ' -->'


@pytest.mark.parametrize('rule', [
    {'required_sql_contains': ['LEFT JOIN']},
    {'rule_type': 'sql_structure', 'required_sql_patterns': ['COALESCE']},
    {'rule_type': 'business', 'required_zero_fill': True},
    {'rule_type': 'business', 'required_hour_sequence': True},
    {'rule_type': 'security', 'required_sql_contains': ['authorized_scope']},
])
def test_sql_contracts_never_call_knowledge_even_if_callback_would_approve(rule):
    calls = []
    violation = _data_skill_sql_validation_violation(
        '每日统计', 'SELECT day, amount FROM events', skill(rule),
        resolve_conflict=lambda *args: calls.append(args) or True,
    )
    assert violation is not None
    assert calls == []


def test_local_contracts_are_checked_before_business_reviews():
    calls = []
    rules = skill(
        {'rule_type': 'business', 'required_sql_contains': ['legacy_amount']},
        {'rule_type': 'sql_structure', 'required_sql_contains': ['LEFT JOIN'], 'message': '补齐日期'},
    )
    violation = _data_skill_sql_validation_violation(
        '每日统计', 'SELECT day, net_amount FROM events', rules,
        resolve_conflict=lambda *args: calls.append(args) or True,
    )
    assert violation.message == '补齐日期'
    assert not calls


def test_structural_failure_also_precedes_existing_knowledge_obligations():
    def never_revalidate():
        pytest.fail('repair the structural contract before rechecking business evidence')
    violation = _data_skill_sql_validation_violation(
        '每日统计', 'SELECT amount FROM events', skill({'required_zero_fill': True}),
        before_business_validation=never_revalidate,
    )
    assert violation is not None


def test_explicit_business_rule_can_still_be_resolved_by_knowledge():
    calls = []
    assert _data_skill_sql_validation_violation(
        '金额', 'SELECT net_amount FROM events',
        skill({'rule_type': 'business', 'required_sql_contains': ['legacy_amount']}),
        resolve_conflict=lambda *args: calls.append(args) or True,
    ) is None
    assert len(calls) == 1


@pytest.mark.parametrize('rule', [
    {'required_fields': ['sample_count']},
    {'rule_type': 'business', 'required_fields': ['sample_count']},
    {'rule_type': 'business', 'sequence_field': 'day', 'require_continuous_sequence': True},
])
def test_analysis_result_contracts_never_call_knowledge(rule):
    from apps.analysis_assistant.api import analysis_assistant as api
    calls = []
    result = {'fields': ['day', 'amount'], 'data': [{'day': 1, 'amount': 2}, {'day': 3, 'amount': 4}]}
    error = api._semantic_validation_error(
        {}, result, '<!-- data-skill-validation: ' + json.dumps(rule) + ' -->',
        resolve_conflict=lambda *args: calls.append(args) or True,
    )
    assert error
    assert not calls


@pytest.mark.parametrize('initial_status', ['invalid_output', 'resolved'])
def test_guard_pins_evidence_and_never_reopens_rule_relationship(initial_status):
    obligation = KnowledgeVerdict(
        status=initial_status, relationship='overrides', output_complies=initial_status == 'resolved',
        document_id='6', quote='金额使用净额。', reason='文档明确覆盖旧字段',
    )
    reviews, checks = [], []
    def review(rule, output):
        reviews.append((rule, output))
        return obligation
    def verify(evidence, output):
        checks.append((evidence, output))
        return evidence.model_copy(update={'status': 'resolved', 'output_complies': True})
    guard = KnowledgeReviewGuard(review, verify)
    if initial_status == 'invalid_output':
        with pytest.raises(KnowledgeOutputValidationError):
            guard.resolve('旧规则', 'SELECT old_amount')
    else:
        assert guard.resolve('旧规则', 'SELECT net_amount')
    guard.revalidate('SELECT net_amount, day')
    guard.revalidate('SELECT net_amount, day')
    assert len(reviews) == 1
    assert len(checks) == 1
    assert checks[0][0].document_id == '6'
    assert checks[0][0].quote == '金额使用净额。'


def test_no_knowledge_context_does_not_invoke_reviewer():
    from apps.knowledge_base.authority import create_knowledge_review_guard
    class NeverCall:
        def invoke(self, *args, **kwargs):
            pytest.fail('empty knowledge must not invoke LLM')
    assert not create_knowledge_review_guard(NeverCall(), '').resolve('业务规则', 'SELECT amount')


def test_new_obligation_invalidates_earlier_unrelated_decision():
    verdicts = iter([
        KnowledgeVerdict(status='not_applicable', relationship='unrelated', reason='无覆盖'),
        KnowledgeVerdict(status='invalid_output', relationship='overrides', output_complies=False,
                         document_id='6', quote='必须使用净额。', reason='字段错误'),
    ])
    checked = []
    def verify(evidence, output):
        checked.append(output)
        return evidence
    guard = KnowledgeReviewGuard(lambda *args: next(verdicts), verify)
    assert not guard.resolve('金额规则', 'SELECT old_amount')
    with pytest.raises(KnowledgeOutputValidationError):
        guard.resolve('金额规则', 'SELECT another_amount')
    with pytest.raises(KnowledgeOutputValidationError):
        guard.revalidate('SELECT old_amount')
    assert checked == ['SELECT old_amount']


@pytest.mark.parametrize('change', [
    {'status': 'not_applicable', 'relationship': 'unrelated', 'output_complies': None, 'document_id': None, 'quote': None},
    {'quote': '金额以退款后净额计算。'},
])
def test_revalidation_rejects_changed_relationship_or_evidence(change):
    from apps.knowledge_base.authority import create_knowledge_review_guard
    from apps.knowledge_base.context import KnowledgeContextError
    from test_knowledge_review_repair import CONTEXT, Responses
    original = dict(status='invalid_output', relationship='overrides', output_complies=False,
                    document_id='6', quote='渠道使用 source_code。', reason='字段不符')
    changed = {**original, 'status': 'resolved', 'output_complies': True, **change}
    model = Responses(json.dumps(original), json.dumps(changed), json.dumps(changed))
    guard = create_knowledge_review_guard(model, CONTEXT)
    with pytest.raises(KnowledgeOutputValidationError):
        guard.resolve('旧字段', 'SELECT old_source')
    with pytest.raises(KnowledgeContextError) as error:
        guard.revalidate('SELECT source_code')
    assert error.value.code == 'knowledge_review_invalid_response'
    assert len(model.calls) == 3
    payload = json.loads(model.calls[1][0][1].content)
    assert payload['verified_obligation']['quote'] == original['quote']
    assert 'lower_priority_rule' not in payload
