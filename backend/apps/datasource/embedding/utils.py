"""
脚本说明：这个脚本放数据源相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from __future__ import annotations

# 作者：Junjun
# 日期：2025/9/23
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

from common.core.config import settings


EMBEDDING_PAYLOAD_VERSION = 1


@dataclass(frozen=True)
class StoredEmbedding:
    """
    是什么：StoredEmbedding 描述库里保存的向量以及它是否匹配当前 embedding 配置。
    """
    vector: list[float] | None
    current: bool
    reason: str
    model: str | None = None
    dim: int | None = None


def embedding_model_identity(model: Any | None = None) -> str:
    """
    是什么：embedding_model_identity 把当前 embedding 模型配置整理成可签名的稳定标识。
    """
    config = getattr(model, "config", None)
    model_name = getattr(config, "model", None) or settings.EMBEDDING_MODEL or settings.DEFAULT_EMBEDDING_MODEL
    normalize_embeddings = getattr(config, "normalize_embeddings", settings.EMBEDDING_NORMALIZE)
    payload = {
        "provider": settings.EMBEDDING_PROVIDER,
        "model": str(model_name or ""),
        "normalize": bool(normalize_embeddings),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def embedding_payload_signature(model_identity: str, dim: int) -> str:
    """
    是什么：embedding_payload_signature 为模型标识和向量维度生成签名。
    """
    payload = {
        "version": EMBEDDING_PAYLOAD_VERSION,
        "model": model_identity,
        "dim": int(dim),
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dump_embedding_payload(vector: list[float], model: Any | None = None) -> str:
    """
    是什么：dump_embedding_payload 把向量和当前模型/维度签名一起保存。
    """
    clean_vector = [float(item) for item in vector]
    model_identity = embedding_model_identity(model)
    dim = len(clean_vector)
    payload = {
        "version": EMBEDDING_PAYLOAD_VERSION,
        "model": model_identity,
        "dim": dim,
        "signature": embedding_payload_signature(model_identity, dim),
        "vector": clean_vector,
    }
    return json.dumps(payload, ensure_ascii=False)


def load_embedding_payload(value: Any, model: Any | None = None) -> StoredEmbedding:
    """
    是什么：load_embedding_payload 读取库里的向量；旧数组格式会被标记为需要重算。
    """
    if value in (None, ""):
        return StoredEmbedding(vector=None, current=False, reason="missing")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return StoredEmbedding(vector=None, current=False, reason="invalid_json")

    if isinstance(value, list):
        try:
            vector = [float(item) for item in value]
        except (TypeError, ValueError):
            return StoredEmbedding(vector=None, current=False, reason="invalid_legacy_vector")
        return StoredEmbedding(vector=vector, current=False, reason="legacy_payload", dim=len(vector))

    if not isinstance(value, dict):
        return StoredEmbedding(vector=None, current=False, reason="invalid_payload")

    raw_vector = value.get("vector")
    if not isinstance(raw_vector, list):
        return StoredEmbedding(vector=None, current=False, reason="missing_vector")
    try:
        vector = [float(item) for item in raw_vector]
    except (TypeError, ValueError):
        return StoredEmbedding(vector=None, current=False, reason="invalid_vector")

    try:
        stored_dim = int(value.get("dim"))
    except (TypeError, ValueError):
        stored_dim = None
    if stored_dim != len(vector):
        return StoredEmbedding(vector=vector, current=False, reason="dim_mismatch", dim=stored_dim)

    current_model = embedding_model_identity(model)
    stored_model = value.get("model")
    expected_signature = embedding_payload_signature(current_model, len(vector))
    if value.get("version") != EMBEDDING_PAYLOAD_VERSION:
        return StoredEmbedding(vector=vector, current=False, reason="version_mismatch", model=stored_model, dim=stored_dim)
    if stored_model != current_model:
        return StoredEmbedding(vector=vector, current=False, reason="model_mismatch", model=stored_model, dim=stored_dim)
    if value.get("signature") != expected_signature:
        return StoredEmbedding(vector=vector, current=False, reason="signature_mismatch", model=stored_model, dim=stored_dim)
    return StoredEmbedding(vector=vector, current=True, reason="ok", model=stored_model, dim=stored_dim)


def embedding_payload_is_current(value: Any, model: Any | None = None) -> bool:
    """
    是什么：embedding_payload_is_current 判断库里的向量是否适配当前 embedding 模型和维度。
    """
    return load_embedding_payload(value, model).current


def cosine_similarity(vec_a, vec_b):
    """
    是什么：cosine_similarity 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if len(vec_a) != len(vec_b):
        raise ValueError("The vector dimension must be the same")

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))

    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)
