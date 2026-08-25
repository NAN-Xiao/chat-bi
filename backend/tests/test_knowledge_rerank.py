"""Rerank client contract tests."""

from __future__ import annotations

import pytest

from apps.ai_model.rerank import OpenAICompatibleReranker, RerankModelInfo


class _Response:
    def __init__(self, body):
        self.body = body
        self.status_code = 200
        self.text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


class _Client:
    response_body = None
    last_request = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, *, headers, json):
        self.last_request = (url, headers, json)
        type(self).last_request = self.last_request
        return _Response(type(self).response_body)


def _reranker() -> OpenAICompatibleReranker:
    return OpenAICompatibleReranker(
        RerankModelInfo(
            model="test-reranker",
            api_base_url="https://example.test/v1",
            api_key="test-key",
            timeout=7,
        )
    )


def test_rerank_sorts_complete_scores_and_sends_all_candidates(monkeypatch):
    _Client.response_body = {
        "results": [
            {"index": 1, "relevance_score": 0.91},
            {"index": 0, "relevance_score": 0.73},
        ]
    }
    monkeypatch.setattr("apps.ai_model.rerank.httpx.Client", _Client)

    result = _reranker().rerank("收入", ["片段一", "片段二"])

    assert result == [(1, 0.91), (0, 0.73)]
    url, headers, payload = _Client.last_request
    assert url == "https://example.test/v1/rerank"
    assert headers["Authorization"] == "Bearer test-key"
    assert payload == {
        "model": "test-reranker",
        "query": "收入",
        "documents": ["片段一", "片段二"],
        "top_n": 2,
        "return_documents": False,
    }


def test_rerank_rejects_incomplete_scores(monkeypatch):
    _Client.response_body = {"results": [{"index": 0, "relevance_score": 0.91}]}
    monkeypatch.setattr("apps.ai_model.rerank.httpx.Client", _Client)

    with pytest.raises(RuntimeError, match="does not score every candidate"):
        _reranker().rerank("收入", ["片段一", "片段二"])
