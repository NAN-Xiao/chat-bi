from __future__ import annotations

import hashlib
import json
from typing import Any

from apps.knowledge_base.schemas import KnowledgePayload, document_markdown


def normalize_markdown(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip(" \t") for line in text.split("\n"))
    return f"{text.rstrip()}\n" if text.strip() else ""


def normalize_payload(payload: KnowledgePayload) -> dict[str, Any]:
    normalized = payload.model_dump(mode="json", by_alias=True, exclude_none=True)
    normalized["blocks"] = [
        {
            **block,
            "title": str(block.get("title") or "").strip(),
            "markdown": normalize_markdown(block.get("markdown", "")),
        }
        for block in normalized.get("blocks", [])
    ]
    normalized["object_references"] = [
        {key: value for key, value in item.items() if not isinstance(value, str) or value.strip()}
        for item in normalized.get("object_references", [])
    ]
    return normalized


def content_hash_for_payload(payload: KnowledgePayload) -> str:
    encoded = json.dumps(normalize_payload(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def standardized_content(payload: KnowledgePayload, *, scope: str = "") -> str:
    """Render one stable, prompt-safe text representation for a document."""
    data = normalize_payload(payload)
    lines = [f"scope: {scope}" if scope else "", "# 文档", document_markdown(payload)]
    lines.append(f"数据源无关: {str(bool(data.get('datasource_neutral', True))).lower()}")
    if data.get("tags"):
        lines.append("标签: " + ", ".join(data["tags"]))
    if data.get("object_references"):
        lines.append("对象声明: " + _stable_json(data["object_references"]))
    return normalize_markdown("\n".join(line for line in lines if line is not None))


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
