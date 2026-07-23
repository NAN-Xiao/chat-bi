# -*- coding: utf-8 -*-
"""定向补齐修仙工作空间 event_realtime 字典元数据。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
TENANT_ID = 7482727237662281728
DATASOURCE_ID = 6
UPDATE_BY = 1
LOCK_KEY = TENANT_ID ^ DATASOURCE_ID
DEFAULT_BACKUP_ROOT = (
    ROOT / ".codex-runtime" / "xiuxian-realtime-tracking-backups"
)

REALTIME_SQL_RULE = (
    "今天、当天、今日、截至目前、当前或实时的事件查询必须使用 event_realtime，"
    "并直接限制当前业务日 dt 分区；完整历史日和成熟 cohort 使用 event，"
    "不得在实时表缺失或无权限时静默回退到历史表。"
)
REALTIME_NOTE = (
    "event_realtime 是 datasource_id=6 的当天实时事件表，与 event 共享 uid、event、"
    "time、dt、prod 等基础字段语义。"
)

REALTIME_TABLE = {
    "table_name": "event_realtime",
    "table_comment": "当天实时事件明细表。每行是一条尚未归档到完整历史分区的用户行为或系统事件。",
    "table_role": "realtime_event_fact",
    "aliases": ["实时事件表", "当天埋点表", "实时行为明细"],
    "ai_notes": "仅用于今天、当天、截至目前和实时分钟/小时查询；完整历史日继续使用 event。",
}

ROLE_MAPPINGS = [
    {"role": "subject_id", "table": "event", "field": "uid", "description": "事件主体用户 ID"},
    {"role": "event_name", "table": "event", "field": "event", "description": "业务事件名"},
    {"role": "event_time", "table": "event", "field": "time", "description": "毫秒时间戳"},
    {"role": "partition_date", "table": "event", "field": "dt", "description": "业务日期分区 yyyyMMdd"},
    {"role": "subject_id", "table": "event_realtime", "field": "uid", "description": "实时事件主体用户 ID"},
    {"role": "event_name", "table": "event_realtime", "field": "event", "description": "实时业务事件名"},
    {"role": "event_time", "table": "event_realtime", "field": "time", "description": "实时事件毫秒时间戳"},
    {"role": "partition_date", "table": "event_realtime", "field": "dt", "description": "实时业务日期分区 yyyyMMdd"},
]

FIELD_OVERRIDES = {
    "uid": {
        "field_comment": "实时事件主体用户 ID；人数指标按 uid 去重。",
        "field_role": "subject_id",
        "semantic_type": "identifier",
        "aliases": ["UID", "用户ID", "玩家ID"],
        "required": True,
    },
    "event": {
        "field_comment": "实时业务事件名；新增用户使用 UserRegister，查询前必须过滤事件名。",
        "field_role": "event_name",
        "semantic_type": "category",
        "aliases": ["事件名", "埋点名", "行为类型"],
        "required": True,
    },
    "time": {
        "field_comment": "实时事件发生时间，13 位 Unix 毫秒时间戳；按小时统计使用 FROM_UNIXTIME(time / 1000)。",
        "field_role": "event_time",
        "semantic_type": "timestamp_ms",
        "aliases": ["事件时间", "毫秒时间戳"],
        "required": True,
    },
    "dt": {
        "field_comment": "实时业务日期分区，8 位 YYYYMMDD 整数；当天查询直接限制当前业务日。",
        "field_role": "partition_date",
        "semantic_type": "date",
        "aliases": ["事件日期", "分区日期", "业务日期"],
        "required": True,
    },
    "prod": {
        "field_comment": "产品 ID；修仙工作空间查询固定过滤 prod=110000047。",
        "field_role": "product_id",
        "semantic_type": "identifier",
        "aliases": ["产品ID", "项目ID"],
        "required": True,
    },
    "personal": {
        "field_comment": "实时事件业务属性 JSON；具体指标只能使用工作空间已配置的 JSONPath。",
        "field_role": "dimension_json",
        "semantic_type": "json",
        "aliases": ["业务属性", "事件属性"],
        "required": False,
    },
}

FIELD_KEYS = (
    "field_name",
    "field_comment",
    "field_role",
    "semantic_type",
    "aliases",
    "value_mappings",
    "expression",
    "required",
    "example_values",
    "ai_notes",
)


class SourceChangedError(RuntimeError):
    """发布锁内发现修仙字典来源发生变化。"""


def _snowflake_id() -> int:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from common.utils.snowflake import snowflake

    return int(snowflake.generate_id())


def _append_once(current: str | None, addition: str) -> str:
    value = str(current or "").strip()
    if addition in value:
        return value
    return "\n".join(part for part in (value, addition) if part)


def _merge_aliases(current: Any, required: list[str]) -> list[str]:
    return list(dict.fromkeys([*(current or []), *required]))


def _semantic_type(field_type: str | None) -> str:
    value = str(field_type or "").lower()
    if any(token in value for token in ("int", "decimal", "numeric", "float", "double")):
        return "number"
    return "text"


def _build_realtime_fields(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    historical = {
        item["field_name"]: item
        for item in snapshot.get("historical_fields") or []
        if item.get("field_name")
    }
    fields: list[dict[str, Any]] = []
    for physical in snapshot.get("physical_fields") or []:
        field_name = str(physical.get("field_name") or "").strip()
        if not field_name:
            continue
        source = historical.get(field_name) or {}
        item = {
            key: deepcopy(source.get(key))
            for key in FIELD_KEYS
            if key != "field_name"
        }
        item["field_name"] = field_name
        item["field_comment"] = item.get("field_comment") or f"event_realtime 物理字段 {field_name}。"
        item["semantic_type"] = item.get("semantic_type") or _semantic_type(
            physical.get("field_type")
        )
        item["aliases"] = list(item.get("aliases") or [])
        item["required"] = bool(item.get("required", False))
        item["example_values"] = list(item.get("example_values") or [])
        override = FIELD_OVERRIDES.get(field_name)
        if override:
            aliases = _merge_aliases(item.get("aliases"), override.get("aliases") or [])
            item.update(deepcopy(override))
            item["aliases"] = aliases
        fields.append(item)

    required = set(FIELD_OVERRIDES)
    available = {item["field_name"] for item in fields}
    missing = sorted(required - available)
    if missing:
        raise ValueError(f"event_realtime 缺少修复所需物理字段: {missing}")
    return fields


def _merge_role_mappings(current: Any) -> list[dict[str, Any]]:
    managed_roles = {"subject_id", "event_name", "event_time", "partition_date"}
    preserved = [
        deepcopy(item)
        for item in (current or [])
        if not (
            isinstance(item, dict)
            and item.get("table") in {"event", "event_realtime"}
            and item.get("role") in managed_roles
        )
    ]
    return [*preserved, *deepcopy(ROLE_MAPPINGS)]


def build_desired_dictionary(snapshot: dict[str, Any]) -> dict[str, Any]:
    config = snapshot.get("config") or {}
    return {
        "table": deepcopy(REALTIME_TABLE),
        "fields": _build_realtime_fields(snapshot),
        "field_role_mappings": _merge_role_mappings(config.get("field_role_mappings")),
        "sql_rules": _append_once(config.get("sql_rules"), REALTIME_SQL_RULE),
        "notes": _append_once(config.get("notes"), REALTIME_NOTE),
    }


def _snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sync_realtime_dictionary(backend: Any, *, apply: bool) -> dict[str, Any]:
    before = backend.load_snapshot()
    desired = build_desired_dictionary(before)
    backup_path = backend.write_backup(before)
    if not apply:
        return {
            "mode": "dry-run",
            "updated": False,
            "backup_path": str(backup_path),
            "field_count": len(desired["fields"]),
        }

    backend.acquire_lock()
    try:
        locked = backend.load_snapshot()
        if _snapshot_fingerprint(locked) != _snapshot_fingerprint(before):
            raise SourceChangedError("修仙实时字典来源在加锁前后发生变化，拒绝写入")
        backend.apply_desired(desired)
        backend.verify_desired(desired)
        backend.commit()
    except BaseException:
        backend.rollback()
        raise
    finally:
        backend.release_lock()
    return {
        "mode": "apply",
        "updated": True,
        "backup_path": str(backup_path),
        "field_count": len(desired["fields"]),
    }


class PsycopgBackend:
    def __init__(self, *, backup_root: Path = DEFAULT_BACKUP_ROOT):
        self.backup_root = Path(backup_root)
        self._write_connection: Any | None = None

    @staticmethod
    def _connection() -> Any:
        return psycopg.connect(**core_system_db_config())

    def _active_or_new_connection(self) -> tuple[Any, bool]:
        if self._write_connection is not None:
            return self._write_connection, False
        return self._connection(), True

    def load_snapshot(self) -> dict[str, Any]:
        connection, should_close = self._active_or_new_connection()
        try:
            with connection.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(
                    """
                    SELECT field_role_mappings, sql_rules, notes
                    FROM public.sys_tenant_tracking_config
                    WHERE tenant_id = %s AND datasource_id = %s
                    """,
                    (TENANT_ID, DATASOURCE_ID),
                )
                config_rows = cur.fetchall()
                if len(config_rows) != 1:
                    raise RuntimeError(f"修仙 tracking config 必须唯一，实际 {len(config_rows)}")
                cur.execute(
                    """
                    SELECT field_name, field_comment, field_role, semantic_type, aliases,
                           value_mappings, expression, required, example_values, ai_notes
                    FROM public.sys_tenant_tracking_field
                    WHERE tenant_id = %s AND datasource_id = %s
                      AND table_name = 'event' AND field_name NOT LIKE '%%.%%'
                    ORDER BY field_name
                    """,
                    (TENANT_ID, DATASOURCE_ID),
                )
                historical_fields = cur.fetchall()
                cur.execute(
                    """
                    SELECT f.field_name, f.field_type
                    FROM public.core_field AS f
                    JOIN public.core_table AS t ON t.id = f.table_id AND t.ds_id = f.ds_id
                    WHERE t.ds_id = %s AND t.table_name = 'event_realtime'
                      AND COALESCE(t.checked, false) = true
                      AND COALESCE(f.checked, false) = true
                    ORDER BY f.field_index, f.id
                    """,
                    (DATASOURCE_ID,),
                )
                physical_fields = cur.fetchall()
                cur.execute(
                    """
                    SELECT table_name, table_comment, table_role, aliases, ai_notes
                    FROM public.sys_tenant_tracking_table
                    WHERE tenant_id = %s AND datasource_id = %s
                      AND table_name = 'event_realtime'
                    """,
                    (TENANT_ID, DATASOURCE_ID),
                )
                target_table = cur.fetchone()
                cur.execute(
                    """
                    SELECT field_name, field_comment, field_role, semantic_type, aliases,
                           value_mappings, expression, required, example_values, ai_notes
                    FROM public.sys_tenant_tracking_field
                    WHERE tenant_id = %s AND datasource_id = %s
                      AND table_name = 'event_realtime'
                    ORDER BY field_name
                    """,
                    (TENANT_ID, DATASOURCE_ID),
                )
                target_fields = cur.fetchall()
            return {
                "config": config_rows[0],
                "historical_fields": historical_fields,
                "physical_fields": physical_fields,
                "target_table": target_table,
                "target_fields": target_fields,
            }
        finally:
            if should_close:
                connection.close()

    def write_backup(self, snapshot: dict[str, Any]) -> Path:
        self.backup_root.mkdir(parents=True, exist_ok=True)
        path = self.backup_root / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
        path.write_text(
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2, default=str),
            encoding="utf-8",
        )
        return path

    def acquire_lock(self) -> None:
        if self._write_connection is not None:
            raise RuntimeError("修仙实时字典发布锁连接已存在")
        self._write_connection = self._connection()
        with self._write_connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))

    def _require_connection(self) -> Any:
        if self._write_connection is None:
            raise RuntimeError("写入修仙实时字典前必须持有发布锁")
        return self._write_connection

    def apply_desired(self, desired: dict[str, Any]) -> None:
        connection = self._require_connection()
        now = int(time.time())
        with connection.cursor() as cur:
            cur.execute(
                """
                UPDATE public.sys_tenant_tracking_config
                SET field_role_mappings = %s, sql_rules = %s, notes = %s,
                    update_by = %s, update_time = %s
                WHERE tenant_id = %s AND datasource_id = %s
                """,
                (
                    Jsonb(desired["field_role_mappings"]),
                    desired["sql_rules"],
                    desired["notes"],
                    UPDATE_BY,
                    now,
                    TENANT_ID,
                    DATASOURCE_ID,
                ),
            )
            if cur.rowcount != 1:
                raise RuntimeError("修仙 tracking config 定向更新失败")
            table = desired["table"]
            cur.execute(
                """
                INSERT INTO public.sys_tenant_tracking_table (
                    id, tenant_id, datasource_id, table_name, table_comment, table_role,
                    aliases, ai_notes, create_by, update_by, create_time, update_time
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, datasource_id, table_name) DO UPDATE SET
                    table_comment = EXCLUDED.table_comment,
                    table_role = EXCLUDED.table_role,
                    aliases = EXCLUDED.aliases,
                    ai_notes = EXCLUDED.ai_notes,
                    update_by = EXCLUDED.update_by,
                    update_time = EXCLUDED.update_time
                """,
                (
                    _snowflake_id(), TENANT_ID, DATASOURCE_ID, table["table_name"],
                    table["table_comment"], table["table_role"], Jsonb(table["aliases"]),
                    table["ai_notes"], UPDATE_BY, UPDATE_BY, now, now,
                ),
            )
            for item in desired["fields"]:
                cur.execute(
                    """
                    INSERT INTO public.sys_tenant_tracking_field (
                        id, tenant_id, datasource_id, table_name, field_name, field_comment,
                        field_role, semantic_type, aliases, value_mappings, expression, required,
                        example_values, ai_notes, create_by, update_by, create_time, update_time
                    ) VALUES (%s, %s, %s, 'event_realtime', %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, datasource_id, table_name, field_name) DO UPDATE SET
                        field_comment = EXCLUDED.field_comment,
                        field_role = EXCLUDED.field_role,
                        semantic_type = EXCLUDED.semantic_type,
                        aliases = EXCLUDED.aliases,
                        value_mappings = EXCLUDED.value_mappings,
                        expression = EXCLUDED.expression,
                        required = EXCLUDED.required,
                        example_values = EXCLUDED.example_values,
                        ai_notes = EXCLUDED.ai_notes,
                        update_by = EXCLUDED.update_by,
                        update_time = EXCLUDED.update_time
                    """,
                    (
                        _snowflake_id(), TENANT_ID, DATASOURCE_ID, item["field_name"],
                        item.get("field_comment"), item.get("field_role"),
                        item.get("semantic_type"), Jsonb(item.get("aliases") or []),
                        Jsonb(item.get("value_mappings")) if item.get("value_mappings") is not None else None,
                        item.get("expression"), bool(item.get("required", False)),
                        Jsonb(item.get("example_values") or []), item.get("ai_notes"),
                        UPDATE_BY, UPDATE_BY, now, now,
                    ),
                )

    def verify_desired(self, desired: dict[str, Any]) -> None:
        connection = self._require_connection()
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                """
                SELECT field_role_mappings, sql_rules, notes
                FROM public.sys_tenant_tracking_config
                WHERE tenant_id = %s AND datasource_id = %s
                """,
                (TENANT_ID, DATASOURCE_ID),
            )
            config = cur.fetchone()
            if not config or config["field_role_mappings"] != desired["field_role_mappings"]:
                raise RuntimeError("修仙实时字典字段角色回读不一致")
            if config["sql_rules"] != desired["sql_rules"] or config["notes"] != desired["notes"]:
                raise RuntimeError("修仙实时字典规则或说明回读不一致")
            cur.execute(
                """
                SELECT table_name, table_comment, table_role, aliases, ai_notes
                FROM public.sys_tenant_tracking_table
                WHERE tenant_id = %s AND datasource_id = %s
                  AND table_name = 'event_realtime'
                """,
                (TENANT_ID, DATASOURCE_ID),
            )
            if cur.fetchone() != desired["table"]:
                raise RuntimeError("修仙 event_realtime 表字典回读不一致")
            cur.execute(
                """
                SELECT field_name, field_comment, field_role, semantic_type, aliases,
                       value_mappings, expression, required, example_values, ai_notes
                FROM public.sys_tenant_tracking_field
                WHERE tenant_id = %s AND datasource_id = %s
                  AND table_name = 'event_realtime'
                ORDER BY field_name
                """,
                (TENANT_ID, DATASOURCE_ID),
            )
            actual = {item["field_name"]: item for item in cur.fetchall()}
        expected = {item["field_name"]: item for item in desired["fields"]}
        if any(actual.get(name) != item for name, item in expected.items()):
            raise RuntimeError("修仙 event_realtime 字段字典回读不一致")

    def commit(self) -> None:
        self._require_connection().commit()

    def rollback(self) -> None:
        if self._write_connection is not None:
            self._write_connection.rollback()

    def release_lock(self) -> None:
        if self._write_connection is None:
            return
        connection = self._write_connection
        self._write_connection = None
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
        finally:
            connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--mode", choices=("dry-run", "apply"), default="dry-run")
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = sync_realtime_dictionary(
        PsycopgBackend(backup_root=args.backup_root),
        apply=args.mode == "apply",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
