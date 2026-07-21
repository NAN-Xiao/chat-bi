"""验证修仙 SQL 修复 Skill 的定向安全同步。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import seed_xiuxian_data_skills as seed  # noqa: E402
import sync_xiuxian_sql_repair_skills as sync  # noqa: E402


def _targets(
    *,
    date_name: str = "修仙业务日期与按日聚合口径",
    date_description: str = "current date description",
    date_prompt: str = f"{sync.DATE_SKILL_MARKER}\ndate prompt",
    payment_name: str = "修仙 ServerPayLog 收入与 ARPU/ARPPU",
    payment_description: str = "current payment description",
    payment_prompt: str = f"{sync.SERVERPAYLOG_SKILL_MARKER}\npayment prompt",
):
    return {
        sync.DATE_SKILL_MARKER: sync.TargetSkill(
            id=255,
            marker=sync.DATE_SKILL_MARKER,
            name=date_name,
            description=date_description,
            prompt=date_prompt,
        ),
        sync.SERVERPAYLOG_SKILL_MARKER: sync.TargetSkill(
            id=202,
            marker=sync.SERVERPAYLOG_SKILL_MARKER,
            name=payment_name,
            description=payment_description,
            prompt=payment_prompt,
        ),
    }


class FakeBackend:
    def __init__(self) -> None:
        self.targets = _targets()
        self.locked_targets = self.targets
        self.events: list[str] = []
        self.backup_path = ROOT / ".codex-runtime" / "test-sql-repair-backup"
        self.backup_targets = self.targets
        self.current_targets = self.targets
        self.backup_originals = self.targets
        self.published_descriptions: dict[str, str | None] | None = None
        self.published_prompts: dict[str, str] | None = None
        self.restore_outcome: str | None = None
        self.cas_failure_mode: str | None = None
        self.fail_lock = False
        self.fail_retrieval = False
        self.fail_unlock = False

    def load_targets(self, *, for_update: bool = False):
        self.events.append(f"load:{for_update}")
        return self.locked_targets if for_update else self.targets

    def load_other_hashes(self):
        self.events.append("load-other")
        return {index: f"hash-{index}" for index in range(11)}

    def backup(self, targets, descriptions, prompts):
        self.events.append("backup")
        assert (
            set(targets)
            == set(descriptions)
            == set(prompts)
            == set(sync.TARGET_SKILL_MARKERS)
        )
        backup = {
            "skills": [
                {
                    "id": self.backup_targets[marker].id,
                    "name": self.backup_targets[marker].name,
                    "description": self.backup_targets[marker].description,
                    "prompt": self.backup_targets[marker].prompt,
                }
                for marker in sync.TARGET_SKILL_MARKERS
            ]
        }
        sync.assert_backup_matches_targets(backup, targets)
        self.backup_originals = targets
        self.published_descriptions = dict(descriptions)
        self.published_prompts = dict(prompts)
        return self.backup_path

    def lock(self) -> None:
        self.events.append("lock")
        if self.fail_lock:
            raise RuntimeError("lock failed")

    def unlock(self) -> None:
        self.events.append("unlock")
        if self.fail_unlock:
            raise RuntimeError("unlock failed")

    def cas_update(self, targets, descriptions, prompts):
        self.events.append("cas-update")
        assert (
            set(targets)
            == set(descriptions)
            == set(prompts)
            == set(sync.TARGET_SKILL_MARKERS)
        )
        if self.cas_failure_mode == "before-write":
            raise RuntimeError("cas failed before write")
        self.current_targets = {
            marker: sync.TargetSkill(
                id=targets[marker].id,
                marker=marker,
                name=targets[marker].name,
                description=descriptions[marker],
                prompt=prompts[marker],
            )
            for marker in sync.TARGET_SKILL_MARKERS
        }
        if self.cas_failure_mode == "after-write":
            raise RuntimeError("cas failed after commit")
        return [targets[marker].id for marker in sync.TARGET_SKILL_MARKERS]

    def refresh_embeddings(self, skill_ids) -> None:
        self.events.append(f"embeddings:{','.join(map(str, skill_ids))}")

    def verify_targets(self, descriptions, prompts, skill_ids) -> None:
        self.events.append("verify-targets")
        assert len(descriptions) == len(prompts) == len(skill_ids) == 2
        assert descriptions[sync.DATE_SKILL_MARKER] == seed.DATE_PARTITION_SKILL_DESCRIPTION
        assert (
            descriptions[sync.SERVERPAYLOG_SKILL_MARKER]
            == self.targets[sync.SERVERPAYLOG_SKILL_MARKER].description
        )

    def verify_other_hashes(self, baseline) -> None:
        self.events.append("verify-other")
        assert len(baseline) == 11

    def retrieve(self, question: str) -> str:
        self.events.append(f"retrieve:{question}")
        if self.fail_retrieval:
            return "无关召回"
        if question == sync.DATE_RETRIEVAL_QUESTION:
            return f"{sync.DATE_SKILL_MARKER}\nday_offsets\n日期骨架只负责补齐输出日期"
        return (
            f"{sync.SERVERPAYLOG_SKILL_MARKER}\nServerPayLog\n"
            "personal.money\nCOUNT(DISTINCT uid)"
        )

    def restore(self) -> None:
        self.events.append("restore")
        current_definitions = {
            marker: (
                self.current_targets[marker].description,
                self.current_targets[marker].prompt,
            )
            for marker in sync.TARGET_SKILL_MARKERS
        }
        backup_definitions = {
            marker: (
                self.backup_originals[marker].description,
                self.backup_originals[marker].prompt,
            )
            for marker in sync.TARGET_SKILL_MARKERS
        }
        if current_definitions == backup_definitions:
            self.restore_outcome = "no-op"
            return
        assert self.published_descriptions is not None
        assert self.published_prompts is not None
        published_definitions = {
            marker: (
                self.published_descriptions[marker],
                self.published_prompts[marker],
            )
            for marker in sync.TARGET_SKILL_MARKERS
        }
        if current_definitions == published_definitions:
            self.current_targets = self.backup_originals
            self.restore_outcome = "restored"
            return
        raise RuntimeError("restore conflict")


def _canonical_target_prompts() -> dict[str, str]:
    from xiuxian_dashboard_skill_catalog import EXPECTED_VIEW_IDS
    from xiuxian_dashboard_snapshot import DashboardSnapshot

    view_ids = sorted(EXPECTED_VIEW_IDS)
    dashboards = []
    for dashboard_index in range(9):
        canvas = {
            view_id: {"sql": f"SELECT {index} AS metric_{index}"}
            for index, view_id in enumerate(
                view_ids[dashboard_index * 5 : dashboard_index * 5 + 5],
                start=dashboard_index * 5,
            )
        }
        dashboards.append(
            DashboardSnapshot.from_row(
                (
                    f"dashboard-{dashboard_index}",
                    f"推荐看板 {dashboard_index}",
                    seed.TENANT_ID,
                    seed.DATASOURCE_ID,
                    json.dumps(canvas, ensure_ascii=False),
                )
            )
        )
    skills = seed.build_data_skills(dashboards)
    payment_prompt = next(
        skill["prompt"]
        for skill in skills
        if sync.SERVERPAYLOG_SKILL_MARKER in skill["prompt"]
    )
    return {
        sync.DATE_SKILL_MARKER: seed.DATE_PARTITION_SKILL["prompt"],
        sync.SERVERPAYLOG_SKILL_MARKER: payment_prompt,
    }


def _restore_skill_state(
    skill_id: int,
    *,
    description: str,
    prompt: str,
) -> dict[str, object]:
    return {
        "id": skill_id,
        "tenant_id": sync.TENANT_ID,
        "type": "DATA_SKILL",
        "create_time": None,
        "name": f"skill-{skill_id}",
        "description": description,
        "target_scope": "SMART_QA",
        "active": True,
        "visible": True,
        "ai_model_id": None,
        "create_by": "tester",
        "visibility_scope": "ADMIN_PUBLIC",
        "prompt": prompt,
        "embedding": [0.1, 0.2],
        "embedding_signature": f"signature-{skill_id}",
        "specific_ds": True,
        "datasource_ids": [sync.DATASOURCE_ID],
    }


class RestoreCursor:
    def __init__(self, connection: RestoreConnection) -> None:
        self.connection = connection
        self.rowcount = 0
        self.rows: list[tuple[dict[str, object]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=()) -> None:
        statement = str(query)
        normalized_params = tuple(params)
        self.connection.executions.append((statement, normalized_params))
        if "SELECT to_jsonb(cp)" in statement:
            skill_ids = [int(skill_id) for skill_id in normalized_params[0]]
            self.rows = [
                (dict(self.connection.current_states[skill_id]),)
                for skill_id in skill_ids
                if skill_id in self.connection.current_states
            ]
            self.rowcount = len(self.rows)
            return
        if "UPDATE custom_prompt SET" in statement:
            self.rows = []
            self.rowcount = 1
            return
        raise AssertionError(f"未预期的恢复 SQL: {statement}")

    def fetchall(self):
        return list(self.rows)


class RestoreConnection:
    def __init__(self, current_states: dict[int, dict[str, object]]) -> None:
        self.current_states = current_states
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.commit_calls = 0
        self.rollback_calls = 0
        self.closed = False

    def cursor(self):
        return RestoreCursor(self)

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.closed = True


def _restore_fixture():
    originals = {
        255: _restore_skill_state(
            255,
            description="original date description",
            prompt=f"{sync.DATE_SKILL_MARKER}\noriginal date prompt",
        ),
        257: _restore_skill_state(
            257,
            description="original payment description",
            prompt=f"{sync.SERVERPAYLOG_SKILL_MARKER}\noriginal payment prompt",
        ),
    }
    published = {
        255: {
            **originals[255],
            "description": seed.DATE_PARTITION_SKILL_DESCRIPTION,
            "prompt": f"{sync.DATE_SKILL_MARKER}\npublished date prompt",
        },
        257: {
            **originals[257],
            "prompt": f"{sync.SERVERPAYLOG_SKILL_MARKER}\npublished payment prompt",
        },
    }
    backup = {"skills": list(originals.values()), "preferences": []}
    return originals, published, backup


def _restore_updates(connection: RestoreConnection):
    return [
        execution
        for execution in connection.executions
        if "UPDATE custom_prompt SET" in execution[0]
    ]


def test_replace_managed_section_is_idempotent_and_paired() -> None:
    original = "header\nbody"
    once = sync.replace_managed_section(original, sync.DATE_SECTION_MARKER, "date-content")
    twice = sync.replace_managed_section(once, sync.DATE_SECTION_MARKER, "date-content")

    assert once == twice
    assert once.count(sync.DATE_SECTION_MARKER) == 1
    assert once.count(sync.managed_section_end_marker(sync.DATE_SECTION_MARKER)) == 1


def test_replace_managed_section_rejects_unpaired_markers() -> None:
    broken = f"header\n{sync.DATE_SECTION_MARKER}\nold content"

    with pytest.raises(ValueError, match="托管段 marker 必须成对"):
        sync.replace_managed_section(broken, sync.DATE_SECTION_MARKER, "date-content")


def test_build_target_prompts_only_changes_two_markers() -> None:
    current = {
        sync.DATE_SKILL_MARKER: "date prompt",
        sync.SERVERPAYLOG_SKILL_MARKER: "payment prompt",
    }
    updated = sync.build_target_prompts(current)

    assert set(updated) == {sync.DATE_SKILL_MARKER, sync.SERVERPAYLOG_SKILL_MARKER}
    assert "day_offsets" in updated[sync.DATE_SKILL_MARKER]
    assert "修复示例：按渠道付费用户" in updated[sync.SERVERPAYLOG_SKILL_MARKER]


def test_build_target_prompts_keeps_canonical_seed_prompts_byte_identical() -> None:
    current = _canonical_target_prompts()

    updated = sync.build_target_prompts(current)

    assert updated == current
    assert updated[sync.DATE_SKILL_MARKER].count("固定 0-14 日日期骨架") == 1
    assert updated[sync.SERVERPAYLOG_SKILL_MARKER].count("修复示例：按渠道付费用户") == 1


def test_build_target_descriptions_only_changes_date_skill() -> None:
    current = {
        sync.DATE_SKILL_MARKER: "old date description",
        sync.SERVERPAYLOG_SKILL_MARKER: "keep payment description",
    }

    updated = sync.build_target_descriptions(current)

    assert updated == {
        sync.DATE_SKILL_MARKER: seed.DATE_PARTITION_SKILL_DESCRIPTION,
        sync.SERVERPAYLOG_SKILL_MARKER: "keep payment description",
    }


def test_sync_target_skills_dry_run_only_backs_up_and_validates() -> None:
    backend = FakeBackend()

    report = sync.sync_target_skills(backend, apply=False)

    assert report.mode == "dry-run"
    assert report.target_skill_count == 2
    assert report.updated is False
    assert len(report.prompt_checks) == 2
    assert all(check.desired_hash and check.desired_length > 0 for check in report.prompt_checks)
    assert backend.events == ["load:False", "load-other", "backup"]


def test_sync_target_skills_apply_uses_lock_cas_embeddings_and_retrieval() -> None:
    backend = FakeBackend()

    report = sync.sync_target_skills(backend, apply=True)

    assert report.updated is True
    assert report.embedding_verified is True
    assert report.retrieval_verified is True
    assert backend.events == [
        "load:False", "load-other", "lock", "load:True", "backup", "cas-update",
        "embeddings:255,202", "verify-targets", "verify-other",
        f"retrieve:{sync.DATE_RETRIEVAL_QUESTION}",
        f"retrieve:{sync.SERVERPAYLOG_RETRIEVAL_QUESTION}", "unlock",
    ]


def test_sync_target_skills_rejects_prompt_hash_change_before_cas() -> None:
    backend = FakeBackend()
    backend.locked_targets = _targets(date_prompt="concurrent change")

    with pytest.raises(sync.TargetSkillChangedError, match="prompt hash"):
        sync.sync_target_skills(backend, apply=True)

    assert "cas-update" not in backend.events
    assert "restore" not in backend.events
    assert backend.events[-1] == "unlock"


def test_sync_target_skills_rejects_description_hash_change_before_cas() -> None:
    backend = FakeBackend()
    backend.locked_targets = _targets(date_description="concurrent change")

    with pytest.raises(sync.TargetSkillChangedError, match="description hash"):
        sync.sync_target_skills(backend, apply=True)

    assert "cas-update" not in backend.events
    assert "restore" not in backend.events
    assert backend.events[-1] == "unlock"


def test_sync_target_skills_restores_both_records_after_verification_failure() -> None:
    backend = FakeBackend()
    backend.fail_retrieval = True

    with pytest.raises(sync.RetrievalVerificationError):
        sync.sync_target_skills(backend, apply=True)

    assert "cas-update" in backend.events
    assert backend.events[-2:] == ["restore", "unlock"]

def test_sync_target_skills_rejects_backup_prompt_hash_mismatch_before_cas() -> None:
    backend = FakeBackend()
    backend.backup_targets = _targets(
        date_prompt=f"{sync.DATE_SKILL_MARKER}\nABA changed prompt"
    )

    with pytest.raises(sync.TargetSkillChangedError, match="恢复备份.*prompt hash"):
        sync.sync_target_skills(backend, apply=True)

    assert "cas-update" not in backend.events
    assert "restore" not in backend.events
    assert backend.events[-1] == "unlock"


def test_sync_target_skills_rejects_backup_description_hash_mismatch_before_cas() -> None:
    backend = FakeBackend()
    backend.backup_targets = _targets(date_description="ABA changed description")

    with pytest.raises(sync.TargetSkillChangedError, match="恢复备份.*description hash"):
        sync.sync_target_skills(backend, apply=True)

    assert "cas-update" not in backend.events
    assert "restore" not in backend.events
    assert backend.events[-1] == "unlock"


def test_psycopg_backend_loads_name_and_description() -> None:
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params) -> None:
            self.query = str(query)
            self.params = params

        @staticmethod
        def fetchall():
            return [
                (
                    255,
                    "修仙业务日期与按日聚合口径",
                    "date description",
                    f"{sync.DATE_SKILL_MARKER}\ndate prompt",
                ),
                (
                    202,
                    "修仙 ServerPayLog 收入与 ARPU/ARPPU",
                    "payment description",
                    f"{sync.SERVERPAYLOG_SKILL_MARKER}\npayment prompt",
                ),
            ]

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_value = FakeCursor()

        def cursor(self):
            return self.cursor_value

    connection = FakeConnection()

    targets = sync.PsycopgBackend._load_targets_on(connection, for_update=False)

    assert "SELECT id, name, description, prompt" in connection.cursor_value.query
    assert targets[sync.DATE_SKILL_MARKER].name == "修仙业务日期与按日聚合口径"
    assert targets[sync.DATE_SKILL_MARKER].description == "date description"


def test_psycopg_backend_cas_and_verify_cover_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCursor:
        def __init__(self) -> None:
            self.executions: list[tuple[str, tuple[object, ...]]] = []
            self.rowcount = 1
            self.rows: list[tuple[object, ...]] = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params=()) -> None:
            self.executions.append((str(query), tuple(params)))

        def fetchall(self):
            return list(self.rows)

    class FakeConnection:
        def __init__(self) -> None:
            self.cursors: list[FakeCursor] = []

        def cursor(self):
            cursor = FakeCursor()
            self.cursors.append(cursor)
            return cursor

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

    backend = sync.PsycopgBackend()
    connection = FakeConnection()
    backend._write_connection = connection
    backend._backup = {"skills": []}
    targets = _targets()
    descriptions = sync.build_target_descriptions(
        {marker: target.description for marker, target in targets.items()}
    )
    prompts = sync.build_target_prompts(
        {marker: target.prompt for marker, target in targets.items()}
    )
    monkeypatch.setattr(
        sync,
        "load_skill_states_by_ids",
        lambda _cursor, ids: {int(skill_id): {"id": int(skill_id)} for skill_id in ids},
    )

    updated_ids = backend.cas_update(targets, descriptions, prompts)

    assert updated_ids == [255, 202]
    update_executions = [
        execution
        for cursor in connection.cursors
        for execution in cursor.executions
        if "UPDATE custom_prompt" in execution[0]
    ]
    assert len(update_executions) == 2
    assert "SET description = %s" in update_executions[0][0]
    assert "SET description = %s" not in update_executions[1][0]
    assert all(
        "description IS NOT DISTINCT FROM %s" in query
        for query, _params in update_executions
    )
    assert update_executions[0][1][0] == seed.DATE_PARTITION_SKILL_DESCRIPTION
    assert update_executions[0][1][-2] == targets[sync.DATE_SKILL_MARKER].description
    assert update_executions[1][1][0] == prompts[sync.SERVERPAYLOG_SKILL_MARKER]

    loaded = {
        marker: sync.TargetSkill(
            id=target.id,
            marker=marker,
            name=target.name,
            description=descriptions[marker],
            prompt=prompts[marker],
        )
        for marker, target in targets.items()
    }
    monkeypatch.setattr(backend, "_load_targets_on", lambda *_args, **_kwargs: loaded)
    verify_cursor = FakeCursor()
    verify_cursor.rows = [
        (
            loaded[marker].id,
            loaded[marker].name,
            loaded[marker].description,
            loaded[marker].prompt,
        )
        for marker in sync.TARGET_SKILL_MARKERS
    ]
    connection.cursor = lambda: verify_cursor
    monkeypatch.setattr(sync, "verify_embeddings", lambda *_args, **_kwargs: None)

    backend.verify_targets(descriptions, prompts, updated_ids)

    assert "SELECT id, name, description, prompt" in verify_cursor.executions[0][0]


def test_seed_restore_skills_restores_original_description_and_prompt() -> None:
    originals, published, backup = _restore_fixture()
    connection = RestoreConnection({skill_id: dict(row) for skill_id, row in published.items()})

    with connection.cursor() as cursor:
        seed.restore_skills(
            cursor,
            backup,
            affected_ids=sorted(originals),
            expected_states=published,
        )

    updates = _restore_updates(connection)
    assert len(updates) == 2
    description_index = seed._RESTORE_SKILL_COLUMNS.index("description")
    prompt_index = seed._RESTORE_SKILL_COLUMNS.index("prompt")
    updates_by_id = {int(params[-2]): (query, params) for query, params in updates}
    for skill_id, original in originals.items():
        query, params = updates_by_id[skill_id]
        assert "description = %s" in query
        assert "prompt = %s" in query
        assert params[description_index] == original["description"]
        assert params[prompt_index] == original["prompt"]


def test_psycopg_backend_restore_noops_when_current_matches_backup() -> None:
    originals, published, backup = _restore_fixture()
    connection = RestoreConnection({skill_id: dict(row) for skill_id, row in originals.items()})
    backend = sync.PsycopgBackend()
    backend._write_connection = connection
    backend._backup = backup
    backend._expected_states = published

    backend.restore()

    assert _restore_updates(connection) == []
    assert connection.rollback_calls == 1
    assert connection.commit_calls == 1


def test_psycopg_backend_restore_rejects_description_conflict() -> None:
    originals, published, backup = _restore_fixture()
    current = {skill_id: dict(row) for skill_id, row in published.items()}
    current[255]["description"] = "concurrent description"
    connection = RestoreConnection(current)
    backend = sync.PsycopgBackend()
    backend._write_connection = connection
    backend._backup = backup
    backend._expected_states = published

    with pytest.raises(seed.SkillRestoreConflictError, match="恢复冲突"):
        backend.restore()

    assert _restore_updates(connection) == []
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 2


def test_sync_target_skills_restores_after_successful_write_when_unlock_fails() -> None:
    backend = FakeBackend()
    backend.fail_unlock = True

    with pytest.raises(RuntimeError, match="unlock failed"):
        sync.sync_target_skills(backend, apply=True)

    assert backend.events[-2:] == ["unlock", "restore"]

def test_sync_target_skills_restores_when_cas_committed_then_raised() -> None:
    backend = FakeBackend()
    backend.cas_failure_mode = "after-write"

    with pytest.raises(RuntimeError, match="cas failed after commit"):
        sync.sync_target_skills(backend, apply=True)

    assert backend.restore_outcome == "restored"
    assert backend.events[-2:] == ["restore", "unlock"]


def test_sync_target_skills_reconciles_noop_when_cas_failed_before_write() -> None:
    backend = FakeBackend()
    backend.cas_failure_mode = "before-write"

    with pytest.raises(RuntimeError, match="cas failed before write"):
        sync.sync_target_skills(backend, apply=True)

    assert backend.restore_outcome == "no-op"
    assert backend.events[-2:] == ["restore", "unlock"]


def test_sync_target_skills_does_not_unlock_when_lock_acquisition_fails() -> None:
    backend = FakeBackend()
    backend.fail_lock = True

    with pytest.raises(RuntimeError, match="lock failed"):
        sync.sync_target_skills(backend, apply=True)

    assert backend.events[-1] == "lock"
    assert "unlock" not in backend.events


def test_psycopg_backend_lock_failure_closes_connection_and_can_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeConnection:
        def __init__(self) -> None:
            self.closed = False
            self.rollback_calls = 0

        def cursor(self):
            return FakeCursor()

        def rollback(self) -> None:
            self.rollback_calls += 1

        def close(self) -> None:
            self.closed = True

    failed_connection = FakeConnection()
    retry_connection = FakeConnection()
    connections = iter((failed_connection, retry_connection))
    backend = sync.PsycopgBackend()
    monkeypatch.setattr(backend, "_connection", lambda: next(connections))
    attempts = 0

    def acquire(_cursor) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("advisory lock failed")

    monkeypatch.setattr(sync, "_acquire_publish_lock", acquire)
    monkeypatch.setattr(sync, "_release_publish_lock", lambda _cursor: None)

    with pytest.raises(RuntimeError, match="advisory lock failed"):
        backend.lock()

    assert failed_connection.rollback_calls == 1
    assert failed_connection.closed is True
    assert backend._write_connection is None

    backend.lock()
    assert backend._write_connection is retry_connection
    backend.unlock()
    assert retry_connection.closed is True
