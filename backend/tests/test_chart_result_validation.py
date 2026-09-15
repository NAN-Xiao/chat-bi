from types import SimpleNamespace

import pytest

from apps.chat.task import llm
from common.error import SingleMessageError


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
