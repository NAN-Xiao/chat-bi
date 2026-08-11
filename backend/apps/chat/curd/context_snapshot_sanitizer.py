"""Whitelist business metadata before it is persisted or returned to clients."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_BUSINESS_CONTEXT_SAFE_FIELDS = frozenset(
    {
        "context_hash",
        "tenant_id",
        "datasource_id",
        "datasource_type",
        "sql_dialect",
        "target_scope",
        "allowed_tables",
        "tracking_warnings",
        "tracking_summary_count",
        "data_skill_count",
        "data_skill_list_sha256",
        "data_skill_model_id",
        "permission_version",
        "schema_hash",
        "knowledge_version_hash",
        "retrieval_failure_type",
        "analysis_time_policy",
        "warnings",
    }
)
_SEMANTIC_CONTEXT_SAFE_FIELDS = frozenset(
    {
        "context_hash",
        "permission_version",
        "schema_hash",
        "skill_selection_hash",
        "knowledge_version_hash",
        "structured_context_hash",
        "retrieval_failure_type",
    }
)
_CITATION_SAFE_FIELDS = frozenset(
    {
        "chunk_id",
        "knowledge_base_id",
        "knowledge_base_name",
        "knowledge_type",
        "version_id",
        "version_number",
        "section_path",
        "source_file_name",
        "score",
        "visibility_scope",
    }
)
_SELECTED_SKILL_SAFE_FIELDS = frozenset(
    {"id", "selection_mode", "source_hash", "target_scope", "visibility_scope"}
)


def _safe_dict(value: Any, allowed_fields: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: deepcopy(item)
        for key, item in value.items()
        if key in allowed_fields
    }


def _safe_dict_list(value: Any, allowed_fields: frozenset[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        sanitized
        for item in value
        if (sanitized := _safe_dict(item, allowed_fields))
    ]


def sanitize_business_context_snapshot(value: dict[str, Any] | None) -> dict[str, Any]:
    """Keep audit metadata while rejecting prompt and knowledge bodies."""
    if not isinstance(value, dict):
        return {}
    snapshot = _safe_dict(value, _BUSINESS_CONTEXT_SAFE_FIELDS)
    snapshot["selected_skills"] = _safe_dict_list(
        value.get("selected_skills"),
        _SELECTED_SKILL_SAFE_FIELDS,
    )
    snapshot["knowledge_citations"] = _safe_dict_list(
        value.get("knowledge_citations"),
        _CITATION_SAFE_FIELDS,
    )
    snapshot["retrieval_warnings"] = [
        str(item) for item in value.get("retrieval_warnings") or [] if str(item).strip()
    ]
    snapshot["warnings"] = [
        str(item) for item in value.get("warnings") or [] if str(item).strip()
    ]

    semantic_value = value.get("business_semantic_context")
    if isinstance(semantic_value, dict):
        semantic = _safe_dict(semantic_value, _SEMANTIC_CONTEXT_SAFE_FIELDS)
        semantic["selected_skills"] = _safe_dict_list(
            semantic_value.get("selected_skills"),
            _SELECTED_SKILL_SAFE_FIELDS,
        )
        semantic["knowledge_citations"] = _safe_dict_list(
            semantic_value.get("knowledge_citations"),
            _CITATION_SAFE_FIELDS,
        )
        semantic["warnings"] = [
            str(item) for item in semantic_value.get("warnings") or [] if str(item).strip()
        ]
        snapshot["business_semantic_context"] = semantic
    return snapshot


__all__ = ["sanitize_business_context_snapshot"]
