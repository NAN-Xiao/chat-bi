"""Canonical identities for physical and tracking semantic objects."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from apps.datasource.models.datasource import CoreField, CoreTable

SemanticObjectType = Literal[
    "SCHEMA",
    "TABLE",
    "FIELD",
    "JSON_PATH",
    "EVENT",
    "EVENT_PROPERTY",
]


@dataclass(frozen=True)
class DeclaredObjectPath:
    object_type: SemanticObjectType
    catalog: str | None = None
    schema: str | None = None
    table: str | None = None
    field: str | None = None
    json_path: str | None = None
    event_name: str | None = None
    event_property_key: str | None = None


@dataclass(frozen=True)
class SemanticObjectKey:
    object_type: SemanticObjectType
    tenant_id: int
    datasource_id: int
    catalog: str | None = None
    schema: str | None = None
    table: str | None = None
    field: str | None = None
    json_path: str | None = None
    event_name: str | None = None
    event_property_key: str | None = None


@dataclass(frozen=True)
class NormalizedTableIdentity:
    catalog_name: str | None
    schema_name: str | None
    table_name: str
    catalog_key: str
    schema_key: str
    table_key: str
    complete: bool
    incomplete_reason: str | None = None


def canonical_object_key(value: SemanticObjectKey) -> str:
    payload = dataclasses.asdict(value)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _unquote_identifier(value: str | None) -> tuple[str, bool]:
    text = str(value or "").strip()
    if len(text) >= 2:
        pairs = {'"': '"', "`": "`", "[": "]"}
        closing = pairs.get(text[0])
        if closing is not None and text[-1] == closing:
            return text[1:-1], True
    return text, False


def normalize_catalog_identifier(value: str | None, *, dialect: str | None) -> str:
    text, quoted = _unquote_identifier(value)
    dialect_key = str(dialect or "").strip().casefold()
    if quoted and dialect_key in {
        "pg",
        "postgres",
        "postgresql",
        "redshift",
        "kingbase",
        "oracle",
        "dm",
    }:
        return text
    if dialect_key in {"oracle", "dm"}:
        return text.upper()
    return text.casefold()


def normalize_discovered_identifier(value: str | None, *, dialect: str | None) -> str:
    text = str(value or "").strip()
    dialect_key = str(dialect or "").strip().casefold()
    if dialect_key in {
        "pg",
        "postgres",
        "postgresql",
        "redshift",
        "kingbase",
        "oracle",
        "dm",
    }:
        return text
    return text.casefold()


def normalized_table_identity(
    *,
    datasource_type: str | None,
    configuration: Mapping[str, object] | None,
    table_name: str,
    catalog_name: str | None = None,
    schema_name: str | None = None,
) -> NormalizedTableIdentity:
    config = configuration or {}
    dialect = str(datasource_type or "").strip().casefold()
    raw_catalog = str(catalog_name or "").strip() or None
    raw_schema = str(schema_name or "").strip() or None

    if raw_schema is None:
        configured_schema = str(config.get("dbSchema") or "").strip()
        configured_database = str(config.get("database") or "").strip()
        if configured_schema:
            raw_schema = configured_schema
        elif dialect in {"pg", "postgres", "postgresql", "redshift", "kingbase"}:
            raw_schema = "public"
        elif dialect == "sqlserver":
            raw_schema = "dbo"
        elif dialect in {"mysql", "doris", "starrocks", "ck", "clickhouse", "hive"}:
            raw_schema = configured_database or None

    schema_required = dialect in {
        "pg",
        "postgres",
        "postgresql",
        "redshift",
        "kingbase",
        "sqlserver",
        "oracle",
        "dm",
        "mysql",
        "doris",
        "starrocks",
        "ck",
        "clickhouse",
        "hive",
    }
    complete = bool(str(table_name or "").strip()) and (
        not schema_required or raw_schema is not None
    )
    return NormalizedTableIdentity(
        catalog_name=raw_catalog,
        schema_name=raw_schema,
        table_name=str(table_name or "").strip(),
        catalog_key=normalize_discovered_identifier(raw_catalog, dialect=dialect),
        schema_key=normalize_discovered_identifier(raw_schema, dialect=dialect),
        table_key=normalize_discovered_identifier(table_name, dialect=dialect),
        complete=complete,
        incomplete_reason=None if complete else "CATALOG_SCHEMA_REQUIRED",
    )


def physical_schema_hash(
    tables: Iterable[CoreTable],
    fields: Iterable[CoreField],
) -> str:
    field_rows: dict[int, list[dict[str, str]]] = {}
    for field in fields:
        field_rows.setdefault(int(field.table_id), []).append(
            {
                "field": str(field.field_key or ""),
                "type": str(field.field_type or "").strip().casefold(),
            }
        )
    payload = []
    for table in tables:
        payload.append(
            {
                "catalog": str(table.catalog_key or ""),
                "schema": str(table.schema_key or ""),
                "table": str(table.table_key or ""),
                "fields": sorted(
                    field_rows.get(int(table.id), []),
                    key=lambda item: (item["field"], item["type"]),
                ),
            }
        )
    payload.sort(key=lambda item: (item["catalog"], item["schema"], item["table"]))
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
