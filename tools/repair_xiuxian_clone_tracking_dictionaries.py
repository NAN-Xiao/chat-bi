# -*- coding: utf-8 -*-
"""Repair Xiuxian-clone tracking dictionaries from the canonical source.

The target datasources are product-specific copies of the Xiuxian datasource.
Their physical schemas are identical, but their workspace tracking dictionaries
were accidentally populated with flam / first_zombie metadata. This command
copies the canonical dictionary only after verifying both physical schemas
match, then rewrites each target's datasource, workspace, and product boundaries.

The command is read-only unless ``--apply`` is supplied.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from common.utils.snowflake import snowflake  # noqa: E402


SOURCE_TENANT_ID = 7482727237662281728
SOURCE_DATASOURCE_ID = 6
TARGET_PROFILES = {
    "lds": {
        "tenant_id": 7493272675721154560,
        "datasource_id": 10,
        "product_id": "110000039",
    },
    "unicorn": {
        "tenant_id": 7493583885482070016,
        "datasource_id": 9,
        "product_id": "110000030",
    },
    "j2000": {
        "tenant_id": 7493583991958671360,
        "datasource_id": 11,
        "product_id": "110000034",
    },
    "gig": {
        "tenant_id": 7493272549510352896,
        "datasource_id": 12,
        "product_id": "110000036",
    },
}
TARGET_NAME = "lds"
TARGET_TENANT_ID = int(TARGET_PROFILES[TARGET_NAME]["tenant_id"])
TARGET_DATASOURCE_ID = int(TARGET_PROFILES[TARGET_NAME]["datasource_id"])
TARGET_PRODUCT_ID = str(TARGET_PROFILES[TARGET_NAME]["product_id"])
BACKUP_DIR = ROOT / ".codex-runtime" / "tracking-dictionary-backups"

CONFIG_COLUMNS = (
    "enabled",
    "default_event_table",
    "default_subject_field",
    "default_event_name_field",
    "default_event_time_field",
    "field_role_mappings",
    "event_name_mappings",
    "sql_rules",
    "notes",
)
TABLE_COLUMNS = (
    "table_comment",
    "table_role",
    "aliases",
    "ai_notes",
    "extra_properties",
)
FIELD_COLUMNS = (
    "field_comment",
    "field_role",
    "semantic_type",
    "source_field",
    "json_path",
    "update_mode",
    "category",
    "aliases",
    "value_mappings",
    "expression",
    "required",
    "example_values",
    "ai_notes",
    "extra_properties",
)
JSON_COLUMNS = {
    "field_role_mappings",
    "event_name_mappings",
    "aliases",
    "extra_properties",
    "value_mappings",
    "example_values",
}


def configure_target(workspace: str) -> None:
    global TARGET_NAME, TARGET_TENANT_ID, TARGET_DATASOURCE_ID, TARGET_PRODUCT_ID

    profile = TARGET_PROFILES[workspace]
    TARGET_NAME = workspace
    TARGET_TENANT_ID = int(profile["tenant_id"])
    TARGET_DATASOURCE_ID = int(profile["datasource_id"])
    TARGET_PRODUCT_ID = str(profile["product_id"])


def _transform(value: Any) -> Any:
    if isinstance(value, str):
        return (
            value.replace(
                f"datasource_id={SOURCE_DATASOURCE_ID}",
                f"datasource_id={TARGET_DATASOURCE_ID}",
            )
            .replace("修仙工作空间", f"{TARGET_NAME} 工作空间")
            .replace("prod=110000047", f"prod={TARGET_PRODUCT_ID}")
        )
    if isinstance(value, list):
        return [_transform(item) for item in value]
    if isinstance(value, dict):
        return {key: _transform(item) for key, item in value.items()}
    return value


def _physical_schema(cur: Any, datasource_id: int) -> list[tuple[str, str, str, int]]:
    cur.execute(
        """
        SELECT t.table_name, f.field_name, f.field_type, f.field_index
        FROM core_table AS t
        JOIN core_field AS f ON f.table_id = t.id
        WHERE t.ds_id = %s
        ORDER BY t.table_name, f.field_index, f.field_name
        """,
        (datasource_id,),
    )
    return [
        (
            str(row["table_name"]),
            str(row["field_name"]),
            str(row["field_type"]),
            int(row["field_index"]),
        )
        for row in cur.fetchall()
    ]


def _require_identity(cur: Any) -> None:
    cur.execute(
        """
        SELECT id, name, tenant_id, status
        FROM core_datasource
        WHERE id IN (%s, %s)
        ORDER BY id
        """,
        (SOURCE_DATASOURCE_ID, TARGET_DATASOURCE_ID),
    )
    rows = {int(row["id"]): row for row in cur.fetchall()}
    source = rows.get(SOURCE_DATASOURCE_ID)
    target = rows.get(TARGET_DATASOURCE_ID)
    if source is None or source["name"] != "修仙" or int(source["tenant_id"]) != SOURCE_TENANT_ID:
        raise RuntimeError("canonical Xiuxian datasource identity changed")
    if target is None or target["name"] != TARGET_NAME or int(target["tenant_id"]) != TARGET_TENANT_ID:
        raise RuntimeError(f"{TARGET_NAME} datasource identity changed")
    if str(source["status"]).lower() != "success" or str(target["status"]).lower() != "success":
        raise RuntimeError("source or target datasource is not healthy")

    cur.execute(
        "SELECT datasource_id FROM core_datasource_tenant_binding WHERE tenant_id = %s",
        (TARGET_TENANT_ID,),
    )
    bindings = cur.fetchall()
    if len(bindings) != 1 or int(bindings[0]["datasource_id"]) != TARGET_DATASOURCE_ID:
        raise RuntimeError(f"{TARGET_NAME} workspace binding changed")

    source_schema = _physical_schema(cur, SOURCE_DATASOURCE_ID)
    target_schema = _physical_schema(cur, TARGET_DATASOURCE_ID)
    if not source_schema or source_schema != target_schema:
        raise RuntimeError(f"Xiuxian and {TARGET_NAME} physical schemas no longer match")


def _load_dictionary(cur: Any, tenant_id: int, datasource_id: int) -> dict[str, Any]:
    cur.execute(
        "SELECT * FROM sys_tenant_tracking_config WHERE tenant_id = %s AND datasource_id = %s",
        (tenant_id, datasource_id),
    )
    config = cur.fetchone()
    if config is None:
        raise RuntimeError(f"tracking config missing: tenant={tenant_id}, datasource={datasource_id}")
    cur.execute(
        """
        SELECT * FROM sys_tenant_tracking_table
        WHERE tenant_id = %s AND datasource_id = %s
        ORDER BY table_name
        """,
        (tenant_id, datasource_id),
    )
    tables = list(cur.fetchall())
    cur.execute(
        """
        SELECT * FROM sys_tenant_tracking_field
        WHERE tenant_id = %s AND datasource_id = %s
        ORDER BY table_name, field_name
        """,
        (tenant_id, datasource_id),
    )
    fields = list(cur.fetchall())
    return {"config": dict(config), "tables": [dict(row) for row in tables], "fields": [dict(row) for row in fields]}


def _desired_dictionary(source: dict[str, Any]) -> dict[str, Any]:
    desired = _transform(source)
    desired["config"]["notes"] = (
        f"{TARGET_NAME} 工作空间数据字典，datasource_id={TARGET_DATASOURCE_ID}。"
        "event_realtime 是当天实时事件表，"
        "与 event 共享 uid、event、time、dt、prod 等基础字段语义；"
        f"{TARGET_NAME} 查询固定过滤 prod={TARGET_PRODUCT_ID}。"
    )
    serialized = json.dumps(desired, ensure_ascii=False, default=str)
    other_target_ids = {
        int(profile["datasource_id"])
        for name, profile in TARGET_PROFILES.items()
        if name != TARGET_NAME
    }
    forbidden = (
        "flam",
        "first_zombie",
        "datasource_id=3",
        f"datasource_id={SOURCE_DATASOURCE_ID}",
        "110000047",
        *(f"datasource_id={datasource_id}" for datasource_id in sorted(other_target_ids)),
    )
    found = [token for token in forbidden if token in serialized]
    if found:
        raise RuntimeError(
            f"transformed {TARGET_NAME} dictionary still contains foreign boundaries: {found}"
        )
    return desired


def _normalized(row: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    return {column: row.get(column) for column in columns}


def _plan(current: dict[str, Any], desired: dict[str, Any]) -> dict[str, Any]:
    current_tables = {row["table_name"]: row for row in current["tables"]}
    desired_tables = {row["table_name"]: row for row in desired["tables"]}
    current_fields = {(row["table_name"], row["field_name"]): row for row in current["fields"]}
    desired_fields = {(row["table_name"], row["field_name"]): row for row in desired["fields"]}
    return {
        "config_changed": _normalized(current["config"], CONFIG_COLUMNS)
        != _normalized(desired["config"], CONFIG_COLUMNS),
        "tables_upserted": sum(
            _normalized(current_tables.get(key, {}), TABLE_COLUMNS)
            != _normalized(row, TABLE_COLUMNS)
            for key, row in desired_tables.items()
        ),
        "tables_deleted": len(set(current_tables) - set(desired_tables)),
        "fields_upserted": sum(
            _normalized(current_fields.get(key, {}), FIELD_COLUMNS)
            != _normalized(row, FIELD_COLUMNS)
            for key, row in desired_fields.items()
        ),
        "fields_deleted": len(set(current_fields) - set(desired_fields)),
        "desired_event_count": len(desired["config"].get("event_name_mappings") or []),
        "desired_table_count": len(desired_tables),
        "desired_field_count": len(desired_fields),
    }


def _json_param(column: str, value: Any) -> Any:
    return Jsonb(value) if column in JSON_COLUMNS and value is not None else value


def _apply_config(cur: Any, desired: dict[str, Any], now: int) -> None:
    assignments = ", ".join(f"{column} = %s" for column in CONFIG_COLUMNS)
    values = [_json_param(column, desired["config"].get(column)) for column in CONFIG_COLUMNS]
    cur.execute(
        f"""
        UPDATE sys_tenant_tracking_config
        SET {assignments}, update_by = %s, update_time = %s
        WHERE tenant_id = %s AND datasource_id = %s
        """,
        (*values, 1, now, TARGET_TENANT_ID, TARGET_DATASOURCE_ID),
    )
    if cur.rowcount != 1:
        raise RuntimeError(
            f"{TARGET_NAME} tracking config update did not affect exactly one row"
        )


def _apply_tables(cur: Any, desired: dict[str, Any], now: int) -> None:
    names = [row["table_name"] for row in desired["tables"]]
    cur.execute(
        """
        DELETE FROM sys_tenant_tracking_table
        WHERE tenant_id = %s AND datasource_id = %s AND NOT (table_name = ANY(%s))
        """,
        (TARGET_TENANT_ID, TARGET_DATASOURCE_ID, names),
    )
    update_sql = ", ".join(f"{column} = EXCLUDED.{column}" for column in TABLE_COLUMNS)
    columns_sql = ", ".join(TABLE_COLUMNS)
    placeholders = ", ".join(["%s"] * len(TABLE_COLUMNS))
    for row in desired["tables"]:
        values = [_json_param(column, row.get(column)) for column in TABLE_COLUMNS]
        cur.execute(
            f"""
            INSERT INTO sys_tenant_tracking_table
              (id, tenant_id, datasource_id, table_name, {columns_sql}, create_by, update_by, create_time, update_time)
            VALUES (%s, %s, %s, %s, {placeholders}, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, datasource_id, table_name) DO UPDATE SET
              {update_sql}, update_by = EXCLUDED.update_by, update_time = EXCLUDED.update_time
            """,
            (
                int(snowflake.generate_id()),
                TARGET_TENANT_ID,
                TARGET_DATASOURCE_ID,
                row["table_name"],
                *values,
                1,
                1,
                now,
                now,
            ),
        )


def _apply_fields(cur: Any, desired: dict[str, Any], now: int) -> None:
    keys = [(row["table_name"], row["field_name"]) for row in desired["fields"]]
    cur.execute(
        """
        SELECT table_name, field_name
        FROM sys_tenant_tracking_field
        WHERE tenant_id = %s AND datasource_id = %s
        """,
        (TARGET_TENANT_ID, TARGET_DATASOURCE_ID),
    )
    stale = [(row["table_name"], row["field_name"]) for row in cur.fetchall() if (row["table_name"], row["field_name"]) not in keys]
    for table_name, field_name in stale:
        cur.execute(
            """
            DELETE FROM sys_tenant_tracking_field
            WHERE tenant_id = %s AND datasource_id = %s AND table_name = %s AND field_name = %s
            """,
            (TARGET_TENANT_ID, TARGET_DATASOURCE_ID, table_name, field_name),
        )

    update_sql = ", ".join(f"{column} = EXCLUDED.{column}" for column in FIELD_COLUMNS)
    columns_sql = ", ".join(FIELD_COLUMNS)
    placeholders = ", ".join(["%s"] * len(FIELD_COLUMNS))
    for row in desired["fields"]:
        values = [_json_param(column, row.get(column)) for column in FIELD_COLUMNS]
        cur.execute(
            f"""
            INSERT INTO sys_tenant_tracking_field
              (id, tenant_id, datasource_id, table_name, field_name, {columns_sql},
               create_by, update_by, create_time, update_time)
            VALUES (%s, %s, %s, %s, %s, {placeholders}, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, datasource_id, table_name, field_name) DO UPDATE SET
              {update_sql}, update_by = EXCLUDED.update_by, update_time = EXCLUDED.update_time
            """,
            (
                int(snowflake.generate_id()),
                TARGET_TENANT_ID,
                TARGET_DATASOURCE_ID,
                row["table_name"],
                row["field_name"],
                *values,
                1,
                1,
                now,
                now,
            ),
        )


def _write_backup(current: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"{TARGET_NAME}_tracking_dictionary_{time.time_ns()}.json"
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def run(*, apply: bool) -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if apply:
                cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (f"repair-{TARGET_NAME}-tracking-dictionary-v1",),
                )
            _require_identity(cur)
            source = _load_dictionary(cur, SOURCE_TENANT_ID, SOURCE_DATASOURCE_ID)
            current = _load_dictionary(cur, TARGET_TENANT_ID, TARGET_DATASOURCE_ID)
            desired = _desired_dictionary(source)
            plan = _plan(current, desired)
            result: dict[str, Any] = {
                "workspace": TARGET_NAME,
                "tenant_id": str(TARGET_TENANT_ID),
                "datasource_id": TARGET_DATASOURCE_ID,
                "product_id": TARGET_PRODUCT_ID,
                "apply": apply,
                **plan,
            }
            if not apply:
                conn.rollback()
                return result

            backup = _write_backup(current)
            now = int(time.time())
            _apply_config(cur, desired, now)
            _apply_tables(cur, desired, now)
            _apply_fields(cur, desired, now)
            updated = _load_dictionary(cur, TARGET_TENANT_ID, TARGET_DATASOURCE_ID)
            remaining = _plan(updated, desired)
            if any(
                remaining[key]
                for key in ("config_changed", "tables_upserted", "tables_deleted", "fields_upserted", "fields_deleted")
            ):
                raise RuntimeError(f"post-update verification failed: {remaining}")
            conn.commit()
            result["backup"] = str(backup)
            result["verified"] = True
            return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        choices=tuple(TARGET_PROFILES),
        default="lds",
        help="target workspace (default: lds)",
    )
    parser.add_argument("--apply", action="store_true", help="write the verified repair")
    args = parser.parse_args()
    configure_target(args.workspace)
    print(json.dumps(run(apply=args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
