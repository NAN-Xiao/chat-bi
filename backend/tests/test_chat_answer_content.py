"""用户正文必须来自本次模型响应，流式显示不能泄漏 SQL/JSON 或改变旧事件。"""

import json
from types import SimpleNamespace

import pytest

from apps.chat.task import assistant_output
from apps.chat.task import llm
from apps.chat.task.llm import LLMService
from apps.chat.curd.chat import format_record
from apps.chat.models.chat_model import ChatInfo, ChatRecordResult


def consume(generator):
    events = []
    while True:
        try:
            events.append(json.loads(next(generator).removeprefix('data:')))
        except StopIteration as result:
            return events, result.value


@pytest.mark.parametrize('size', [1, 7, 1024])
def test_sql_stream_publishes_only_explicit_answer_text_and_preserves_sql(size):
    raw = json.dumps({
        'answer_content': '已确认字段。\n将按“类别”查询 📊',
        'success': True, 'sql': 'SELECT private_column FROM permitted_table',
        'nested': {'answer_content': '不应显示嵌套字段'},
    }, ensure_ascii=True)
    chunks = [{'content': raw[i:i + size], 'reasoning_content': ''} for i in range(0, len(raw), size)]
    service = SimpleNamespace(generate_sql=lambda *_args, **_kwargs: iter([
        {'content': '', 'reasoning_content': '原有推理事件'}, *chunks,
    ]))

    events, returned = consume(LLMService.generate_sql_text_streaming_reasoning(service, None, in_chat=True))

    assert returned == raw
    assert [e for e in events if e['type'] == 'sql-result'] == [
        {'type': 'sql-result', 'content': '', 'reasoning_content': '原有推理事件'}]
    body = [e for e in events if e['type'] == 'answer-content']
    assert body, '用户正文尚未通过任务事件发送'
    assert body[-1] == {'type': 'answer-content', 'source': 'sql', 'content': '已确认字段。\n将按“类别”查询 📊'}
    assert all('private_column' not in e['content'] and '嵌套' not in e['content'] for e in body)
    for event in body:
        event['content'].encode('utf-8')  # 分块的 Unicode 转义不得产生孤立 surrogate。


@pytest.mark.parametrize('raw', [
    '{"success":true,"sql":"SELECT 1"}',
    '{"answer_content":null,"sql":"SELECT 1"}',
    '{"nested":{"answer_content":"不应展示"},"sql":"SELECT 1"}',
])
def test_missing_answer_field_never_substitutes_raw_model_output(raw):
    service = SimpleNamespace(generate_sql=lambda *_args, **_kwargs: iter([{'content': raw}]))
    events, returned = consume(LLMService.generate_sql_text_streaming_reasoning(service, None, in_chat=True))
    assert returned == raw
    assert not any(e.get('content') for e in events if e['type'] == 'answer-content')


def test_non_chat_sql_generation_keeps_original_output():
    raw = '{"answer_content":"普通正文","sql":"SELECT 1"}'
    service = SimpleNamespace(generate_sql=lambda *_args, **_kwargs: iter([{'content': raw}]))
    events, returned = consume(LLMService.generate_sql_text_streaming_reasoning(service, None, in_chat=False))
    assert events == []
    assert returned == raw
    assert llm._parse_sql_answer_data(raw)['answer_content'] == '普通正文'


def test_chart_stream_preserves_existing_events_and_separates_body(monkeypatch):
    emitted = []
    monkeypatch.setattr(assistant_output, 'emit', lambda event: emitted.append(json.loads(event.removeprefix('data:'))))
    chunks = [
        {'content': '{"answer_content":"将使用', 'reasoning_content': '推理'},
        {'content': '表格展示。","type":"table","columns":[]}', 'reasoning_content': ''},
    ]
    returned = assistant_output.emit_stream_text(
        chunks, in_chat=True, stream=False, event_type='chart-result', answer_content_source='chart',
    )
    assert returned == ''.join(c['content'] for c in chunks)
    assert [e for e in emitted if e['type'] == 'chart-result'] == [
        {'type': 'chart-result', **c} for c in chunks]
    assert [e for e in emitted if e['type'] == 'answer-content'][-1] == {
        'type': 'answer-content', 'source': 'chart', 'content': '将使用表格展示。'}


def test_history_restores_body_without_sql_or_reasoning():
    record = ChatRecordResult(
        id=1, chat_id=2, question='测试',
        sql_answer=json.dumps({'content': json.dumps({'answer_content': '查询正文', 'sql': 'SELECT secret'})}),
        chart_answer=json.dumps({'content': json.dumps({'answer_content': '图表正文', 'type': 'table'})}),
        sql_reasoning_content='旧推理',
    )
    result = format_record(record)
    assert result.get('answer_content') == {'sql': '查询正文', 'chart': '图表正文'}
    assert result['sql_answer'] == '旧推理'
    response = ChatInfo(records=[result])
    assert response.records[0].answer_content == {'sql': '查询正文', 'chart': '图表正文'}
