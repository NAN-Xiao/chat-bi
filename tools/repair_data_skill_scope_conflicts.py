"""安全治理平台 Data Skill 171/234 与用户私有 Skill 280。"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import psycopg
from core_system_db import core_system_db_config, export_postgres_compat_env
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
BACKUP_ROOT = ROOT / ".codex-runtime" / "data-skill-scope-conflict-backups"
TARGET_IDS = (171, 234, 280)
EMBEDDING_IDS = (171, 280)
LOCK_NAME = "repair-data-skill-scope-conflicts-v1"

EXPECTED_PROMPT_SHA256 = {
    171: "96f7fb760fb14b62cd84df9ba3a4e21da615ead3c12cc7324bceb2a5a8145c2c",
    234: "a7330d9e46175e1a991d058492a0b2d72323ef0e780a62d3e66a1320257c09ec",
    280: "3073d524631de743c6b87019cf28fd717ef4ea7314b86ff5284be082b7bd9514",
}
BOUNDED_SCAN_MARKER = "<!-- data-skill-managed-section:bounded-fact-scan:v1 -->"
BOUNDED_SCAN_SECTION = f"""{BOUNDED_SCAN_MARKER}
## 高成本事实明细的有界扫描

- 本规则仅适用于可能产生高成本扫描的事实明细表；维表、小表和合理的无时间字段分析不得被错误阻断。
- 生成 SQL 前必须先依据当前工作空间 Schema 与元数据确认真实的业务时间字段或分区字段，不得猜测字段名。
- 对高成本事实明细，应优先使用用户指定的时间范围；用户未指定时，只能使用平台允许的有界时间或分区条件，再查询对应数据。
- 当前数据源权限、实时 Schema、空间级 Data Skill 和用户明确条件优先；若不存在可确认的时间字段，应说明缺少的元数据，而不是静默替换为相似字段。
""".strip()

EXPECTED_IDENTITIES: dict[int, dict[str, Any]] = {
    171: {
        "name": "平台通用 Data Skill：时间字段、观察窗口与日期边界",
        "type": "DATA_SKILL",
        "tenant_id": 1,
        "create_by": None,
        "visibility_scope": "PLATFORM_PUBLIC",
        "target_scope": "ALL",
        "ai_model_id": None,
    },
    234: {
        "name": "平台通用 Data Skill：取数据的约束",
        "type": "DATA_SKILL",
        "tenant_id": 1,
        "create_by": 1,
        "visibility_scope": "PLATFORM_PUBLIC",
        "target_scope": "ALL",
        "ai_model_id": None,
    },
    280: {
        "name": "示例：修仙 资源获取与消耗统计口径",
        "type": "DATA_SKILL",
        "tenant_id": 7482727237662281728,
        "create_by": 7482253745313550336,
        "visibility_scope": "USER_PRIVATE",
        "target_scope": "ALL",
        "ai_model_id": None,
    },
}

ROW_COLUMNS = (
    "id",
    "type",
    "create_time",
    "name",
    "prompt",
    "specific_ds",
    "datasource_ids",
    "description",
    "ai_model_id",
    "create_by",
    "target_scope",
    "active",
    "visibility_scope",
    "tenant_id",
    "visible",
    "embedding",
    "embedding_signature",
)
MUTABLE_COLUMNS = tuple(column for column in ROW_COLUMNS if column not in {"id", "create_time"})


@dataclass(frozen=True)
class RepairReport:
    mode: str
    target_ids: tuple[int, ...]
    updated_ids: tuple[int, ...]
    updated: bool
    embedding_verified: bool
    backup_path: str | None = None


class RepairBackend(Protocol):
    def acquire_lock(self) -> None: ...

    def release_lock(self) -> None: ...

    def inspect(self, *, for_update: bool = False) -> dict[int, dict[str, Any]]: ...

    def backup(self, rows: Mapping[int, Mapping[str, Any]]) -> Any: ...

    def apply_updates(
        self,
        originals: Mapping[int, Mapping[str, Any]],
        desired: Mapping[int, Mapping[str, Any]],
    ) -> tuple[int, ...]: ...

    def refresh_embeddings(self, skill_ids: Sequence[int]) -> None: ...

    def verify(self, desired: Mapping[int, Mapping[str, Any]]) -> None: ...

    def restore(
        self,
        backup: Any,
        expected: Mapping[int, Mapping[str, Any]],
    ) -> None: ...


def _prompt_sha256(prompt: Any) -> str:
    return hashlib.sha256(str(prompt or "").strip().encode("utf-8")).hexdigest()


def _normalized_datasource_ids(value: Any) -> list[int]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list):
        raise RuntimeError("Data Skill datasource_ids 前置状态无效")
    return [int(item) for item in value]


def _base_171_prompt(prompt: str) -> str:
    count = prompt.count(BOUNDED_SCAN_MARKER)
    if count > 1:
        raise RuntimeError("Skill 171 前置状态存在重复受管段落")
    if count == 0:
        return prompt.strip()
    prefix, marker_and_suffix = prompt.split(BOUNDED_SCAN_MARKER, 1)
    actual_section = (BOUNDED_SCAN_MARKER + marker_and_suffix).strip()
    if actual_section != BOUNDED_SCAN_SECTION:
        raise RuntimeError("Skill 171 前置状态的受管段落已漂移")
    return prefix.strip()


def validate_targets(rows: Mapping[int, Mapping[str, Any]]) -> None:
    if set(rows) != set(TARGET_IDS):
        raise RuntimeError(
            f"Data Skill 前置状态 ID 不完整：期望 {TARGET_IDS}，实际 {tuple(sorted(rows))}"
        )

    for skill_id in TARGET_IDS:
        row = rows[skill_id]
        if int(row.get("id", -1)) != skill_id:
            raise RuntimeError(f"Skill {skill_id} 前置状态 ID 漂移")
        for field, expected in EXPECTED_IDENTITIES[skill_id].items():
            if row.get(field) != expected:
                raise RuntimeError(f"Skill {skill_id} 前置状态字段 {field} 漂移")

        prompt = str(row.get("prompt") or "")
        hash_source = _base_171_prompt(prompt) if skill_id == 171 else prompt
        if _prompt_sha256(hash_source) != EXPECTED_PROMPT_SHA256[skill_id]:
            raise RuntimeError(f"Skill {skill_id} 前置状态 prompt SHA256 漂移")

    row_171 = rows[171]
    if (
        bool(row_171.get("specific_ds"))
        or _normalized_datasource_ids(row_171.get("datasource_ids"))
        or not bool(row_171.get("active"))
        or not bool(row_171.get("visible"))
    ):
        raise RuntimeError("Skill 171 前置状态作用域漂移")

    row_234 = rows[234]
    if bool(row_234.get("specific_ds")) or _normalized_datasource_ids(
        row_234.get("datasource_ids")
    ):
        raise RuntimeError("Skill 234 前置状态作用域漂移")
    if (bool(row_234.get("active")), bool(row_234.get("visible"))) not in {
        (True, True),
        (False, False),
    }:
        raise RuntimeError("Skill 234 前置状态启停字段漂移")

    row_280 = rows[280]
    scope_280 = (
        bool(row_280.get("specific_ds")),
        tuple(_normalized_datasource_ids(row_280.get("datasource_ids"))),
    )
    if scope_280 not in {(False, ()), (True, (6,))}:
        raise RuntimeError("Skill 280 前置状态数据源作用域漂移")
    if not bool(row_280.get("active")) or not bool(row_280.get("visible")):
        raise RuntimeError("Skill 280 前置状态启停字段漂移")


def build_desired_rows(
    rows: Mapping[int, Mapping[str, Any]],
) -> dict[int, dict[str, Any]]:
    desired = {skill_id: copy.deepcopy(dict(rows[skill_id])) for skill_id in TARGET_IDS}

    prompt_171 = str(desired[171].get("prompt") or "")
    if BOUNDED_SCAN_MARKER not in prompt_171:
        desired[171]["prompt"] = f"{prompt_171.strip()}\n\n{BOUNDED_SCAN_SECTION}\n"
        desired[171]["embedding"] = None
        desired[171]["embedding_signature"] = None

    desired[234]["active"] = False
    desired[234]["visible"] = False
    desired[234]["embedding"] = None
    desired[234]["embedding_signature"] = None

    scope_changed = not bool(desired[280].get("specific_ds")) or _normalized_datasource_ids(
        desired[280].get("datasource_ids")
    ) != [6]
    desired[280]["specific_ds"] = True
    desired[280]["datasource_ids"] = [6]
    if scope_changed:
        desired[280]["embedding"] = None
        desired[280]["embedding_signature"] = None
    return desired


def repair_skills(backend: RepairBackend, *, apply: bool) -> RepairReport:
    if not apply:
        rows = backend.inspect(for_update=False)
        validate_targets(rows)
        return RepairReport(
            mode="dry-run",
            target_ids=TARGET_IDS,
            updated_ids=(),
            updated=False,
            embedding_verified=False,
        )

    backup: Any = None
    desired: dict[int, dict[str, Any]] | None = None
    applied = False
    primary_error: BaseException | None = None
    backend.acquire_lock()
    try:
        rows = backend.inspect(for_update=True)
        validate_targets(rows)
        desired = build_desired_rows(rows)
        changed_ids = tuple(
            skill_id for skill_id in TARGET_IDS if desired[skill_id] != rows[skill_id]
        )
        if not changed_ids:
            backend.verify(desired)
            return RepairReport(
                mode="apply",
                target_ids=TARGET_IDS,
                updated_ids=(),
                updated=False,
                embedding_verified=True,
            )

        backup = backend.backup(rows)
        updated_ids = backend.apply_updates(rows, desired)
        if tuple(updated_ids) != changed_ids:
            raise RuntimeError(
                f"Data Skill 更新 ID 不完整：期望 {changed_ids}，实际 {tuple(updated_ids)}"
            )
        applied = True
        backend.refresh_embeddings(EMBEDDING_IDS)
        backend.verify(desired)
        return RepairReport(
            mode="apply",
            target_ids=TARGET_IDS,
            updated_ids=tuple(updated_ids),
            updated=True,
            embedding_verified=True,
            backup_path=str(getattr(backup, "path", backup)),
        )
    except BaseException as exc:
        if applied and desired is not None:
            try:
                backend.restore(backup, desired)
            except BaseException as restore_error:
                exc.add_note(f"三条 Data Skill 恢复失败：{restore_error}")
        primary_error = exc
        raise
    finally:
        try:
            backend.release_lock()
        except BaseException as release_error:
            if primary_error is None:
                raise
            primary_error.add_note(f"治理锁释放失败：{release_error}")


@dataclass(frozen=True)
class BackupArtifact:
    path: Path
    rows: dict[int, dict[str, Any]]


def _json_default(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return str(value)


def _semantic_state(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in row.items()
        if key not in {"embedding", "embedding_signature"}
    }


class PsycopgRepairBackend:
    def __init__(self, *, backup_root: Path = BACKUP_ROOT) -> None:
        self.backup_root = Path(backup_root)
        self.connection: psycopg.Connection | None = None

    @staticmethod
    def _connect() -> psycopg.Connection:
        return psycopg.connect(**core_system_db_config(), row_factory=dict_row)

    def _require_connection(self) -> psycopg.Connection:
        if self.connection is None or self.connection.closed:
            raise RuntimeError("Data Skill 治理锁尚未获取")
        return self.connection

    def acquire_lock(self) -> None:
        if self.connection is not None:
            raise RuntimeError("Data Skill 治理锁已获取")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", (LOCK_NAME,))
            self.connection = connection
        except BaseException:
            connection.close()
            raise

    def release_lock(self) -> None:
        connection = self.connection
        self.connection = None
        if connection is None:
            return
        try:
            if not connection.closed and not connection.broken:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", (LOCK_NAME,))
        finally:
            connection.close()

    @staticmethod
    def _select_rows(
        connection: psycopg.Connection, *, for_update: bool
    ) -> dict[int, dict[str, Any]]:
        suffix = " FOR UPDATE" if for_update else ""
        columns = ", ".join(ROW_COLUMNS)
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {columns} FROM custom_prompt "
                f"WHERE id = ANY(%s) ORDER BY id{suffix}",
                (list(TARGET_IDS),),
            )
            rows = [dict(row) for row in cursor.fetchall()]
        return {int(row["id"]): row for row in rows}

    def inspect(self, *, for_update: bool = False) -> dict[int, dict[str, Any]]:
        if for_update:
            return self._select_rows(self._require_connection(), for_update=True)
        with self._connect() as connection:
            return self._select_rows(connection, for_update=False)

    def backup(self, rows: Mapping[int, Mapping[str, Any]]) -> BackupArtifact:
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.backup_root / timestamp / "skills.json"
        target.parent.mkdir(parents=True, exist_ok=False)
        copied_rows = {skill_id: copy.deepcopy(dict(row)) for skill_id, row in rows.items()}
        target.write_text(
            json.dumps(
                {"target_ids": TARGET_IDS, "created_at": timestamp, "rows": copied_rows},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=_json_default,
            ),
            encoding="utf-8",
        )
        if not target.exists() or target.stat().st_size == 0:
            raise RuntimeError("Data Skill 恢复备份写入失败")
        return BackupArtifact(path=target, rows=copied_rows)

    @staticmethod
    def _cas_where(row: Mapping[str, Any]) -> tuple[str, list[Any]]:
        clauses = ["id = %s"]
        params: list[Any] = [int(row["id"])]
        for column in MUTABLE_COLUMNS:
            if column == "datasource_ids":
                clauses.append("datasource_ids IS NOT DISTINCT FROM %s::jsonb")
                params.append(Jsonb(_normalized_datasource_ids(row.get(column))))
            else:
                clauses.append(f"{column} IS NOT DISTINCT FROM %s")
                params.append(row.get(column))
        return " AND ".join(clauses), params

    def apply_updates(
        self,
        originals: Mapping[int, Mapping[str, Any]],
        desired: Mapping[int, Mapping[str, Any]],
    ) -> tuple[int, ...]:
        connection = self._require_connection()
        changed_ids = tuple(
            skill_id for skill_id in TARGET_IDS if desired[skill_id] != originals[skill_id]
        )
        try:
            with connection.cursor() as cursor:
                for skill_id in changed_ids:
                    before = originals[skill_id]
                    after = desired[skill_id]
                    where_sql, where_params = self._cas_where(before)
                    cursor.execute(
                        f"""
                        UPDATE custom_prompt
                        SET prompt = %s,
                            active = %s,
                            visible = %s,
                            specific_ds = %s,
                            datasource_ids = %s::jsonb,
                            embedding = %s,
                            embedding_signature = %s
                        WHERE {where_sql}
                        """,
                        [
                            after.get("prompt"),
                            after.get("active"),
                            after.get("visible"),
                            after.get("specific_ds"),
                            Jsonb(_normalized_datasource_ids(after.get("datasource_ids"))),
                            after.get("embedding"),
                            after.get("embedding_signature"),
                            *where_params,
                        ],
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError(f"Skill {skill_id} CAS 更新失败，前置状态已变化")
            connection.commit()
            return changed_ids
        except BaseException:
            connection.rollback()
            raise

    @staticmethod
    def _save_embeddings(skill_ids: Sequence[int]) -> int:
        export_postgres_compat_env(core_system_db_config())
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))
        from sqlalchemy.orm import scoped_session, sessionmaker

        from apps.chat.curd.custom_prompt_embedding import save_custom_prompt_skill_embedding
        from common.core.db import engine

        session_maker = scoped_session(sessionmaker(bind=engine))
        return save_custom_prompt_skill_embedding(
            session_maker,
            [int(skill_id) for skill_id in skill_ids],
        )

    def refresh_embeddings(self, skill_ids: Sequence[int]) -> None:
        saved = self._save_embeddings(skill_ids)
        if saved != len(skill_ids):
            raise RuntimeError(
                f"Data Skill embedding 刷新不完整：期望 {len(skill_ids)}，实际 {saved}"
            )

    def verify(self, desired: Mapping[int, Mapping[str, Any]]) -> None:
        current = self._select_rows(self._require_connection(), for_update=False)
        if set(current) != set(TARGET_IDS):
            raise RuntimeError("Data Skill 更新后回读 ID 不完整")
        for skill_id in TARGET_IDS:
            if _semantic_state(current[skill_id]) != _semantic_state(desired[skill_id]):
                raise RuntimeError(f"Skill {skill_id} 更新后语义状态不一致")
        for skill_id in EMBEDDING_IDS:
            if not current[skill_id].get("embedding") or not current[skill_id].get(
                "embedding_signature"
            ):
                raise RuntimeError(f"Skill {skill_id} embedding 回读失败")
        if current[234].get("embedding") is not None or current[234].get(
            "embedding_signature"
        ) is not None:
            raise RuntimeError("Skill 234 停用后 embedding 未清空")

    def restore(
        self,
        backup: BackupArtifact,
        expected: Mapping[int, Mapping[str, Any]],
    ) -> None:
        if backup is None or set(backup.rows) != set(TARGET_IDS):
            raise RuntimeError("三条 Data Skill 恢复备份不完整")
        connection = self._require_connection()
        try:
            connection.rollback()
            current = self._select_rows(connection, for_update=True)
            for skill_id in TARGET_IDS:
                if _semantic_state(current[skill_id]) != _semantic_state(expected[skill_id]):
                    raise RuntimeError(
                        f"Skill {skill_id} 发布后被再次修改，拒绝用备份覆盖"
                    )
            with connection.cursor() as cursor:
                for skill_id in TARGET_IDS:
                    current_row = current[skill_id]
                    original = backup.rows[skill_id]
                    where_sql, where_params = self._cas_where(current_row)
                    assignments = []
                    set_params: list[Any] = []
                    for column in MUTABLE_COLUMNS:
                        if column == "datasource_ids":
                            assignments.append("datasource_ids = %s::jsonb")
                            set_params.append(
                                Jsonb(_normalized_datasource_ids(original.get(column)))
                            )
                        else:
                            assignments.append(f"{column} = %s")
                            set_params.append(original.get(column))
                    cursor.execute(
                        f"UPDATE custom_prompt SET {', '.join(assignments)} WHERE {where_sql}",
                        [*set_params, *where_params],
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError(f"Skill {skill_id} 恢复 CAS 失败")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--mode",
        choices=("dry-run", "apply"),
        default="dry-run",
        help="默认只读校验；显式 apply 才更新数据库",
    )
    parser.add_argument("--backup-root", type=Path, default=BACKUP_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = repair_skills(
        PsycopgRepairBackend(backup_root=args.backup_root),
        apply=args.mode == "apply",
    )
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
