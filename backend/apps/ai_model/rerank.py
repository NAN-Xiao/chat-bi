"""OpenAI-compatible reranking client used by knowledge retrieval."""

from __future__ import annotations

import math
import threading

import httpx
from pydantic import BaseModel

from apps.ai_model.embedding import _load_default_ai_model_connection
from common.core.config import settings


class RerankModelInfo(BaseModel):
    model: str = settings.KNOWLEDGE_RETRIEVAL_RERANK_MODEL
    api_base_url: str | None = settings.KNOWLEDGE_RETRIEVAL_RERANK_API_BASE_URL
    api_key: str | None = settings.KNOWLEDGE_RETRIEVAL_RERANK_API_KEY
    timeout: int = settings.KNOWLEDGE_RETRIEVAL_RERANK_REQUEST_TIMEOUT


class OpenAICompatibleReranker:
    """Call a rerank endpoint and return a complete, validated score list."""

    def __init__(self, config: RerankModelInfo):
        api_base_url = config.api_base_url
        api_key = config.api_key
        if not api_base_url or not api_key:
            default_api_base_url, default_api_key = _load_default_ai_model_connection()
            api_base_url = api_base_url or default_api_base_url
            api_key = api_key or default_api_key
        if not api_base_url:
            raise ValueError("Knowledge rerank API base URL is not configured")
        if not api_key:
            raise ValueError("Knowledge rerank API key is not configured")
        if not config.model.strip():
            raise ValueError("Knowledge rerank model is not configured")
        self.config = config.model_copy(update={"api_base_url": api_base_url, "api_key": api_key})
        self._url = self._build_rerank_url(api_base_url)

    @staticmethod
    def _build_rerank_url(api_base_url: str) -> str:
        base_url = api_base_url.rstrip("/")
        if base_url.endswith("/rerank"):
            return base_url
        return f"{base_url}/rerank"

    def rerank(self, query: str, documents: list[str]) -> list[tuple[int, float]]:
        if not documents:
            return []
        payload = {
            "model": self.config.model,
            "query": query,
            "documents": documents,
            "top_n": len(documents),
            "return_documents": False,
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.config.timeout) as client:
                response = client.post(self._url, headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            response_text = exc.response.text[:1000] if exc.response is not None else ""
            raise RuntimeError(
                f"Knowledge rerank request failed: HTTP {exc.response.status_code} {response_text}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Knowledge rerank request failed: {exc}") from exc

        raw_results = body.get("results") if isinstance(body, dict) else None
        if raw_results is None and isinstance(body, dict):
            raw_results = body.get("data")
        if not isinstance(raw_results, list):
            raise RuntimeError("Knowledge rerank response missing results list")

        scores: list[tuple[int, float]] = []
        seen: set[int] = set()
        for item in raw_results:
            if not isinstance(item, dict):
                raise RuntimeError("Knowledge rerank response item must be an object")
            try:
                index = int(item["index"])
                value = item.get("relevance_score", item.get("score"))
                score = float(value)
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError("Knowledge rerank response item has invalid index or score") from exc
            if index < 0 or index >= len(documents) or index in seen or not math.isfinite(score):
                raise RuntimeError("Knowledge rerank response contains invalid or duplicate document indexes")
            seen.add(index)
            scores.append((index, score))

        expected_indexes = set(range(len(documents)))
        if seen != expected_indexes:
            raise RuntimeError("Knowledge rerank response does not score every candidate document")
        return sorted(scores, key=lambda item: (-item[1], item[0]))


_rerank_models: dict[str, OpenAICompatibleReranker] = {}
_rerank_lock = threading.Lock()


class RerankModelCache:
    @staticmethod
    def get_model(config: RerankModelInfo | None = None) -> OpenAICompatibleReranker:
        resolved_config = config or RerankModelInfo()
        key = ":".join(
            (
                resolved_config.model,
                resolved_config.api_base_url or "",
            )
        )
        model = _rerank_models.get(key)
        if model is None:
            with _rerank_lock:
                model = _rerank_models.get(key)
                if model is None:
                    model = OpenAICompatibleReranker(resolved_config)
                    _rerank_models[key] = model
        return model


__all__ = ["OpenAICompatibleReranker", "RerankModelInfo", "RerankModelCache"]
