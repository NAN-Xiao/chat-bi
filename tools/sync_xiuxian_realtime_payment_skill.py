# -*- coding: utf-8 -*-
"""安全地把修仙实时看板当前 SQL 定向同步到 Data Skill 269。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import psycopg

from core_system_db import core_system_db_config
from publish_xiuxian_dashboard_data_skills import (
    _connection_is_usable,
    _default_retrieval_checker,
    _restore_with_new_connection,
    acquire_publish_lock,
    backup_and_write_skill_snapshot,
    refresh_and_verify_embeddings,
    release_publish_lock,
    skill_recovery_path as _skill_recovery_path,
    utc_timestamp,
    verify_skill_backup,
)
from seed_xiuxian_data_skills import (
    DATASOURCE_ID,
    TENANT_ID,
    _embedding_model,
    _save_embeddings,
    backup_existing_skills,
    build_data_skills,
    load_skill_states_by_ids,
    upsert_skills,
    verify_embeddings,
)
from xiuxian_dashboard_snapshot import (
    load_recommended_dashboards,
    verify_backup,
    write_verified_backup,
)


REALTIME_DASHBOARD_ID = "10604280d5a941af9720800bce6e030f"
REALTIME_VIEW_ID = "2193936101973073920"
REALTIME_SKILL_MARKER = (
    "<!-- data-skill-source:xiuxian:dashboard:realtime-payment -->"
)
EXPECTED_SKILL_ID = 269
RETRIEVAL_QUESTION = "今天每小时支付记录数和收入金额"
DEFAULT_BACKUP_ROOT = (
    Path(__file__).resolve().parents[1]
    / ".codex-runtime"
    / "xiuxian-realtime-payment-skill-backups"
)


class SourceDashboardChangedError(RuntimeError):
    """发布锁内发现实时看板来源发生变化。"""


class RetrievalVerificationError(RuntimeError):
    """定向 Skill 未按预期召回。"""


class SkillSyncRecoveryError(RuntimeError):
    """Skill 更新失败后恢复也失败。"""

    def __init__(self, sync_error: BaseException, recovery_error: BaseException):
        self.sync_error = sync_error
        self.recovery_error = recovery_error
        super().__init__(
            "修仙实时付费 Skill 同步失败且恢复失败: "
            f"sync={sync_error!r}; recovery={recovery_error!r}"
        )


@dataclass(frozen=True)
class DashboardSource:
    dashboard_id: str
    dashboard_name: str
    tenant_id: int
    datasource_id: int
    view_id: str
    title: str
    sql: str
    sql_sha256: str
    update_time: int

    @property
    def guard(self) -> tuple[Any, ...]:
        return (
            self.dashboard_id,
            self.tenant_id,
            self.datasource_id,
            self.view_id,
            self.sql_sha256,
            self.update_time,
        )


@dataclass(frozen=True)
class SyncReport:
    mode: str
    skill_id: int
    source: DashboardSource
    backup_path: str
    updated: bool
    embedding_verified: bool
    retrieval_verified: bool
    prompt: str


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def source_metadata_path(backup_path: Path) -> Path:
    backup_path = Path(backup_path)
    return backup_path.parent / f"{backup_path.name}.realtime-source.json"


def skill_recovery_path(backup_path: Path) -> Path:
    return _skill_recovery_path(Path(backup_path))


def dashboard_source_from_row(row: tuple[Any, ...]) -> DashboardSource:
    """从 core_dashboard 行提取并严格校验唯一实时组件。"""

    dashboard_id, name, tenant_id, datasource_id, canvas_raw, update_time = row
    if str(dashboard_id) != REALTIME_DASHBOARD_ID:
        raise ValueError(f"实时看板 ID 不匹配: {dashboard_id}")
    if int(tenant_id) != TENANT_ID or int(datasource_id) != DATASOURCE_ID:
        raise ValueError("实时看板不属于修仙工作空间 datasource 6")
    try:
        canvas = json.loads(canvas_raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("实时看板 canvas_view_info 不是有效 JSON") from exc
    if not isinstance(canvas, dict) or set(canvas) != {REALTIME_VIEW_ID}:
        raise ValueError(
            "实时看板必须只包含当前组件: "
            f"expected={[REALTIME_VIEW_ID]}, actual={sorted(canvas) if isinstance(canvas, dict) else type(canvas).__name__}"
        )
    view = canvas[REALTIME_VIEW_ID]
    if not isinstance(view, dict):
        raise ValueError("实时付费组件配置不是 JSON 对象")
    direct_sql = view.get("sql")
    source_sql = (
        ((view.get("sourceConfig") or {}).get("sql") or {}).get("sql")
        if isinstance(view.get("sourceConfig"), dict)
        else None
    )
    candidates = [value for value in (direct_sql, source_sql) if isinstance(value, str)]
    if not candidates or not candidates[0].strip():
        raise ValueError("实时付费组件 SQL 为空")
    if any(value != candidates[0] for value in candidates[1:]):
        raise ValueError("实时付费组件直接 SQL 与 sourceConfig SQL 不一致")
    sql = candidates[0]
    chart = view.get("chart") if isinstance(view.get("chart"), dict) else {}
    title = str(chart.get("title") or "")
    if title != "每小时付费数据":
        raise ValueError(f"实时付费组件标题不匹配: {title}")
    return DashboardSource(
        dashboard_id=str(dashboard_id),
        dashboard_name=str(name or ""),
        tenant_id=int(tenant_id),
        datasource_id=int(datasource_id),
        view_id=REALTIME_VIEW_ID,
        title=title,
        sql=sql,
        sql_sha256=_sha256_text(sql),
        update_time=int(update_time),
    )


def extract_skill_sql(prompt: str) -> str:
    pattern = re.compile(
        rf"<!-- dashboard-sql:{re.escape(REALTIME_VIEW_ID)} -->\s*```sql\s*\n"
        r"(?P<sql>[\s\S]*?)\n```"
    )
    matches = [match.group("sql") for match in pattern.finditer(prompt)]
    if len(matches) != 1:
        raise ValueError("实时付费 Skill 必须包含且只包含一个当前看板 SQL 块")
    return matches[0]


def validate_skill_source(skill: Mapping[str, str], source: DashboardSource) -> None:
    prompt = str(skill.get("prompt") or "")
    if not prompt.startswith(REALTIME_SKILL_MARKER):
        raise ValueError("实时付费 Skill marker 不匹配")
    embedded_sql = extract_skill_sql(prompt)
    if embedded_sql != source.sql.strip():
        raise ValueError("实时付费 Skill SQL 与当前看板 SQL 不一致")
    required = ("event_realtime", "ServerPayLog", "$.money", "COUNT(")
    missing = [item for item in required if item not in prompt]
    if missing:
        raise ValueError(f"实时付费 Skill 缺少权威口径: {missing}")


def verify_retrieval_text(text: str) -> None:
    required = ("修仙实时付费趋势", "event_realtime", "ServerPayLog", "$.money")
    missing = [item for item in required if item not in str(text or "")]
    if missing:
        raise RetrievalVerificationError(f"实时付费 Skill 召回文本缺少: {missing}")


def _assert_source_unchanged(before: DashboardSource, after: DashboardSource) -> None:
    if before.guard != after.guard:
        raise SourceDashboardChangedError(
            "实时看板在读取与发布锁之间发生变化，拒绝更新 Skill 269"
        )


def validate_marker_rows(
    rows: list[tuple[Any, Any]], expected_markers: set[str]
) -> dict[int, str]:
    ids = [int(row[0]) for row in rows]
    prompts = [str(row[1] or "") for row in rows]
    markers = [prompt.splitlines()[0].strip() if prompt else "" for prompt in prompts]
    if (
        len(rows) != len(expected_markers)
        or len(set(ids)) != len(expected_markers)
        or len(set(markers)) != len(expected_markers)
        or set(markers) != expected_markers
    ):
        raise RuntimeError(
            "修仙 source marker 目录不一致: "
            f"expected={sorted(expected_markers)}, actual={sorted(markers)}"
        )
    return {
        skill_id: _sha256_text(prompt)
        for skill_id, prompt in zip(ids, prompts, strict=True)
    }


def sync_realtime_skill(backend: Any, *, apply: bool) -> SyncReport:
    """执行只读 dry-run 或只更新 Skill 269 的安全同步。"""

    source = backend.load_source()
    skill = backend.build_skill()
    validate_skill_source(skill, source)
    baseline_hashes = backend.load_skill_hashes()
    backup = backend.load_target_backup()
    backup_path = backend.write_backup(source, backup)
    if not apply:
        return SyncReport(
            mode="dry-run",
            skill_id=EXPECTED_SKILL_ID,
            source=source,
            backup_path=str(backup_path),
            updated=False,
            embedding_verified=False,
            retrieval_verified=False,
            prompt=skill["prompt"],
        )

    expected_states: dict[int, dict[str, Any]] = {}
    failure: BaseException | None = None
    backend.acquire_lock()
    try:
        _assert_source_unchanged(source, backend.load_source())
        backend.upsert_target(skill, expected_states)
        backend.refresh_embedding(EXPECTED_SKILL_ID)
        backend.verify_target(skill)
        backend.verify_other_hashes(baseline_hashes)
        retrieval_text = backend.retrieve(RETRIEVAL_QUESTION)
        verify_retrieval_text(retrieval_text)
    except BaseException as sync_error:
        failure = sync_error
        if expected_states:
            try:
                backend.restore(backup, expected_states)
            except BaseException as recovery_error:
                combined_error = SkillSyncRecoveryError(sync_error, recovery_error)
                failure = combined_error
                raise combined_error from recovery_error
        raise
    finally:
        try:
            backend.release_lock()
        except BaseException as unlock_error:
            if failure is None:
                raise
            failure.add_note(f"发布锁释放失败: {unlock_error!r}")

    return SyncReport(
        mode="apply",
        skill_id=EXPECTED_SKILL_ID,
        source=source,
        backup_path=str(backup_path),
        updated=True,
        embedding_verified=True,
        retrieval_verified=True,
        prompt=skill["prompt"],
    )


class PsycopgSyncBackend:
    """以现有发布器能力实现单 marker 的数据库同步后端。"""

    def __init__(self, *, backup_root: Path = DEFAULT_BACKUP_ROOT):
        self.backup_root = Path(backup_root)
        self._write_connection: Any | None = None
        self._dashboards: list[Any] | None = None
        self._skill: dict[str, str] | None = None
        self._target_backup: dict[str, list[dict[str, Any]]] | None = None
        self._expected_markers: set[str] | None = None

    @staticmethod
    def _connection() -> Any:
        return psycopg.connect(**core_system_db_config())

    def _active_or_new_connection(self) -> tuple[Any, bool]:
        if self._write_connection is not None:
            return self._write_connection, False
        return self._connection(), True

    def load_source(self) -> DashboardSource:
        connection, should_close = self._active_or_new_connection()
        try:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, tenant_id, datasource, canvas_view_info, update_time
                    FROM core_dashboard
                    WHERE id = %s
                      AND tenant_id = %s
                      AND datasource = %s
                      AND node_type = 'leaf'
                      AND COALESCE(delete_flag, 0) = 0
                    """,
                    (REALTIME_DASHBOARD_ID, TENANT_ID, DATASOURCE_ID),
                )
                rows = cur.fetchall()
            if len(rows) != 1:
                raise RuntimeError(f"实时看板记录必须唯一，实际 {len(rows)}")
            return dashboard_source_from_row(rows[0])
        finally:
            if should_close:
                connection.close()

    def build_skill(self) -> dict[str, str]:
        with self._connection() as connection:
            dashboards = load_recommended_dashboards(connection)
        skills = build_data_skills(dashboards)
        matches = [
            skill
            for skill in skills
            if str(skill.get("prompt") or "").startswith(REALTIME_SKILL_MARKER)
        ]
        if len(matches) != 1:
            raise RuntimeError("实时付费 Skill marker 必须唯一")
        markers = {
            str(skill.get("prompt") or "").splitlines()[0].strip()
            for skill in skills
        }
        if len(markers) != 13 or "" in markers:
            raise RuntimeError("生成的修仙 Skill marker 目录必须包含 13 个唯一 marker")
        self._dashboards = dashboards
        self._skill = matches[0]
        self._expected_markers = markers
        return matches[0]

    def load_skill_hashes(self) -> dict[int, str]:
        with self._connection() as connection, connection.cursor() as cur:
            cur.execute(
                """
                SELECT id, prompt
                FROM custom_prompt
                WHERE tenant_id = %s
                  AND type = 'DATA_SKILL'
                  AND specific_ds = TRUE
                  AND datasource_ids = %s::jsonb
                  AND position('data-skill-source:xiuxian:' in COALESCE(prompt, '')) > 0
                ORDER BY id
                """,
                (TENANT_ID, json.dumps([DATASOURCE_ID])),
            )
            rows = cur.fetchall()
        if self._expected_markers is None:
            raise RuntimeError("校验 marker 前必须先构建修仙 Skill 目录")
        return validate_marker_rows(rows, self._expected_markers)

    def load_target_backup(self) -> dict[str, list[dict[str, Any]]]:
        with self._connection() as connection, connection.cursor() as cur:
            backup = backup_existing_skills(cur, [REALTIME_SKILL_MARKER])
        skills = list(backup.get("skills", ()))
        if len(skills) != 1:
            raise RuntimeError(f"Data Skill marker 重复或缺失，实际记录数 {len(skills)}")
        if int(skills[0].get("id")) != EXPECTED_SKILL_ID:
            raise RuntimeError(
                f"实时付费 Skill ID 必须为 {EXPECTED_SKILL_ID}，实际 {skills[0].get('id')}"
            )
        self._target_backup = backup
        return backup

    def write_backup(
        self,
        source: DashboardSource,
        backup: Mapping[str, list[dict[str, Any]]],
    ) -> Path:
        if self._dashboards is None or self._skill is None:
            raise RuntimeError("写备份前必须先构建当前实时付费 Skill")
        backup_path = write_verified_backup(
            self._dashboards,
            self.backup_root,
            f"{utc_timestamp()}-{uuid4().hex[:8]}",
        )
        verify_backup(backup_path)
        with self._connection() as connection:
            captured = backup_and_write_skill_snapshot(
                connection, [self._skill], backup_path
            )
        verified = verify_skill_backup(backup_path)
        if captured != verified or dict(backup) != verified:
            raise RuntimeError("实时付费 Skill 恢复工件与预检快照不一致")
        source_path = source_metadata_path(backup_path)
        source_path.write_text(
            json.dumps(asdict(source), ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        return backup_path

    def acquire_lock(self) -> None:
        if self._write_connection is not None:
            raise RuntimeError("发布锁连接已存在")
        self._write_connection = self._connection()
        acquire_publish_lock(self._write_connection)

    def release_lock(self) -> None:
        if self._write_connection is None:
            return
        connection = self._write_connection
        self._write_connection = None
        try:
            if _connection_is_usable(connection):
                release_publish_lock(connection)
        finally:
            connection.close()

    def _require_write_connection(self) -> Any:
        if self._write_connection is None:
            raise RuntimeError("定向写入必须持有修仙发布锁")
        return self._write_connection

    def upsert_target(
        self,
        skill: dict[str, str],
        expected_states: dict[int, dict[str, Any]],
    ) -> None:
        connection = self._require_write_connection()
        try:
            with connection.cursor() as cur:
                current = backup_existing_skills(cur, [REALTIME_SKILL_MARKER])
                if current != self._target_backup:
                    raise RuntimeError("Skill 269 在备份后发生变化，拒绝覆盖")
                ids = upsert_skills(cur, [skill])
                if ids != [EXPECTED_SKILL_ID]:
                    raise RuntimeError(f"定向更新返回了意外 Skill ID: {ids}")
                cur.execute(
                    """
                    SELECT id, name, description, prompt, visibility_scope,
                           specific_ds, datasource_ids, tenant_id, embedding,
                           embedding_signature
                    FROM custom_prompt
                    WHERE id = %s
                    """,
                    (EXPECTED_SKILL_ID,),
                )
                rows = cur.fetchall()
                if len(rows) != 1:
                    raise RuntimeError("定向更新后无法唯一读取 Skill 269")
                row = rows[0]
                if (
                    int(row[0]) != EXPECTED_SKILL_ID
                    or row[1] != skill["name"]
                    or row[2] != skill["description"]
                    or row[3] != skill["prompt"].strip()
                    or row[4] != "ADMIN_PUBLIC"
                    or row[5] is not True
                    or list(row[6] or []) != [DATASOURCE_ID]
                    or int(row[7]) != TENANT_ID
                    or row[8] is not None
                    or row[9] is not None
                ):
                    raise RuntimeError("Skill 269 写入结果或作用域不符合预期")
                captured_states = load_skill_states_by_ids(cur, ids)
                expected_states.clear()
                expected_states.update(captured_states)
            connection.commit()
        except BaseException:
            try:
                connection.rollback()
            except BaseException:
                pass
            raise

    def refresh_embedding(self, skill_id: int) -> None:
        connection = self._require_write_connection()
        refresh_and_verify_embeddings(connection, [skill_id], _save_embeddings)

    def verify_target(self, skill: Mapping[str, str]) -> None:
        connection = self._require_write_connection()
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, description, prompt, visibility_scope,
                       specific_ds, datasource_ids, tenant_id
                FROM custom_prompt
                WHERE id = %s
                """,
                (EXPECTED_SKILL_ID,),
            )
            rows = cur.fetchall()
            if len(rows) != 1:
                raise RuntimeError("embedding 后无法唯一读取 Skill 269")
            row = rows[0]
            if row[3] != str(skill["prompt"]).strip():
                raise RuntimeError("embedding 后 Skill 269 prompt 发生变化")
            verify_embeddings(cur, [EXPECTED_SKILL_ID], model=_embedding_model())

    def verify_other_hashes(self, baseline_hashes: Mapping[int, str]) -> None:
        current = self.load_skill_hashes()
        baseline_other = {
            skill_id: digest
            for skill_id, digest in baseline_hashes.items()
            if skill_id != EXPECTED_SKILL_ID
        }
        current_other = {
            skill_id: digest
            for skill_id, digest in current.items()
            if skill_id != EXPECTED_SKILL_ID
        }
        if current_other != baseline_other:
            raise RuntimeError("Skill 269 之外的修仙 Skills 发生变化")

    @staticmethod
    def retrieve(question: str) -> str:
        return _default_retrieval_checker(question)

    def restore(
        self,
        backup: Mapping[str, list[dict[str, Any]]],
        expected_states: Mapping[int, Mapping[str, Any]],
    ) -> None:
        original_lock_held = bool(
            self._write_connection is not None
            and _connection_is_usable(self._write_connection)
        )
        _restore_with_new_connection(
            self._connection,
            backup,
            [REALTIME_SKILL_MARKER],
            expected_states,
            original_lock_held=original_lock_held,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--mode",
        choices=("dry-run", "apply"),
        default="dry-run",
        help="默认只读校验并备份；显式 apply 才更新 Skill 269",
    )
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=DEFAULT_BACKUP_ROOT,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = sync_realtime_skill(
        PsycopgSyncBackend(backup_root=args.backup_root),
        apply=args.mode == "apply",
    )
    print(
        json.dumps(
            {
                "mode": report.mode,
                "dashboard_id": report.source.dashboard_id,
                "view_id": report.source.view_id,
                "sql_sha256": report.source.sql_sha256,
                "skill_id": report.skill_id,
                "updated": int(report.updated),
                "embedding_verified": int(report.embedding_verified),
                "retrieval_verified": int(report.retrieval_verified),
                "backup_path": report.backup_path,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
