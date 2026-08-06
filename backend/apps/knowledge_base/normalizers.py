from __future__ import annotations

import hashlib
import json
from typing import Any

from apps.knowledge_base.schemas import KnowledgePayload


def normalize_markdown(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip(" \t") for line in text.split("\n"))
    return f"{text.rstrip()}\n" if text.strip() else ""


def normalize_payload(payload: KnowledgePayload) -> dict[str, Any]:
    normalized = payload.model_dump(mode="json", by_alias=True, exclude_none=True)
    if normalized.get("knowledge_type") == "DOCUMENT":
        normalized["markdown"] = normalize_markdown(normalized.get("markdown", ""))
    return normalized


def content_hash_for_payload(payload: KnowledgePayload) -> str:
    encoded = json.dumps(normalize_payload(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
