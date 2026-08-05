"""Catalog hash maintenance for direct psycopg metadata writers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any


def _value(row: Mapping[str, Any] | Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key)


def physical_schema_hash_rows(
    tables: Iterable[Mapping[str, Any] | Any],
    fields: Iterable[Mapping[str, Any] | Any],
) -> str:
    """Match the application's canonical physical schema hash."""
    field_rows: dict[int, list[dict[str, str]]] = {}
    for field in fields:
        field_rows.setdefault(int(_value(field, "table_id")), []).append(
            {
                "field": str(_value(field, "field_key") or ""),
                "type": str(_value(field, "field_type") or "").strip().casefold(),
            }
        )

    payload = []
    for table in tables:
        table_id = int(_value(table, "id"))
        payload.append(
            {
                "catalog": str(_value(table, "catalog_key") or ""),
                "schema": str(_value(table, "schema_key") or ""),
                "table": str(_value(table, "table_key") or ""),
                "fields": sorted(
                    field_rows.get(table_id, []),
                    key=lambda item: (item["field"], item["type"]),
                ),
            }
        )

    payload.sort(key=lambda item: (item["catalog"], item["schema"], item["table"]))
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def refresh_physical_schema_hash_cursor(cursor, *, datasource_id: int) -> str:
    """Validate full catalog keys and restore the datasource hash in this transaction."""
    cursor.execute(
        """
        SELECT id, catalog_key, schema_key, table_key
        FROM public.core_table
        WHERE ds_id = %s
        ORDER BY catalog_key, schema_key, table_key, id
        """,
        (int(datasource_id),),
    )
    tables = list(cursor.fetchall())
    cursor.execute(
        """
        SELECT table_id, field_key, field_type
        FROM public.core_field
        WHERE ds_id = %s
        ORDER BY table_id, field_key, id
        """,
        (int(datasource_id),),
    )
    fields = list(cursor.fetchall())

    invalid_tables = [
        int(_value(row, "id"))
        for row in tables
        if not str(_value(row, "schema_key") or "").strip()
        or str(_value(row, "schema_key")).startswith("__legacy_schema__:")
        or not str(_value(row, "table_key") or "").strip()
    ]
    invalid_fields = [
        int(_value(row, "table_id"))
        for row in fields
        if not str(_value(row, "field_key") or "").strip()
    ]
    if invalid_tables or invalid_fields:
        raise RuntimeError(
            "物理目录键不完整，拒绝生成 Schema hash："
            f"tables={invalid_tables}, field_tables={invalid_fields}"
        )

    schema_hash = physical_schema_hash_rows(tables, fields)
    cursor.execute(
        """
        UPDATE public.core_datasource
        SET catalog_complete = true,
            catalog_incomplete_reason = NULL,
            physical_schema_hash = %s
        WHERE id = %s
        """,
        (schema_hash, int(datasource_id)),
    )
    if cursor.rowcount != 1:
        raise RuntimeError(f"数据源不存在，无法更新 Schema hash：{datasource_id}")
    return schema_hash
