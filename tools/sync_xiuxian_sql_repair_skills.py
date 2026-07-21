"""定向同步修仙日期与 ServerPayLog SQL 修复 Data Skill。"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
from core_system_db import core_system_db_config, export_postgres_compat_env
from psycopg.types.json import Jsonb
from seed_xiuxian_data_skills import (
    DATE_PARTITION_SKILL_DESCRIPTION,
    DATE_SECTION_END_MARKER,
    DATE_SECTION_MARKER,
    DATE_SPINE_GUIDANCE,
    SERVERPAYLOG_REPAIR_EXAMPLES,
    SERVERPAYLOG_SECTION_END_MARKER,
    SERVERPAYLOG_SECTION_MARKER,
    _acquire_publish_lock,
    _embedding_model,
    _release_publish_lock,
    _save_embeddings,
    _stable_skill_state,
    backup_existing_skills,
    load_skill_states_by_ids,
    restore_skills,
    validate_prompt_length,
    verify_embeddings,
)

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
DB = core_system_db_config()

TENANT_ID = 7482727237662281728
DATASOURCE_ID = 6
DATE_SKILL_MARKER = "<!-- data-skill-source:xiuxian:date-partition-aggregation -->"
SERVERPAYLOG_SKILL_MARKER = (
    "<!-- data-skill-source:xiuxian:serverpaylog-monetization-arppu -->"
)
TARGET_SKILL_MARKERS = (DATE_SKILL_MARKER, SERVERPAYLOG_SKILL_MARKER)
DATE_RETRIEVAL_QUESTION = "最近15天补齐新增趋势"
SERVERPAYLOG_RETRIEVAL_QUESTION = "最近七天收入和 ARPPU"
DEFAULT_BACKUP_ROOT = ROOT / ".codex-runtime" / "xiuxian-sql-repair-skill-backups"
BACKUP_VERSION = 1


class TargetSkillChangedError(RuntimeError):
    """发布锁内目标 Skill 已偏离 dry-run 快照。"""


class RetrievalVerificationError(RuntimeError):
    """目标问题未召回预期 Data Skill。"""


class SyncRecoveryError(RuntimeError):
    """同步失败后，两条目标 Skill 的自动恢复也失败。"""

    def __init__(self, sync_error: BaseException, recovery_error: BaseException):
        self.sync_error = sync_error
        self.recovery_error = recovery_error
        super().__init__(
            "修仙 SQL 修复 Skill 同步失败且恢复失败: "
            f"sync={sync_error!r}; recovery={recovery_error!r}"
        )


@dataclass(frozen=True)
class TargetSkill:
    id: int
    marker: str
    name: str
    description: str | None
    prompt: str


@dataclass(frozen=True)
class PromptCheck:
    skill_id: int
    marker: str
    original_hash: str
    desired_hash: str
    original_length: int
    desired_length: int
    original_description_hash: str
    desired_description_hash: str
    original_description_length: int
    desired_description_length: int


@dataclass(frozen=True)
class SyncReport:
    mode: str
    target_skill_count: int
    skill_ids: tuple[int, ...]
    backup_path: str
    updated: bool
    embedding_verified: bool
    retrieval_verified: bool
    prompt_checks: tuple[PromptCheck, ...]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_nullable_text(value: str | None) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def managed_section_end_marker(start_marker: str) -> str:
    pairs = {
        DATE_SECTION_MARKER: DATE_SECTION_END_MARKER,
        SERVERPAYLOG_SECTION_MARKER: SERVERPAYLOG_SECTION_END_MARKER,
    }
    try:
        return pairs[start_marker]
    except KeyError as exc:
        raise ValueError(f"未知托管段 marker: {start_marker}") from exc


def replace_managed_section(prompt: str, start_marker: str, content: str) -> str:
    """成对替换托管段；首次追加，重复执行保持字节一致。"""

    end_marker = managed_section_end_marker(start_marker)
    start_count = prompt.count(start_marker)
    end_count = prompt.count(end_marker)
    if start_count != end_count or start_count > 1:
        raise ValueError("托管段 marker 必须成对且最多出现一次")
    managed = f"{start_marker}\n{content.strip()}\n{end_marker}"
    if start_count == 0:
        return f"{prompt.rstrip()}\n\n{managed}".strip()

    start_index = prompt.index(start_marker)
    end_index = prompt.index(end_marker, start_index)
    prefix = prompt[:start_index].rstrip()
    suffix = prompt[end_index + len(end_marker) :].strip()
    return "\n\n".join(part for part in (prefix, managed, suffix) if part)


def build_target_prompts(current: Mapping[str, str]) -> dict[str, str]:
    """只为日期和 ServerPayLog 两条 source marker 构造目标 prompt。"""

    if set(current) != set(TARGET_SKILL_MARKERS):
        raise ValueError("定向同步输入必须恰好包含日期与 ServerPayLog 两条 Skill")
    return {
        DATE_SKILL_MARKER: replace_managed_section(
            str(current[DATE_SKILL_MARKER]),
            DATE_SECTION_MARKER,
            DATE_SPINE_GUIDANCE,
        ),
        SERVERPAYLOG_SKILL_MARKER: replace_managed_section(
            str(current[SERVERPAYLOG_SKILL_MARKER]),
            SERVERPAYLOG_SECTION_MARKER,
            SERVERPAYLOG_REPAIR_EXAMPLES,
        ),
    }


def build_target_descriptions(
    current: Mapping[str, str | None],
) -> dict[str, str | None]:
    """日期 Skill 使用 canonical 描述，ServerPayLog 保留当前描述。"""

    if set(current) != set(TARGET_SKILL_MARKERS):
        raise ValueError("定向同步输入必须恰好包含日期与 ServerPayLog 两条 Skill")
    return {
        DATE_SKILL_MARKER: DATE_PARTITION_SKILL_DESCRIPTION,
        SERVERPAYLOG_SKILL_MARKER: current[SERVERPAYLOG_SKILL_MARKER],
    }


def _prompt_checks(
    targets: Mapping[str, TargetSkill],
    descriptions: Mapping[str, str | None],
    prompts: Mapping[str, str],
) -> tuple[PromptCheck, ...]:
    checks: list[PromptCheck] = []
    for marker in TARGET_SKILL_MARKERS:
        target = targets[marker]
        desired_description = descriptions[marker]
        desired = str(prompts[marker]).strip()
        validate_prompt_length(desired)
        checks.append(
            PromptCheck(
                skill_id=int(target.id),
                marker=marker,
                original_hash=_sha256_text(target.prompt),
                desired_hash=_sha256_text(desired),
                original_length=len(target.prompt),
                desired_length=len(desired),
                original_description_hash=_sha256_nullable_text(target.description),
                desired_description_hash=_sha256_nullable_text(desired_description),
                original_description_length=len(target.description or ""),
                desired_description_length=len(desired_description or ""),
            )
        )
    return tuple(checks)


def _assert_target_snapshot_unchanged(
    baseline: Mapping[str, TargetSkill],
    current: Mapping[str, TargetSkill],
) -> None:
    if set(baseline) != set(current) or set(current) != set(TARGET_SKILL_MARKERS):
        raise TargetSkillChangedError("发布锁内目标 Skill marker 集合已变化")
    for marker in TARGET_SKILL_MARKERS:
        before = baseline[marker]
        after = current[marker]
        if before.id != after.id:
            raise TargetSkillChangedError(f"目标 Skill ID 已变化: {marker}")
        if _sha256_text(before.name) != _sha256_text(after.name):
            raise TargetSkillChangedError(f"目标 Skill name hash 已变化: {marker}")
        if _sha256_nullable_text(before.description) != _sha256_nullable_text(
            after.description
        ):
            raise TargetSkillChangedError(
                f"目标 Skill description hash 已变化: {marker}"
            )
        if _sha256_text(before.prompt) != _sha256_text(after.prompt):
            raise TargetSkillChangedError(f"目标 Skill prompt hash 已变化: {marker}")


def assert_backup_matches_targets(
    backup: Mapping[str, Sequence[Mapping[str, Any]]],
    targets: Mapping[str, TargetSkill],
) -> None:
    """确认恢复工件与锁内读取的两条目标 Skill 属于同一版本。"""

    rows = [dict(row) for row in backup.get("skills", ())]
    if len(rows) != 2:
        raise TargetSkillChangedError(
            f"恢复备份必须精确包含两条目标 Data Skill，实际 {len(rows)}"
        )
    by_id = {int(row["id"]): row for row in rows}
    target_ids = {target.id for target in targets.values()}
    if len(by_id) != 2 or set(by_id) != target_ids:
        raise TargetSkillChangedError("恢复备份 ID 与锁内目标不一致")
    for marker in TARGET_SKILL_MARKERS:
        target = targets[marker]
        backup_row = by_id[target.id]
        backup_name = str(backup_row.get("name") or "")
        if _sha256_text(backup_name) != _sha256_text(target.name):
            raise TargetSkillChangedError(
                f"恢复备份与锁内目标 name hash 不一致: id={target.id}"
            )
        backup_description = backup_row.get("description")
        if _sha256_nullable_text(backup_description) != _sha256_nullable_text(
            target.description
        ):
            raise TargetSkillChangedError(
                f"恢复备份与锁内目标 description hash 不一致: id={target.id}"
            )
        backup_prompt = str(backup_row.get("prompt") or "")
        if _sha256_text(backup_prompt) != _sha256_text(target.prompt):
            raise TargetSkillChangedError(
                f"恢复备份与锁内目标 prompt hash 不一致: id={target.id}"
            )


def _verify_retrieval_text(text: str, required: Sequence[str], question: str) -> None:
    missing = [value for value in required if value not in str(text or "")]
    if missing:
        raise RetrievalVerificationError(f"召回问题 {question!r} 缺少预期内容: {missing}")


def sync_target_skills(backend: Any, *, apply: bool) -> SyncReport:
    """dry-run 只备份与校验；apply 才在发布锁内更新两条 Skill。"""

    targets = backend.load_targets(for_update=False)
    current_descriptions = {
        marker: targets[marker].description for marker in TARGET_SKILL_MARKERS
    }
    current_prompts = {marker: targets[marker].prompt for marker in TARGET_SKILL_MARKERS}
    desired_descriptions = build_target_descriptions(current_descriptions)
    desired_prompts = build_target_prompts(current_prompts)
    checks = _prompt_checks(targets, desired_descriptions, desired_prompts)
    other_hashes = backend.load_other_hashes()
    skill_ids = tuple(targets[marker].id for marker in TARGET_SKILL_MARKERS)
    if not apply:
        backup_path = Path(
            backend.backup(targets, desired_descriptions, desired_prompts)
        )
        return SyncReport(
            mode="dry-run",
            target_skill_count=2,
            skill_ids=skill_ids,
            backup_path=str(backup_path),
            updated=False,
            embedding_verified=False,
            retrieval_verified=False,
            prompt_checks=checks,
        )

    locked = False
    write_attempted = False
    wrote = False
    failure: BaseException | None = None
    backup_path: Path | None = None
    try:
        backend.lock()
        locked = True
        locked_targets = backend.load_targets(for_update=True)
        _assert_target_snapshot_unchanged(targets, locked_targets)
        locked_prompts = {
            marker: locked_targets[marker].prompt for marker in TARGET_SKILL_MARKERS
        }
        locked_descriptions = {
            marker: locked_targets[marker].description
            for marker in TARGET_SKILL_MARKERS
        }
        desired_descriptions = build_target_descriptions(locked_descriptions)
        desired_prompts = build_target_prompts(locked_prompts)
        checks = _prompt_checks(
            locked_targets,
            desired_descriptions,
            desired_prompts,
        )
        skill_ids = tuple(
            locked_targets[marker].id for marker in TARGET_SKILL_MARKERS
        )
        backup_path = Path(
            backend.backup(
                locked_targets,
                desired_descriptions,
                desired_prompts,
            )
        )
        write_attempted = True
        updated_ids = tuple(
            backend.cas_update(
                locked_targets,
                desired_descriptions,
                desired_prompts,
            )
        )
        if updated_ids != skill_ids:
            raise RuntimeError(f"定向 CAS 返回意外 Skill ID: {updated_ids}")
        wrote = True
        backend.refresh_embeddings(updated_ids)
        backend.verify_targets(desired_descriptions, desired_prompts, updated_ids)
        backend.verify_other_hashes(other_hashes)
        _verify_retrieval_text(
            backend.retrieve(DATE_RETRIEVAL_QUESTION),
            (DATE_SKILL_MARKER, "day_offsets", "日期骨架只负责补齐输出日期"),
            DATE_RETRIEVAL_QUESTION,
        )
        _verify_retrieval_text(
            backend.retrieve(SERVERPAYLOG_RETRIEVAL_QUESTION),
            (
                SERVERPAYLOG_SKILL_MARKER,
                "ServerPayLog",
                "personal.money",
                "COUNT(DISTINCT uid)",
            ),
            SERVERPAYLOG_RETRIEVAL_QUESTION,
        )
    except BaseException as exc:
        failure = exc
        if write_attempted:
            try:
                backend.restore()
            except BaseException as recovery_error:
                combined = SyncRecoveryError(exc, recovery_error)
                failure = combined
                raise combined from recovery_error
        raise
    finally:
        if locked:
            try:
                backend.unlock()
            except BaseException as unlock_error:
                if failure is not None:
                    failure.add_note(f"发布锁释放失败: {unlock_error!r}")
                elif wrote:
                    try:
                        backend.restore()
                    except BaseException as recovery_error:
                        raise SyncRecoveryError(
                            unlock_error,
                            recovery_error,
                        ) from recovery_error
                    raise
                else:
                    raise

    if backup_path is None:
        raise RuntimeError("apply 完成后缺少恢复备份路径")
    return SyncReport(
        mode="apply",
        target_skill_count=2,
        skill_ids=skill_ids,
        backup_path=str(backup_path),
        updated=True,
        embedding_verified=True,
        retrieval_verified=True,
        prompt_checks=checks,
    )


def _json_default(value: Any) -> str:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return str(value)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        default=_json_default,
    ).encode("utf-8")


def _connection_is_usable(connection: Any | None) -> bool:
    return connection is not None and not bool(getattr(connection, "closed", True))


class PsycopgBackend:
    """只读两条 source marker，并用独立恢复工件执行安全定向同步。"""

    def __init__(self, *, backup_root: Path = DEFAULT_BACKUP_ROOT):
        self.backup_root = Path(backup_root)
        self._write_connection: Any | None = None
        self._backup: dict[str, list[dict[str, Any]]] | None = None
        self._expected_states: dict[int, dict[str, Any]] = {}

    @staticmethod
    def _connection() -> Any:
        return psycopg.connect(**core_system_db_config())

    def _active_or_new_connection(self) -> tuple[Any, bool]:
        if self._write_connection is not None:
            return self._write_connection, False
        return self._connection(), True

    @staticmethod
    def _load_targets_on(
        connection: Any,
        *,
        for_update: bool,
    ) -> dict[str, TargetSkill]:
        suffix = " FOR UPDATE" if for_update else ""
        with connection.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, name, description, prompt
                FROM custom_prompt
                WHERE tenant_id = %s
                  AND type = 'DATA_SKILL'
                  AND specific_ds = TRUE
                  AND datasource_ids = %s::jsonb
                  AND (
                      position(%s in COALESCE(prompt, '')) > 0
                      OR position(%s in COALESCE(prompt, '')) > 0
                  )
                ORDER BY id{suffix}
                """,
                (
                    TENANT_ID,
                    Jsonb([DATASOURCE_ID]),
                    DATE_SKILL_MARKER,
                    SERVERPAYLOG_SKILL_MARKER,
                ),
            )
            rows = cur.fetchall()
        if len(rows) != 2:
            raise RuntimeError(f"目标 Data Skill 必须恰好两条，实际 {len(rows)}")
        targets: dict[str, TargetSkill] = {}
        for skill_id, name_value, description_value, prompt_value in rows:
            name = str(name_value or "")
            prompt = str(prompt_value or "")
            matched = [marker for marker in TARGET_SKILL_MARKERS if marker in prompt]
            if len(matched) != 1 or prompt.count(matched[0]) != 1:
                raise RuntimeError(f"Data Skill source marker 不唯一: id={skill_id}")
            marker = matched[0]
            if marker in targets:
                raise RuntimeError(f"Data Skill source marker 重复: {marker}")
            targets[marker] = TargetSkill(
                id=int(skill_id),
                marker=marker,
                name=name,
                description=description_value,
                prompt=prompt,
            )
        if set(targets) != set(TARGET_SKILL_MARKERS):
            raise RuntimeError("日期与 ServerPayLog source marker 未完整命中")
        if len({target.id for target in targets.values()}) != 2:
            raise RuntimeError("两条目标 Data Skill ID 必须唯一")
        return {marker: targets[marker] for marker in TARGET_SKILL_MARKERS}

    def load_targets(self, *, for_update: bool = False) -> dict[str, TargetSkill]:
        if for_update:
            if self._write_connection is None:
                raise RuntimeError("锁内重读必须持有修仙发布锁")
            return self._load_targets_on(self._write_connection, for_update=True)
        connection = self._connection()
        try:
            return self._load_targets_on(connection, for_update=False)
        finally:
            connection.close()

    def load_other_hashes(self) -> dict[int, tuple[str, str, str, str]]:
        connection, should_close = self._active_or_new_connection()
        try:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, description, prompt, embedding_signature
                    FROM custom_prompt
                    WHERE tenant_id = %s
                      AND type = 'DATA_SKILL'
                      AND specific_ds = TRUE
                      AND datasource_ids = %s::jsonb
                      AND position('data-skill-source:xiuxian:' in COALESCE(prompt, '')) > 0
                    ORDER BY id
                    """,
                    (TENANT_ID, Jsonb([DATASOURCE_ID])),
                )
                rows = cur.fetchall()
        finally:
            if should_close:
                connection.close()
        target_ids = {
            target.id for target in self.load_targets(for_update=False).values()
        }
        other = {
            int(skill_id): (
                _sha256_text(str(name or "")),
                _sha256_nullable_text(description),
                _sha256_text(str(prompt or "")),
                str(signature or ""),
            )
            for skill_id, name, description, prompt, signature in rows
            if int(skill_id) not in target_ids
        }
        if len(other) != 11:
            raise RuntimeError(f"目标之外的修仙 Data Skill 必须为 11 条，实际 {len(other)}")
        return other

    def backup(
        self,
        targets: Mapping[str, TargetSkill],
        descriptions: Mapping[str, str | None],
        prompts: Mapping[str, str],
    ) -> Path:
        self.backup_root.mkdir(parents=True, exist_ok=True)
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = self.backup_root / f"{timestamp}-{uuid4().hex[:8]}"
        staging = target.with_name(f".{target.name}.{os.getpid()}.staging")
        staging.mkdir(parents=False, exist_ok=False)
        try:
            connection, should_close = self._active_or_new_connection()
            try:
                with connection.cursor() as cur:
                    backup = backup_existing_skills(cur, TARGET_SKILL_MARKERS)
            finally:
                if should_close:
                    connection.close()
            assert_backup_matches_targets(backup, targets)
            checks = _prompt_checks(targets, descriptions, prompts)
            payload = {
                "version": BACKUP_VERSION,
                "tenant_id": TENANT_ID,
                "datasource_id": DATASOURCE_ID,
                "markers": list(TARGET_SKILL_MARKERS),
                "backup": backup,
                "prompt_checks": [asdict(check) for check in checks],
            }
            payload_bytes = _json_bytes(payload)
            (staging / "recovery.json").write_bytes(payload_bytes)
            manifest = {
                "version": BACKUP_VERSION,
                "tenant_id": TENANT_ID,
                "datasource_id": DATASOURCE_ID,
                "target_skill_count": 2,
                "recovery_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            }
            (staging / "manifest.json").write_bytes(_json_bytes(manifest))
            staging.replace(target)
        except BaseException:
            if staging.exists():
                for child in staging.iterdir():
                    child.unlink()
                staging.rmdir()
            raise
        saved_payload = (target / "recovery.json").read_bytes()
        saved_manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        if saved_manifest.get("recovery_sha256") != hashlib.sha256(saved_payload).hexdigest():
            raise RuntimeError("恢复备份验签失败")
        self._backup = backup
        return target

    def lock(self) -> None:
        if self._write_connection is not None:
            raise RuntimeError("修仙发布锁已持有")
        connection = self._connection()
        try:
            with connection.cursor() as cur:
                _acquire_publish_lock(cur)
        except BaseException:
            try:
                connection.rollback()
            finally:
                connection.close()
            raise
        self._write_connection = connection

    def unlock(self) -> None:
        if self._write_connection is None:
            return
        connection = self._write_connection
        self._write_connection = None
        try:
            if _connection_is_usable(connection):
                with connection.cursor() as cur:
                    _release_publish_lock(cur)
        finally:
            connection.close()

    def _require_write_connection(self) -> Any:
        if self._write_connection is None:
            raise RuntimeError("定向写入必须持有修仙发布锁")
        return self._write_connection

    def cas_update(
        self,
        targets: Mapping[str, TargetSkill],
        descriptions: Mapping[str, str | None],
        prompts: Mapping[str, str],
    ) -> list[int]:
        if self._backup is None:
            raise RuntimeError("CAS 更新前必须创建恢复备份")
        connection = self._require_write_connection()
        ids: list[int] = []
        try:
            with connection.cursor() as cur:
                for marker in TARGET_SKILL_MARKERS:
                    target = targets[marker]
                    desired_description = descriptions[marker]
                    desired = str(prompts[marker]).strip()
                    if marker == DATE_SKILL_MARKER:
                        cur.execute(
                            """
                            UPDATE custom_prompt
                            SET description = %s,
                                prompt = %s,
                                embedding = NULL,
                                embedding_signature = NULL
                            WHERE id = %s
                              AND tenant_id = %s
                              AND type = 'DATA_SKILL'
                              AND specific_ds = TRUE
                              AND datasource_ids = %s::jsonb
                              AND name IS NOT DISTINCT FROM %s
                              AND description IS NOT DISTINCT FROM %s
                              AND prompt = %s
                            """,
                            (
                                desired_description,
                                desired,
                                target.id,
                                TENANT_ID,
                                Jsonb([DATASOURCE_ID]),
                                target.name,
                                target.description,
                                target.prompt,
                            ),
                        )
                    else:
                        cur.execute(
                            """
                            UPDATE custom_prompt
                            SET prompt = %s,
                                embedding = NULL,
                                embedding_signature = NULL
                            WHERE id = %s
                              AND tenant_id = %s
                              AND type = 'DATA_SKILL'
                              AND specific_ds = TRUE
                              AND datasource_ids = %s::jsonb
                              AND name IS NOT DISTINCT FROM %s
                              AND description IS NOT DISTINCT FROM %s
                              AND prompt = %s
                            """,
                            (
                                desired,
                                target.id,
                                TENANT_ID,
                                Jsonb([DATASOURCE_ID]),
                                target.name,
                                target.description,
                                target.prompt,
                            ),
                        )
                    if cur.rowcount != 1:
                        raise TargetSkillChangedError(
                            f"目标 Skill CAS 更新失败: id={target.id}"
                        )
                    ids.append(target.id)
                states = load_skill_states_by_ids(cur, ids)
                if set(states) != set(ids):
                    raise RuntimeError("无法构造两条目标 Skill 的发布期望态")
                self._expected_states = states
            connection.commit()
            return ids
        except BaseException:
            connection.rollback()
            raise

    def refresh_embeddings(self, skill_ids: Sequence[int]) -> None:
        normalized_ids = [int(skill_id) for skill_id in skill_ids]
        saved = _save_embeddings(normalized_ids)
        if saved != len(normalized_ids):
            raise RuntimeError(
                f"Data Skill embedding 保存不完整: 期望 {len(normalized_ids)}，实际 {saved}"
            )
        with self._require_write_connection().cursor() as cur:
            verify_embeddings(cur, normalized_ids, model=_embedding_model())

    def verify_targets(
        self,
        descriptions: Mapping[str, str | None],
        prompts: Mapping[str, str],
        skill_ids: Sequence[int],
    ) -> None:
        loaded_targets = self._load_targets_on(
            self._require_write_connection(),
            for_update=False,
        )
        expected_by_id = {
            loaded_targets[marker].id: (
                loaded_targets[marker].name,
                descriptions[marker],
                str(prompts[marker]).strip(),
            )
            for marker in TARGET_SKILL_MARKERS
        }
        if set(expected_by_id) != {int(skill_id) for skill_id in skill_ids}:
            raise RuntimeError("目标 Skill 回读 ID 集合不一致")
        with self._require_write_connection().cursor() as cur:
            cur.execute(
                """
                SELECT id, name, description, prompt
                FROM custom_prompt
                WHERE tenant_id = %s AND id = ANY(%s)
                ORDER BY id
                """,
                (TENANT_ID, list(expected_by_id)),
            )
            rows = cur.fetchall()
            actual = {
                int(skill_id): (str(name or ""), description, str(prompt or ""))
                for skill_id, name, description, prompt in rows
            }
            if actual != expected_by_id:
                raise RuntimeError("两条目标 Data Skill 写入后回读不一致")
            verify_embeddings(cur, list(expected_by_id), model=_embedding_model())

    def verify_other_hashes(
        self,
        baseline: Mapping[int, tuple[str, str, str, str]],
    ) -> None:
        current = self.load_other_hashes()
        if dict(current) != dict(baseline):
            raise RuntimeError("目标之外的 11 条修仙 Data Skill 发生变化")

    @staticmethod
    def retrieve(question: str) -> str:
        export_postgres_compat_env(DB)
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))
        from sqlmodel import Session

        from apps.chat.curd.custom_prompt import find_data_skills
        from common.core.db import engine

        with Session(engine) as session:
            text, _logs, _model = find_data_skills(
                session,
                datasource=DATASOURCE_ID,
                tenant_id=TENANT_ID,
                target_scope="SMART_QA",
                question=question,
            )
        return text

    def restore(self) -> None:
        if self._backup is None:
            raise RuntimeError("恢复所需的两条 Skill 快照不完整")
        connection = self._write_connection
        owns_connection = False
        if not _connection_is_usable(connection):
            connection = self._connection()
            try:
                with connection.cursor() as cur:
                    _acquire_publish_lock(cur)
            except BaseException:
                try:
                    connection.rollback()
                finally:
                    connection.close()
                raise
            owns_connection = True
        try:
            connection.rollback()
            original_rows = [dict(row) for row in self._backup.get("skills", ())]
            original_by_id = {int(row["id"]): row for row in original_rows}
            affected_ids = sorted(original_by_id)
            if len(affected_ids) != 2:
                raise RuntimeError("恢复备份必须精确包含两条目标 Data Skill")
            if self._expected_states:
                with connection.cursor() as cur:
                    restore_skills(
                        cur,
                        self._backup,
                        affected_ids=affected_ids,
                        expected_states=self._expected_states,
                    )
            else:
                with connection.cursor() as cur:
                    current_states = load_skill_states_by_ids(
                        cur,
                        affected_ids,
                        for_update=True,
                    )
                if set(current_states) != set(original_by_id):
                    raise TargetSkillChangedError(
                        "CAS 未形成发布期望态，且当前 Skill ID 已偏离恢复备份"
                    )
                conflicts = [
                    skill_id
                    for skill_id in affected_ids
                    if _stable_skill_state(current_states[skill_id])
                    != _stable_skill_state(original_by_id[skill_id])
                ]
                if conflicts:
                    raise TargetSkillChangedError(
                        "CAS 未形成发布期望态，当前 Skill 也不等于备份原态，"
                        f"拒绝覆盖: {conflicts}"
                    )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            if owns_connection:
                try:
                    with connection.cursor() as cur:
                        _release_publish_lock(cur)
                finally:
                    connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--mode",
        choices=("dry-run", "apply"),
        default="dry-run",
        help="默认创建恢复备份并校验两条 prompt；显式 apply 才更新数据库",
    )
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = sync_target_skills(
        PsycopgBackend(backup_root=args.backup_root),
        apply=args.mode == "apply",
    )
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
