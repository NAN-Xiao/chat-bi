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


def standardized_content(payload: KnowledgePayload, *, scope: str = "") -> str:
    """Render one stable, prompt-safe text representation for all payload types."""
    data = normalize_payload(payload)
    lines = [
        f"knowledge_type: {data.get('knowledge_type', '')}",
        f"scope: {scope}" if scope else "",
    ]
    kind = data.get("knowledge_type")
    if kind == "DOCUMENT":
        lines.extend(["# 文档", data.get("markdown", "")])
        lines.append(f"数据源无关: {str(bool(data.get('datasource_neutral', True))).lower()}")
        if data.get("tags"):
            lines.append("标签: " + ", ".join(data["tags"]))
        if data.get("object_references"):
            lines.append("对象声明: " + _stable_json(data["object_references"]))
    elif kind == "BUSINESS":
        for label, key in (("术语", "term"), ("别名", "aliases"), ("定义", "definition"), ("公式", "formula"), ("约束", "constraints")):
            value = data.get(key)
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            if value:
                lines.append(f"{label}: {value}")
        if data.get("related_objects"):
            lines.append("关联对象: " + _stable_json(data["related_objects"]))
        for index, example in enumerate(data.get("examples", []), start=1):
            lines.extend([
                f"## SQL 示例 {index}: {example.get('name', '')}",
                f"问题: {example.get('question', '')}",
                f"方言: {example.get('dialect', '')}",
                "```sql",
                example.get("sql", ""),
                "```",
                f"说明: {example.get('notes', '')}",
            ])
    elif kind == "EVENT":
        lines.extend([
            f"事件: {data.get('event_name', '')}",
            f"显示名称: {data.get('display_name', '')}",
            f"别名: {', '.join(data.get('aliases', []))}",
            f"说明: {data.get('description', '')}",
            f"来源表: {data.get('table_name', '')}",
            f"事件名字段: {data.get('event_name_field', '')}",
            f"事件时间字段: {data.get('event_time_field', '')}",
        ])
        for parameter in data.get("parameters", []):
            lines.append(
                "参数: {name} ({data_type}) {description}".format(**parameter)
            )
        if data.get("parameters"):
            lines.append("参数映射: " + _stable_json(data["parameters"]))
    elif kind == "JSON_FIELD":
        lines.extend([
            f"表: {data.get('table_name', '')}",
            f"Schema: {data.get('schema_name', '')}",
            f"宿主字段: {data.get('source_field', '')}",
            f"JSON Path: {data.get('json_path', '')}",
            f"字段: {data.get('field_name', '')}",
            f"类型: {data.get('data_type', '')}",
            f"显示名称: {data.get('display_name', '')}",
            f"表达式: {data.get('expression', '')}",
            f"说明: {data.get('description', '')}",
            f"别名: {', '.join(data.get('aliases', []))}",
        ])
        if data.get("value_mappings"):
            lines.append("值映射: " + _stable_json(data["value_mappings"]))
    return normalize_markdown("\n".join(line for line in lines if line is not None))


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
