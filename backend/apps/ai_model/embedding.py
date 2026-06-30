import math
import threading
from typing import Optional

import httpx
from langchain_core.embeddings import Embeddings
from pydantic import BaseModel
from sqlmodel import Session, select

from apps.system.models.system_model import AiModelDetail
from common.core.config import settings
from common.core.db import engine
from common.utils.crypto import shuzhi_decrypt_sync


class EmbeddingModelInfo(BaseModel):
    model: str = settings.EMBEDDING_MODEL or settings.DEFAULT_EMBEDDING_MODEL
    api_base_url: Optional[str] = settings.EMBEDDING_API_BASE_URL
    api_key: Optional[str] = settings.EMBEDDING_API_KEY
    timeout: int = settings.EMBEDDING_REQUEST_TIMEOUT
    batch_size: int = settings.EMBEDDING_BATCH_SIZE
    normalize_embeddings: bool = settings.EMBEDDING_NORMALIZE


_lock = threading.Lock()
locks = {}
_embedding_model: dict[str, Optional[Embeddings]] = {}


def _normalize_api_base_url(raw_url: Optional[str]) -> Optional[str]:
    if raw_url is None:
        return None
    url = raw_url.strip().rstrip("/")
    if not url:
        return None
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("Embedding API base URL must start with http:// or https://")
    return url


def _load_default_ai_model_connection() -> tuple[Optional[str], Optional[str]]:
    if not settings.EMBEDDING_USE_DEFAULT_AI_MODEL_CONFIG:
        return None, None

    with Session(engine) as session:
        db_model = session.exec(
            select(AiModelDetail).where(AiModelDetail.default_model == True)
        ).first()
        if not db_model:
            return None, None

        api_base_url = shuzhi_decrypt_sync(db_model.api_domain)
        api_key = shuzhi_decrypt_sync(db_model.api_key)
        return api_base_url, api_key


def _build_default_config() -> EmbeddingModelInfo:
    api_base_url = settings.EMBEDDING_API_BASE_URL
    api_key = settings.EMBEDDING_API_KEY

    if not api_base_url or not api_key:
        default_api_base_url, default_api_key = _load_default_ai_model_connection()
        api_base_url = api_base_url or default_api_base_url
        api_key = api_key or default_api_key

    return EmbeddingModelInfo(
        model=settings.EMBEDDING_MODEL or settings.DEFAULT_EMBEDDING_MODEL,
        api_base_url=_normalize_api_base_url(api_base_url),
        api_key=api_key,
        timeout=settings.EMBEDDING_REQUEST_TIMEOUT,
        batch_size=max(settings.EMBEDDING_BATCH_SIZE, 1),
        normalize_embeddings=settings.EMBEDDING_NORMALIZE,
    )


def _normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [value / norm for value in vector]


class OpenAICompatibleEmbeddings(Embeddings):
    def __init__(self, config: EmbeddingModelInfo):
        if not config.api_base_url:
            raise ValueError("Embedding API base URL is not configured")
        if not config.api_key:
            raise ValueError("Embedding API key is not configured")
        self.config = config
        self._url = self._build_embeddings_url(config.api_base_url)

    @staticmethod
    def _build_embeddings_url(api_base_url: str) -> str:
        base_url = api_base_url.rstrip("/")
        if base_url.endswith("/embeddings"):
            return base_url
        return f"{base_url}/embeddings"

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "input": texts,
        }

        try:
            with httpx.Client(timeout=self.config.timeout) as client:
                response = client.post(self._url, headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            response_text = exc.response.text[:1000] if exc.response is not None else ""
            raise RuntimeError(
                f"Embedding request failed: HTTP {exc.response.status_code} {response_text}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Embedding request failed: {exc}") from exc

        data = body.get("data")
        if not isinstance(data, list):
            raise RuntimeError("Embedding response missing data list")

        data = sorted(data, key=lambda item: item.get("index", 0))
        vectors = []
        for item in data:
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                raise RuntimeError("Embedding response item missing embedding list")
            vector = [float(value) for value in embedding]
            vectors.append(_normalize_vector(vector) if self.config.normalize_embeddings else vector)

        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Embedding response count mismatch: expected {len(texts)}, got {len(vectors)}"
            )

        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float]] = []
        batch_size = max(self.config.batch_size, 1)
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            vectors.extend(self._embed_batch(batch))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class EmbeddingModelCache:
    @staticmethod
    def _new_instance(config: Optional[EmbeddingModelInfo] = None) -> Embeddings:
        if settings.EMBEDDING_PROVIDER != "openai":
            raise ValueError(f"Unsupported embedding provider: {settings.EMBEDDING_PROVIDER}")
        return OpenAICompatibleEmbeddings(config or _build_default_config())

    @staticmethod
    def _get_lock(key: str):
        lock = locks.get(key)
        if lock is None:
            with _lock:
                lock = locks.get(key)
                if lock is None:
                    lock = threading.Lock()
                    locks[key] = lock

        return lock

    @staticmethod
    def get_model(
        key: Optional[str] = None,
        config: Optional[EmbeddingModelInfo] = None,
    ) -> Embeddings:
        resolved_config = config or _build_default_config()
        resolved_key = key or (
            f"{settings.EMBEDDING_PROVIDER}:"
            f"{resolved_config.api_base_url}:"
            f"{resolved_config.model}"
        )
        model_instance = _embedding_model.get(resolved_key)
        if model_instance is None:
            lock = EmbeddingModelCache._get_lock(resolved_key)
            with lock:
                model_instance = _embedding_model.get(resolved_key)
                if model_instance is None:
                    model_instance = EmbeddingModelCache._new_instance(resolved_config)
                    _embedding_model[resolved_key] = model_instance

        return model_instance
