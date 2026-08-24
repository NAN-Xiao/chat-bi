"""Read-only adapters for existing tracking metadata and structured knowledge."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from apps.datasource.crud.semantic_object_key import DeclaredObjectPath
from apps.knowledge_base.backfill import LegacyV2ParityReport
from apps.knowledge_base.backfill import (
    verify_legacy_v2_parity as _verify_legacy_v2_parity,
)
from apps.knowledge_base.object_references import ProjectedObjectReference
from apps.knowledge_base.object_resolution import resolve_references_for_context
from apps.system.crud.tracking_config import (
    get_tracking_config,
    project_tracking_config_for_ai_context,
)


@dataclass(frozen=True)
class StructuredEventRecord:
    event_name: str
    display_name: str
    description: str
    table_name: str
    event_name_field: str
    event_time_field: str | None
    parameters: tuple[dict[str, Any], ...]
    source_identity: tuple[Any, ...]
    source_hash: str


@dataclass(frozen=True)
class StructuredJsonFieldRecord:
    schema_name: str | None
    table_name: str
    source_field: str
    json_path: str
    field_name: str
    display_name: str
    data_type: str
    expression: str
    description: str
    value_mappings: dict[str, str]
    source_identity: tuple[Any, ...]
    source_hash: str


@dataclass(frozen=True)
class TrackingStructuredRecords:
    events: tuple[StructuredEventRecord, ...] = ()
    json_fields: tuple[StructuredJsonFieldRecord, ...] = ()
    warnings: tuple[str, ...] = ()


def verify_legacy_v2_source_parity(session: Any, *, mismatch_limit: int = 50) -> LegacyV2ParityReport:
    """Expose the cutover dual-read check beside the source adapters."""
    return _verify_legacy_v2_parity(session, mismatch_limit=mismatch_limit)


def verify_legacy_v2_parity(session: Any, *, mismatch_limit: int = 50) -> LegacyV2ParityReport:
    """Compatibility name for callers that keep parity checks with source adapters."""
    return verify_legacy_v2_source_parity(session, mismatch_limit=mismatch_limit)


def load_tracking_structured_records(
    session: Any,
    *,
    tenant_id: int,
    datasource_id: int,
    permission_snapshot: Any | None = None,
    resolver: Callable[..., list[Any]] | None = None,
) -> TrackingStructuredRecords:
    """Project tracking config into immutable records without writing source rows."""
    config = project_tracking_config_for_ai_context(
        get_tracking_config(session, int(tenant_id), int(datasource_id))
    )
    if not getattr(config, "enabled", True):
        return TrackingStructuredRecords()
    if permission_snapshot is not None and int(permission_snapshot.datasource_id) != int(datasource_id):
        return TrackingStructuredRecords(warnings=("事件配置与当前数据源不一致。",))

    json_fields: list[StructuredJsonFieldRecord] = []
    for row in getattr(config, "fields", None) or ():
        source_field = _text(getattr(row, "source_field", None))
        json_path = _text(getattr(row, "json_path", None))
        field_name = _text(getattr(row, "field_name", None))
        if not source_field or not json_path or not field_name:
            continue
        record = StructuredJsonFieldRecord(
            schema_name=None,
            table_name=_text(getattr(row, "table_name", None)),
            source_field=source_field,
            json_path=json_path,
            field_name=field_name,
            display_name=_text(getattr(row, "field_comment", None)) or field_name,
            data_type=_text(getattr(row, "semantic_type", None)) or "string",
            expression=_text(getattr(row, "expression", None)),
            description=_text(getattr(row, "ai_notes", None)) or _text(getattr(row, "field_comment", None)),
            value_mappings={},
            source_identity=("TRACKING_FIELD", int(getattr(row, "id", 0) or 0)),
            source_hash=_hash({"field": _safe_model(row), "datasource_id": int(datasource_id)}),
        )
        refs = [
            ProjectedObjectReference(
                object_type="JSON_PATH",
                declared_path=DeclaredObjectPath(
                    object_type="JSON_PATH",
                    table=record.table_name,
                    field=record.source_field,
                    json_path=record.json_path,
                ),
                declared_key="",
                source_kind="STRUCTURED_PAYLOAD",
            )
        ]
        if _references_allowed(
            session,
            refs,
            permission_snapshot=permission_snapshot,
            resolver=resolver,
        ):
            json_fields.append(record)
    return TrackingStructuredRecords(json_fields=tuple(json_fields))


def _references_allowed(session: Any, references: Iterable[ProjectedObjectReference], *, permission_snapshot: Any | None, resolver: Callable[..., list[Any]] | None) -> bool:
    if permission_snapshot is None:
        return True
    resolved = (resolver or resolve_references_for_context)(
        references,
        tenant_id=int(permission_snapshot.tenant_id),
        datasource_id=int(permission_snapshot.datasource_id),
        physical_schema_hash=str(permission_snapshot.schema_hash),
        session=session,
    )
    if any(getattr(item, "status", None) != "RESOLVED" for item in resolved):
        return False
    for item in resolved:
        key = getattr(item, "canonical_key", None)
        if not key or key not in permission_snapshot.allowed_object_keys or key in permission_snapshot.denied_object_keys:
            return False
    return True


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_model(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return {key: getattr(value, key) for key in ("id", "table_name", "field_name", "source_field", "json_path", "expression")}


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


__all__ = [
    "StructuredEventRecord",
    "StructuredJsonFieldRecord",
    "TrackingStructuredRecords",
    "load_tracking_structured_records",
]
