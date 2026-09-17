"""Evidence-backed knowledge decisions shared by assistant surfaces."""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Literal
from xml.etree import ElementTree

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.knowledge_base.context import KNOWLEDGE_CONTEXT_SYSTEM_RULES, KnowledgeContextError
from common.utils.llm_attempts import observe_llm_retries

logger = logging.getLogger(__name__)


class KnowledgeVerdict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    status: Literal['not_applicable', 'resolved', 'invalid_output', 'conflict', 'uncertain']
    relationship: Literal['unrelated', 'supports', 'overrides', 'uncertain']
    reason: str = Field(min_length=1)
    output_complies: bool | None = None
    document_id: str | None = None
    quote: str | None = None
    conflicting_document_id: str | None = None
    conflicting_quote: str | None = None


class KnowledgeOutputValidationError(KnowledgeContextError):
    """Only a verified, applicable business rule can request SQL repair."""
    repairable = True

    def __init__(self, verdict: KnowledgeVerdict):
        self.repair_message = json.dumps({
            'reason': verdict.reason, 'document_id': verdict.document_id,
            'required_rule': verdict.quote,
        }, ensure_ascii=False)
        super().__init__('knowledge_output_invalid', '生成结果未遵循知识库业务规则，需要重新生成。',
                         details={'verdict': verdict.model_dump(), 'repair_message': self.repair_message})


class KnowledgeReviewGuard:
    """Keep verified higher-priority obligations across repairs of one query."""
    def __init__(self, review, verify):
        self.review = review
        self.verify = verify
        self.obligations = {}
        self.decisions = {}

    def resolve(self, rule: str, output: str) -> bool:
        key = (rule, output)
        if key in self.decisions:
            return self.decisions[key]
        obligation = self.obligations.get(rule)
        if obligation is not None:
            verdict = self.verify(obligation, output)
            _validate_pinned_obligation(verdict, obligation)
        else:
            verdict = self.review(rule, output)
        if verdict.relationship == 'overrides' and verdict.status in {'resolved', 'invalid_output'}:
            if obligation is None:
                # Earlier "unrelated" decisions cannot satisfy a newly pinned rule.
                self.decisions = {key: value for key, value in self.decisions.items() if key[0] != rule}
            self.obligations[rule] = verdict
        result = _verdict_allows_override(verdict)
        self.decisions[key] = result
        return result

    def revalidate(self, output: str):
        for rule in sorted(self.obligations):
            self.resolve(rule, output)


def _validate_pinned_obligation(verdict: KnowledgeVerdict, obligation: KnowledgeVerdict):
    if verdict.status in {'uncertain', 'conflict'}:
        return
    if (verdict.status not in {'resolved', 'invalid_output'} or verdict.relationship != 'overrides'
            or verdict.document_id != obligation.document_id or verdict.quote != obligation.quote):
        raise ValueError('Revalidation must check the same verified document and rule, not reopen applicability')


def create_knowledge_review_guard(llm, knowledge_context: str, **options) -> KnowledgeReviewGuard:
    return KnowledgeReviewGuard(
        lambda rule, output: review_business_conflict(llm, knowledge_context, rule, output, **options),
        lambda obligation, output: review_business_conflict(
            llm, knowledge_context, '', output, obligation=obligation, **options),
    )


def _documents(context: str) -> dict[str, dict[str, str]]:
    """Keep every scope and rule; remove only duplicate copies of the same document."""
    root = ElementTree.fromstring(context)
    docs = {}
    for layer in root:
        for doc in layer.findall('.//document'):
            key = doc.get('id')
            if not key:
                raise ValueError('Document ID missing')
            content = '\n'.join(doc.itertext()).strip()
            value = {'scope': layer.tag, 'content': content, 'name': doc.get('name', '')}
            if key in docs and docs[key] != value:
                raise ValueError('Conflicting copies of a document')
            docs[key] = value
    return docs


def _validate_evidence(verdict: KnowledgeVerdict, documents: dict) -> None:
    if verdict.status == 'uncertain':
        return
    if verdict.status == 'not_applicable':
        if verdict.relationship != 'unrelated':
            raise ValueError('not_applicable must be unrelated')
        return
    doc = documents.get(verdict.document_id)
    if not doc or not verdict.quote or not verdict.quote.strip() or verdict.quote not in doc['content']:
        raise ValueError('Missing verifiable document evidence')
    if verdict.relationship not in {'supports', 'overrides'}:
        raise ValueError('Applicable verdict needs a rule relationship')
    if verdict.status in {'resolved', 'invalid_output'}:
        expected_compliance = verdict.status == 'resolved'
        if verdict.output_complies is not expected_compliance:
            raise ValueError('Verdict status disagrees with output compliance')
    if verdict.status == 'resolved' and verdict.relationship != 'overrides':
        raise ValueError('Supporting the original rule cannot override it')
    if verdict.status == 'conflict':
        other = documents.get(verdict.conflicting_document_id)
        if (not other or other['scope'] != doc['scope'] or not verdict.conflicting_quote
                or not verdict.conflicting_quote.strip() or verdict.conflicting_quote not in other['content']
                or (verdict.conflicting_document_id == verdict.document_id and verdict.conflicting_quote == verdict.quote)):
            raise ValueError('Conflict requires two distinct same-scope rules')


_REVIEW_RULES = '''
只裁决输入 lower_priority_rule 的业务规则关系，不审查无关规则，不扩展裁决范围。
先判断知识库是否明确定义了与该规则不同的适用业务规则：
- 无覆盖规则或无关知识：status=not_applicable, relationship=unrelated，保留原校验与修复。
- 文档只是要求遵循原规则/Data Skill：relationship=supports，不是规则冲突；即使输出违规，也交回原校验修复。
- 原规则要求补齐日期，文档也要求补齐日期：两者一致，必须是supports，不能写overrides。
- 有明确覆盖规则且输出符合：status=resolved, relationship=overrides。
- 有明确覆盖规则但输出不符合：status=invalid_output, relationship=overrides，引用正确规则供修复。
- 两条适用同层规则相互矛盾：status=conflict，同时引用两条完整原文；不可按顺序选择。
- 无法确认：status=uncertain；不可将不确定当作允许。
允许覆盖和拒绝输出都必须提供文档ID与逐字原文quote；仅有文档前言、遵循Data Skill的说明不能证明覆盖。
quote只复制documents中直接支持结论的一句完整原文，不要复制章节标题、不要改写、不要从lower_priority_rule复制到quote。
document_id只能取documents对象的键，lower_priority_rule不是知识文档。
区分文档里的参数化示例和已解析SQL。示例出现{{参数名}}本身不能证明最终SQL必须保留占位符。
参数来源和值是否经过授权由配置解析与权限校验负责；你不能批准替换、删除强制过滤或从示例推断授权。
权限、工作空间、当前数据源、只读限制、SQL物理可执行性与输出协议不可被知识覆盖。
输出必须是一个符合下列Schema的JSON对象，不输出Markdown、解释段落或SQL全文。
resolved必须明确output_complies=true；invalid_output必须明确output_complies=false。需要修复的输出绝不能返回resolved。
'''


def review_business_conflict(llm, knowledge_context: str, lower_priority_rule: str, output: str,
                             *, observer: Callable[[dict], None] | None = None,
                             json_mode: bool = False, extra_body: dict | None = None,
                             obligation: KnowledgeVerdict | None = None) -> KnowledgeVerdict:
    if not knowledge_context or not knowledge_context.strip():
        if obligation is not None:
            raise KnowledgeContextError('knowledge_context_invalid', '复核所需的知识文档不可用。')
        return KnowledgeVerdict(status='not_applicable', relationship='unrelated', reason='没有知识文档')
    try:
        documents = _documents(knowledge_context)
    except (ValueError, ElementTree.ParseError) as error:
        raise KnowledgeContextError('knowledge_context_invalid', '知识规则上下文无效，请检查文档配置。') from error
    if not documents:
        return KnowledgeVerdict(status='not_applicable', relationship='unrelated', reason='没有知识文档')
    observer = observer or getattr(llm, 'knowledge_review_observer', None)
    json_mode = json_mode or getattr(llm, 'knowledge_review_json_mode', False)
    extra_body = extra_body if extra_body is not None else getattr(llm, 'knowledge_review_extra_body', None)
    if obligation is not None:
        _validate_evidence(obligation, documents)
    review_rules = _REVIEW_RULES if obligation is None else '''
本次只复核 output 是否遵守 verified_obligation 中已经确认适用的文档原文规则。
不得重新判断该规则是否覆盖低优先级规则，不得改判 not_applicable 或 supports。
遵守时返回 resolved、output_complies=true；不遵守时返回 invalid_output、output_complies=false。
这两种结果 relationship 均为 overrides，document_id 和 quote 必须原样使用 verified_obligation。
无法确认时返回 uncertain；如发现同层文档冲突返回 conflict 并提供两条真实证据。
输出完整 JSON，保留原规则；禁止换用另一段引用或忽略已确认的规则。
'''
    payload = {'documents': documents, 'output': output}
    if obligation is None:
        payload['lower_priority_rule'] = lower_priority_rule
    else:
        payload['verified_obligation'] = obligation.model_dump()
    messages = [
        SystemMessage(content=KNOWLEDGE_CONTEXT_SYSTEM_RULES + review_rules
                      + json.dumps(KnowledgeVerdict.model_json_schema(), ensure_ascii=False)),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False, separators=(',', ':'))),
    ]
    review_id = uuid.uuid4().hex

    def emit(event):
        logger.info('Knowledge review %s', json.dumps(event, ensure_ascii=False, default=str))
        if observer:
            observer(event)

    for attempt in (1, 2):
        call_id = uuid.uuid4().hex
        metadata = {'review_id': review_id, 'call_id': call_id, 'attempt': attempt,
                    'document_ids': list(documents), 'phase': 'revalidate' if obligation else 'resolve',
                    'rule_sha256': hashlib.sha256((obligation.quote if obligation else lower_priority_rule).encode()).hexdigest()}
        started = time.monotonic()
        emit({**metadata, 'event': 'start'})
        retries = []
        try:
            with observe_llm_retries(retries.append):
                invoke_options = {'response_format': {'type': 'json_object'}} if json_mode else {}
                if extra_body:
                    invoke_options['extra_body'] = {**(getattr(llm, 'extra_body', None) or {}), **extra_body}
                response = llm.invoke(messages, **invoke_options)
        except Exception as error:
            emit({**metadata, 'event': 'finish', 'status': 'unavailable', 'usage': {},
                  'sdk_retries': len(retries), 'duration_ms': round((time.monotonic()-started)*1000),
                  'exception_type': type(error).__name__})
            raise KnowledgeContextError('knowledge_review_unavailable', '知识规则校验服务暂时不可用，请重试。') from error
        usage = getattr(response, 'usage_metadata', None) or (getattr(response, 'response_metadata', {}) or {}).get('token_usage') or {}
        verdict = None
        try:
            verdict = KnowledgeVerdict.model_validate_json(response.content)
            _validate_evidence(verdict, documents)
            if obligation is not None:
                _validate_pinned_obligation(verdict, obligation)
        except (ValidationError, ValueError, TypeError) as error:
            emit({**metadata, 'event': 'finish', 'status': 'invalid_response', 'usage': usage,
                  'sdk_retries': len(retries), 'duration_ms': round((time.monotonic()-started)*1000),
                  'validation_error': str(error)[:500], 'rejected_verdict': verdict.model_dump() if verdict else None})
            if attempt == 2:
                raise KnowledgeContextError('knowledge_review_invalid_response', '知识规则校验未返回有效结果，请重试。') from error
            messages.append(HumanMessage(content=(
                '上次裁决未通过校验：' + (str(error) if isinstance(error, ValueError) and not isinstance(error, ValidationError) else 'JSON Schema不匹配')
                + '。请重新返回完整JSON。quote必须逐字复制documents中的一句原文，document_id使用其键。'
                + ('必须继续复核 verified_obligation 的同一原文，禁止重新判定规则适用性。' if obligation else
                   '原知识未定义覆盖规则时返回not_applicable/unrelated，不要引用Data Skill规则作为知识文档。')
            )))
            continue
        emit({**metadata, 'event': 'finish', 'status': verdict.status, 'usage': usage,
              'sdk_retries': len(retries), 'duration_ms': round((time.monotonic()-started)*1000),
              'verdict': verdict.model_dump()})
        return verdict
    raise AssertionError('Review attempt budget exhausted')


def knowledge_resolves_business_conflict(llm, knowledge_context: str, lower_priority_rule: str, output: str,
                                         *, observer=None, json_mode: bool = False, extra_body: dict | None = None) -> bool:
    if not knowledge_context or not knowledge_context.strip():
        return False
    verdict = review_business_conflict(llm, knowledge_context, lower_priority_rule, output,
                                      observer=observer, json_mode=json_mode, extra_body=extra_body)
    return _verdict_allows_override(verdict)


def _verdict_allows_override(verdict: KnowledgeVerdict) -> bool:
    if verdict.status == 'not_applicable' or (verdict.status == 'invalid_output' and verdict.relationship == 'supports'):
        return False
    if verdict.status == 'resolved':
        return True
    if verdict.status == 'invalid_output':
        raise KnowledgeOutputValidationError(verdict)
    messages = {'conflict': '知识库同层业务规则存在冲突，请明确采用的文档口径。',
                'uncertain': '无法确认知识库业务规则冲突，请明确口径。'}
    raise KnowledgeContextError(f'knowledge_{verdict.status}', messages[verdict.status],
                                details={'verdict': verdict.model_dump()})
