"""Read-only adapters for existing tracking metadata and structured knowledge."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from apps.datasource.crud.semantic_object_key import DeclaredObjectPath
from apps.knowledge_base.object_references import ProjectedObjectReference
from apps.knowledge_base.object_resolution import resolve_references_for_context
from apps.system.crud.tracking_config import get_tracking_config


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


def load_tracking_structured_records(
    session: Any,
    *,
    tenant_id: int,
    datasource_id: int,
    permission_snapshot: Any | None = None,
    resolver: Callable[..., list[Any]] | None = None,
) -> TrackingStructuredRecords:
    """Project tracking config into immutable records without writing source rows."""
    config = get_tracking_config(session, int(tenant_id), int(datasource_id), include_legacy=True)
    if not getattr(config, "enabled", True):
        return TrackingStructuredRecords()
    if permission_snapshot is not None and int(permission_snapshot.datasource_id) != int(datasource_id):
        return TrackingStructuredRecords(warnings=("事件配置与当前数据源不一致。",))

    table_name = _text(getattr(config, "default_event_table", None))
    event_name_field = _text(getattr(config, "default_event_name_field", None))
    event_time_field = _text(getattr(config, "default_event_time_field", None)) or None
    if not table_name or not event_name_field:
        return TrackingStructuredRecords(warnings=("当前工作空间未配置完整的事件表和事件名字段。",))

    events: list[StructuredEventRecord] = []
    for index, mapping in enumerate(getattr(config, "event_name_mappings", None) or ()):
        if not isinstance(mapping, dict):
            continue
        properties = tuple(_property(item) for item in (mapping.get("properties") or ()) if isinstance(item, dict))
        properties = tuple(item for item in properties if item["name"])
        for event_name in _event_names(mapping):
            record = StructuredEventRecord(
                event_name=event_name,
                display_name=_first(mapping, "event_display_name", "display_name", "metric", "name") or event_name,
                description=_first(mapping, "description", "event_description", "ai_notes"),
                table_name=table_name,
                event_name_field=event_name_field,
                event_time_field=event_time_field,
                parameters=properties,
                source_identity=("TRACKING_CONFIG", int(getattr(config, "id", 0) or 0), index, event_name),
                source_hash=_hash({"mapping": mapping, "event_name": event_name, "datasource_id": int(datasource_id)}),
            )
            refs = _event_references(record)
            if _references_allowed(
                session,
                refs,
                permission_snapshot=permission_snapshot,
                resolver=resolver,
            ):
                events.append(record)

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
            value_mappings=_mapping(getattr(row, "value_mappings", None)),
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
    return TrackingStructuredRecords(events=tuple(events), json_fields=tuple(json_fields))


def _event_references(record: StructuredEventRecord) -> list[ProjectedObjectReference]:
    references = [
        ProjectedObjectReference(
            object_type="EVENT",
            declared_path=DeclaredObjectPath(
                object_type="EVENT",
                table=record.table_name,
                field=record.event_name_field,
                event_name=record.event_name,
            ),
            declared_key="",
            source_kind="STRUCTURED_PAYLOAD",
        )
    ]
    references.extend(
        ProjectedObjectReference(
            object_type="EVENT_PROPERTY",
            declared_path=DeclaredObjectPath(
                object_type="EVENT_PROPERTY",
                table=record.table_name,
                field=str(item["name"]),
                event_name=record.event_name,
                event_property_key=str(item["name"]),
            ),
            declared_key="",
            source_kind="STRUCTURED_PAYLOAD",
        )
        for item in record.parameters
    )
    return references


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


def _event_names(mapping: dict[str, Any]) -> list[str]:
    values = [mapping.get(key) for key in ("event_name", "eventName", "name", "value")]
    if isinstance(mapping.get("events"), list):
        values.extend(mapping["events"])
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result


def _property(value: dict[str, Any]) -> dict[str, Any]:
    name = _first(value, "property_name", "propertyName", "field_name", "fieldName", "name")
    return {
        "name": name,
        "display_name": _first(value, "property_display_name", "display_name", "label") or name,
        "data_type": _first(value, "property_type", "semantic_type", "field_type", "type"),
        "description": _first(value, "description", "ai_notes"),
        "source_field": _text(value.get("source_field")),
        "json_path": _text(value.get("json_path")),
    }


def _first(value: Any, *keys: str) -> str:
    if not isinstance(value, dict):
        return ""
    for key in keys:
        text = _text(value.get(key))
        if text:
            return text
    return ""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    return {}


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
