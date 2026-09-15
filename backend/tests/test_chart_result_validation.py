from types import SimpleNamespace

import pytest

from apps.chat.task import llm
from common.error import SingleMessageError
from common.utils.chart_result_validation import validate_temporal_query_result


@pytest.mark.parametrize('rows', [
    [{'day': None, 'value': value} for value in [56, 60, 79, 70, 79, 72, 63]],
    [{'value': 56}],
    [{'day': '2026-09-08', 'value': 56}, {'day': None, 'value': 60}],
])
def test_invalid_trend_is_rejected_before_chart_save(monkeypatch, rows):
    saved = []
    monkeypatch.setattr(llm, 'save_chart', lambda **kwargs: saved.append(kwargs))
    service = SimpleNamespace(chat_date_pivot=None, record=SimpleNamespace(id=1))
    with pytest.raises(SingleMessageError):
        llm.LLMService.check_save_chart(
            service, session=None,
            res='{"type":"line","axis":{"x":{"value":"day"},"y":[{"value":"value"}]}}',
            result={'fields': ['day', 'value'], 'data': rows},
        )
    assert saved == []


@pytest.mark.parametrize('rows', [
    [],
    [{'day': '2026-09-08', 'value': 0}],
    [{'day': '2026-09-08', 'value': None}],
    [{'day': '2026-09-08', 'value': 2}, {'day': '2026-09-08', 'value': 3}],
])
def test_valid_trends_keep_original_rows(monkeypatch, rows):
    saved = []
    monkeypatch.setattr(llm, 'save_chart', lambda **kwargs: saved.append(kwargs))
    service = SimpleNamespace(chat_date_pivot=None, record=SimpleNamespace(id=1))
    llm.LLMService.check_save_chart(
        service, session=None,
        res='{"type":"line","axis":{"x":{"value":"day"},"y":[{"value":"value"}]}}',
        result={'fields': ['day', 'value'], 'data': rows},
    )
    assert len(saved) == 1


def test_invalid_trend_cannot_be_exported_as_image(monkeypatch):
    requests = []
    monkeypatch.setattr(llm.requests, 'post', lambda **kwargs: requests.append(kwargs))
    with pytest.raises(SingleMessageError):
        llm.request_picture(
            1, 2, {'type': 'line', 'axis': {'x': {'value': 'day'}}},
            {'fields': ['day', 'value'], 'data': [{'day': None, 'value': 10}]},
        )
    assert requests == []


def test_auxiliary_nullable_date_is_not_assumed_to_be_axis():
    sql = 'SELECT CAST(order_day AS DATE) AS day, total, CAST(shipped_at AS DATE) AS shipped_day FROM orders'
    result = {'fields': ['day', 'total', 'shipped_day'], 'data': [{'day': '2026-09-08', 'total': 56, 'shipped_day': None}]}
    validate_temporal_query_result(sql, 'mysql', result, 'line')
    validate_temporal_query_result(sql, 'mysql', result, 'line', dimension='day')
    with pytest.raises(SingleMessageError):
        validate_temporal_query_result(sql, 'mysql', result, 'line', dimension='shipped_day')


def test_date_function_null_result_is_rejected():
    with pytest.raises(SingleMessageError):
        validate_temporal_query_result('SELECT DATE(raw_day) AS day FROM orders', 'mysql', {'data': [{'day': None}]}, 'line')


def test_time_only_trend_is_valid():
    validate_temporal_query_result("SELECT STR_TO_DATE(raw_time, '%H:%i:%s') AS clock FROM orders", 'mysql', {'data': [{'clock': '12:30:00'}]}, 'line')
