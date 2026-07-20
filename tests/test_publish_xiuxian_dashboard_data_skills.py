from __future__ import annotations

import importlib
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

publisher = importlib.import_module("publish_xiuxian_dashboard_data_skills")
repair = importlib.import_module("xiuxian_dashboard_sql_repair")


def test_expected_repair_count_tracks_audited_catalog():
    assert publisher.EXPECTED_REPAIR_COUNT == len(repair.REPAIR_SPECS) == 10


class Connection:
    def __init__(self, name: str, calls: list[str]):
        self.name = name
        self.calls = calls
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def cursor(self):
        class Cursor:
            def execute(self, _sql, _params=None):
                pass

            def fetchall(self):
                return []

            def close(self):
                pass

        return Cursor()


class EquivalenceCursor:
    def execute(self, _sql: str) -> None:
        pass

    def fetchone(self):
        return (date(2026, 7, 16),)

    def close(self) -> None:
        pass


class EquivalenceConnection:
    def cursor(self):
        return EquivalenceCursor()


def _validate_one_repair(monkeypatch, original_result, rewritten_result):
    view_id = "view-with-order-ties"
    dashboard = SimpleNamespace(
        drawers=[
            SimpleNamespace(
                view_id=view_id,
                sql=(
                    "SELECT cohort_dt, amount, channel FROM metrics "
                    "ORDER BY cohort_dt DESC, amount DESC"
                ),
            )
        ]
    )
    results = iter((original_result, rewritten_result))
    monkeypatch.setattr(publisher, "REPAIR_SPECS", {view_id: object()})
    monkeypatch.setattr(publisher, "EXPECTED_REPAIR_COUNT", 1)
    monkeypatch.setattr(
        publisher,
        "rewrite_bounds_sql",
        lambda requested_view_id, sql: sql.replace("metrics", "rewritten_metrics"),
    )
    monkeypatch.setattr(publisher, "execute_query", lambda cursor, sql: next(results))

    return publisher.validate_all_repairs([dashboard], EquivalenceConnection())


def test_validate_all_repairs_accepts_only_order_tie_reordering(monkeypatch):
    columns = ("cohort_dt", "amount", "channel")
    original = repair.QueryResult(
        columns,
        (
            (date(2026, 7, 15), 100, "Organic"),
            (date(2026, 7, 15), 100, "Unknown"),
            (date(2026, 7, 14), 80, "Paid"),
        ),
    )
    rewritten = repair.QueryResult(
        columns,
        (
            (date(2026, 7, 15), 100, "Unknown"),
            (date(2026, 7, 15), 100, "Organic"),
            (date(2026, 7, 14), 80, "Paid"),
        ),
    )

    repairs = _validate_one_repair(monkeypatch, original, rewritten)

    assert set(repairs) == {"view-with-order-ties"}


@pytest.mark.parametrize(
    ("original", "rewritten"),
    [
        (
            repair.QueryResult(("x",), ((1,), (2,))),
            repair.QueryResult(("x",), ((1,), (3,))),
        ),
        (
            repair.QueryResult(("x",), ((1,), (1,), (2,))),
            repair.QueryResult(("x",), ((1,), (2,), (2,))),
        ),
        (
            repair.QueryResult(("x",), ((1,),)),
            repair.QueryResult(("y",), ((1,),)),
        ),
        (
            repair.QueryResult(("x",), ((1,),)),
            repair.QueryResult(("x",), ((1,), (1,))),
        ),
    ],
    ids=("value", "duplicate-count", "columns", "row-count"),
)
def test_validate_all_repairs_rejects_real_result_mismatches(
    monkeypatch, original, rewritten
):
    with pytest.raises(publisher.ResultMismatchError):
        _validate_one_repair(monkeypatch, original, rewritten)


def _install_read_phases(monkeypatch, calls, *, repairs=None, skills=None):
    repair_count = publisher.EXPECTED_REPAIR_COUNT
    repairs = repairs or {
        f"view-{index}": f"SELECT {index}" for index in range(repair_count)
    }
    skills = skills or [
        {"name": f"Skill {index}", "description": "", "prompt": f"marker-{index}"}
        for index in range(13)
    ]
    dashboards = [object()]
    backup_path = Path("backup/20260716-120000")

    def load(connection):
        calls.append("load")
        return dashboards

    def backup(rows, backup_root, timestamp):
        assert rows is dashboards
        calls.append("backup")
        return backup_path

    def verify(path):
        assert path == backup_path
        calls.append("verify_backup")
        return object()

    def compare(rows, connection):
        assert rows is dashboards
        calls.append(f"{repair_count}_equivalence")
        return repairs

    def explain(rewritten, connection):
        assert rewritten is repairs
        calls.append(f"{repair_count}_explain")

    def in_memory(rows, rewritten):
        assert rows is dashboards
        assert rewritten is repairs
        calls.append("in_memory")
        return ["repaired-dashboard"]

    def build(rows):
        assert rows == ["repaired-dashboard"]
        calls.append("build_skills")
        return skills

    monkeypatch.setattr(publisher, "load_recommended_dashboards", load)
    monkeypatch.setattr(publisher, "write_verified_backup", backup)
    monkeypatch.setattr(publisher, "verify_backup", verify)
    monkeypatch.setattr(publisher, "validate_all_repairs", compare)
    monkeypatch.setattr(publisher, "validate_all_plans", explain)
    monkeypatch.setattr(publisher, "apply_repairs_in_memory", in_memory)
    monkeypatch.setattr(publisher, "build_data_skills", build)
    monkeypatch.setattr(publisher, "validate_skill_preflight", lambda *_args: None)
    monkeypatch.setattr(publisher, "validate_published_skill_set", lambda *_args: None)
    monkeypatch.setattr(publisher, "utc_timestamp", lambda: "20260716-120000")
    return dashboards, repairs, skills, backup_path


def test_dry_run_is_default_and_reaches_in_memory_skills_without_system_writes(
    monkeypatch, tmp_path
):
    calls: list[str] = []
    system = Connection("system-read", calls)
    datasource = Connection("datasource", calls)
    _, _, skills, backup_path = _install_read_phases(monkeypatch, calls)

    for name in (
        "apply_dashboard_repairs",
        "backup_and_write_skill_snapshot",
        "upsert_and_commit_skills",
        "refresh_and_verify_embeddings",
        "verify_retrieval",
    ):
        monkeypatch.setattr(
            publisher,
            name,
            lambda *args, _name=name, **kwargs: calls.append(_name),
        )

    report = publisher.run_publish(
        backup_root=tmp_path,
        system_connection_factory=lambda: system,
        datasource_connection_factory=lambda: datasource,
    )

    assert calls[:7] == [
        "load",
        "backup",
        "verify_backup",
        f"{publisher.EXPECTED_REPAIR_COUNT}_equivalence",
        f"{publisher.EXPECTED_REPAIR_COUNT}_explain",
        "in_memory",
        "build_skills",
    ]
    assert not any(
        name in calls
        for name in (
            "apply_dashboard_repairs",
            "backup_and_write_skill_snapshot",
            "upsert_and_commit_skills",
            "refresh_and_verify_embeddings",
            "verify_retrieval",
        )
    )
    assert report.mode == "dry-run"
    assert report.phase is publisher.PublishPhase.SKILLS_BUILT
    assert report.backup_path == backup_path
    assert report.repaired_view_count == publisher.EXPECTED_REPAIR_COUNT
    assert report.skill_count == len(skills)


def test_apply_stops_before_writes_when_one_result_differs(monkeypatch, tmp_path):
    calls: list[str] = []
    system = Connection("system-read", calls)
    datasource = Connection("datasource", calls)
    _install_read_phases(monkeypatch, calls)

    def mismatch(*_args):
        calls.append(f"{publisher.EXPECTED_REPAIR_COUNT}_equivalence")
        raise publisher.ResultMismatchError(
            "view=95d8497afac14f0a90342031fb43bc04 field=累计付费率"
        )

    monkeypatch.setattr(publisher, "validate_all_repairs", mismatch)
    monkeypatch.setattr(
        publisher,
        "apply_dashboard_repairs",
        lambda *_args, **_kwargs: calls.append("apply_dashboards"),
    )

    with pytest.raises(publisher.ResultMismatchError, match="累计付费率"):
        publisher.run_publish(
            mode="apply",
            backup_root=tmp_path,
            system_connection_factory=lambda: system,
            datasource_connection_factory=lambda: datasource,
            embedding_refresher=lambda _ids: 0,
            retrieval_checker=lambda _question: "",
        )

    assert calls[:4] == [
        "load",
        "backup",
        "verify_backup",
        f"{publisher.EXPECTED_REPAIR_COUNT}_equivalence",
    ]
    assert "apply_dashboards" not in calls


def test_apply_restores_skills_and_releases_lock_when_retrieval_fails(
    monkeypatch, tmp_path
):
    calls: list[str] = []
    read_connection = Connection("system-read", calls)
    apply_connection = Connection("system-apply", calls)
    recovery_connection = Connection("system-recovery", calls)
    datasource = Connection("datasource", calls)
    factory_connections = iter(
        (read_connection, apply_connection, recovery_connection)
    )
    dashboards, repairs, skills, backup_path = _install_read_phases(monkeypatch, calls)
    skill_backup = {"skills": [{"id": 7}], "preferences": []}
    ids = list(range(100, 113))
    update_times: list[int] = []

    monkeypatch.setattr(publisher.time, "time", lambda: 1784175253.987)
    monkeypatch.setattr(
        publisher,
        "acquire_publish_lock",
        lambda connection: calls.append(f"lock:{connection.name}"),
    )
    monkeypatch.setattr(
        publisher,
        "release_publish_lock",
        lambda connection: calls.append(f"unlock:{connection.name}"),
    )

    def apply_dashboards(connection, rows, rewritten, **kwargs):
        update_times.append(kwargs["update_time"])
        calls.append("apply_dashboards")
        return 4

    monkeypatch.setattr(publisher, "apply_dashboard_repairs", apply_dashboards)
    monkeypatch.setattr(
        publisher,
        "backup_and_write_skill_snapshot",
        lambda connection, generated, path: (
            calls.append("backup_skills") or skill_backup
        ),
    )
    monkeypatch.setattr(
        publisher,
        "verify_skill_backup",
        lambda path: calls.append("verify_skills") or skill_backup,
    )
    def upsert(connection, generated, *, expected_states):
        expected_states.update(
            {
                skill_id: {"id": skill_id, "tenant_id": publisher.TENANT_ID}
                for skill_id in ids
            }
        )
        calls.append("upsert_skills")
        return ids

    monkeypatch.setattr(publisher, "upsert_and_commit_skills", upsert)
    monkeypatch.setattr(
        publisher,
        "refresh_and_verify_embeddings",
        lambda connection, affected, refresher, model_factory=None: calls.append(
            "embeddings"
        ),
    )

    def fail_retrieval(checker):
        calls.append("retrieval")
        raise publisher.RetrievalSmokeError("未召回修仙英雄养成")

    monkeypatch.setattr(publisher, "verify_retrieval", fail_retrieval)
    monkeypatch.setattr(
        publisher,
        "restore_published_skills",
        lambda connection, backup, markers, **_kwargs: calls.append(
            f"restore_skills:{connection.name}"
        ),
    )

    with pytest.raises(publisher.RetrievalSmokeError, match="英雄养成"):
        publisher.run_publish(
            mode="apply",
            backup_root=tmp_path,
            system_connection_factory=lambda: next(factory_connections),
            datasource_connection_factory=lambda: datasource,
            embedding_refresher=lambda affected: len(affected),
            retrieval_checker=lambda question: question,
        )

    assert calls.index("lock:system-apply") < calls.index("apply_dashboards")
    assert calls.index("apply_dashboards") < calls.index("backup_skills")
    assert calls.index("backup_skills") < calls.index("verify_skills")
    assert calls.index("verify_skills") < calls.index("upsert_skills")
    assert calls.index("upsert_skills") < calls.index("embeddings")
    assert calls.index("embeddings") < calls.index("retrieval")
    assert calls.index("retrieval") < calls.index(
        "restore_skills:system-recovery"
    )
    assert calls.index("restore_skills:system-recovery") < calls.index(
        "unlock:system-apply"
    )
    assert "lock:system-recovery" not in calls
    assert backup_path == Path("backup/20260716-120000")
    assert len(repairs) == publisher.EXPECTED_REPAIR_COUNT
    assert type(update_times[0]) is int
    assert update_times == [1784175253]
    assert len(skills) == 13


def test_commit_uncertainty_restores_by_markers_on_a_new_connection(
    monkeypatch, tmp_path
):
    calls: list[str] = []
    read_connection = Connection("system-read", calls)
    apply_connection = Connection("system-apply", calls)
    recovery_connection = Connection("system-recovery", calls)
    datasource = Connection("datasource", calls)
    factory_connections = iter(
        (read_connection, apply_connection, recovery_connection)
    )
    _dashboards, _repairs, skills, _backup_path = _install_read_phases(
        monkeypatch, calls
    )
    skill_backup = {"skills": [{"id": 7}], "preferences": []}

    monkeypatch.setattr(
        publisher,
        "acquire_publish_lock",
        lambda connection: calls.append(f"lock:{connection.name}"),
    )
    monkeypatch.setattr(
        publisher,
        "release_publish_lock",
        lambda connection: calls.append(f"unlock:{connection.name}"),
    )
    monkeypatch.setattr(
        publisher,
        "apply_dashboard_repairs",
        lambda *_args, **_kwargs: calls.append("apply_dashboards") or 4,
    )
    monkeypatch.setattr(
        publisher,
        "backup_and_write_skill_snapshot",
        lambda *_args: calls.append("backup_skills") or skill_backup,
    )
    monkeypatch.setattr(
        publisher,
        "verify_skill_backup",
        lambda _path: calls.append("verify_skills") or skill_backup,
    )

    expected_after_upsert = {
        index: {"id": index, "tenant_id": publisher.TENANT_ID}
        for index in range(100, 113)
    }

    def uncertain_commit(*_args, expected_states):
        expected_states.update(expected_after_upsert)
        calls.append("server_persisted_skills")
        raise OSError("commit acknowledgement lost")

    monkeypatch.setattr(publisher, "upsert_and_commit_skills", uncertain_commit)
    restored = []
    monkeypatch.setattr(
        publisher,
        "restore_published_skills",
        lambda connection, backup, markers, **kwargs: restored.append(
            (connection.name, backup, tuple(markers), kwargs["expected_states"])
        ),
    )

    with pytest.raises(OSError, match="acknowledgement"):
        publisher.run_publish(
            mode="apply",
            backup_root=tmp_path,
            system_connection_factory=lambda: next(factory_connections),
            datasource_connection_factory=lambda: datasource,
            embedding_refresher=lambda affected: len(affected),
            retrieval_checker=lambda question: question,
        )

    assert restored
    connection_name, restored_backup, markers, restored_expected = restored[0]
    assert connection_name == "system-recovery"
    assert restored_backup == skill_backup
    assert set(markers) == set(publisher._skill_markers(skills))
    assert restored_expected == expected_after_upsert
    assert "lock:system-recovery" not in calls
    assert calls.index("server_persisted_skills") < calls.index(
        "unlock:system-apply"
    )


def test_upsert_captures_expected_state_before_uncertain_commit(monkeypatch):
    expected_row = {
        "id": 7,
        "tenant_id": publisher.TENANT_ID,
        "name": "发布名称",
        "embedding": None,
    }
    observed = []

    class Cursor:
        def close(self):
            pass

    class DbConnection:
        def cursor(self):
            return Cursor()

        def commit(self):
            observed.append("commit")
            raise OSError("commit acknowledgement lost")

        def rollback(self):
            observed.append("rollback")

    monkeypatch.setattr(publisher, "upsert_skills", lambda *_args, **_kwargs: [7])
    monkeypatch.setattr(
        publisher, "validate_published_skill_set", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        publisher,
        "load_skill_states_by_ids",
        lambda _cursor, _ids: {7: expected_row},
    )
    expected_states = {}

    with pytest.raises(OSError, match="acknowledgement"):
        publisher.upsert_and_commit_skills(
            DbConnection(),
            [{"name": "发布名称", "description": "", "prompt": "marker"}],
            expected_states=expected_states,
        )

    assert expected_states == {7: expected_row}
    assert observed == ["commit", "rollback"]


def test_broken_publish_session_reacquires_lock_on_recovery_connection(
    monkeypatch, tmp_path
):
    calls: list[str] = []
    read_connection = Connection("system-read", calls)
    apply_connection = Connection("system-apply", calls)
    recovery_connection = Connection("system-recovery", calls)
    datasource = Connection("datasource", calls)
    factory_connections = iter(
        (read_connection, apply_connection, recovery_connection)
    )
    _install_read_phases(monkeypatch, calls)
    skill_backup = {"skills": [], "preferences": []}

    monkeypatch.setattr(
        publisher,
        "acquire_publish_lock",
        lambda connection: calls.append(f"lock:{connection.name}"),
    )
    monkeypatch.setattr(
        publisher,
        "release_publish_lock",
        lambda connection: calls.append(f"unlock:{connection.name}"),
    )
    monkeypatch.setattr(
        publisher,
        "apply_dashboard_repairs",
        lambda *_args, **_kwargs: 4,
    )
    monkeypatch.setattr(
        publisher,
        "backup_and_write_skill_snapshot",
        lambda *_args: skill_backup,
    )
    monkeypatch.setattr(
        publisher,
        "verify_skill_backup",
        lambda _path: skill_backup,
    )

    def fail_on_broken_connection(*_args, expected_states):
        expected_states.update(
            {
                index: {"id": index, "tenant_id": publisher.TENANT_ID}
                for index in range(100, 113)
            }
        )
        apply_connection.closed = True
        raise OSError("connection lost during commit")

    monkeypatch.setattr(
        publisher, "upsert_and_commit_skills", fail_on_broken_connection
    )
    monkeypatch.setattr(
        publisher,
        "restore_published_skills",
        lambda connection, backup, markers, **_kwargs: calls.append(
            f"restore:{connection.name}"
        ),
    )

    with pytest.raises(OSError, match="connection lost"):
        publisher.run_publish(
            mode="apply",
            backup_root=tmp_path,
            system_connection_factory=lambda: next(factory_connections),
            datasource_connection_factory=lambda: datasource,
        )

    assert calls.index("lock:system-recovery") < calls.index(
        "restore:system-recovery"
    )
    assert calls.index("restore:system-recovery") < calls.index(
        "unlock:system-recovery"
    )
    assert "unlock:system-apply" not in calls


def test_precommit_validation_failure_does_not_start_state_restore(
    monkeypatch, tmp_path
):
    calls: list[str] = []
    read_connection = Connection("system-read", calls)
    apply_connection = Connection("system-apply", calls)
    datasource = Connection("datasource", calls)
    factory_connections = iter((read_connection, apply_connection))
    _install_read_phases(monkeypatch, calls)
    skill_backup = {"skills": [{"id": 7}], "preferences": []}

    monkeypatch.setattr(publisher, "acquire_publish_lock", lambda _connection: None)
    monkeypatch.setattr(publisher, "release_publish_lock", lambda _connection: None)
    monkeypatch.setattr(publisher, "apply_dashboard_repairs", lambda *_args, **_kwargs: 4)
    monkeypatch.setattr(
        publisher, "backup_and_write_skill_snapshot", lambda *_args: skill_backup
    )
    monkeypatch.setattr(publisher, "verify_skill_backup", lambda _path: skill_backup)

    def fail_before_expected_state(*_args, expected_states):
        assert expected_states == {}
        raise RuntimeError("发布后存在第14条 Skill")

    monkeypatch.setattr(
        publisher, "upsert_and_commit_skills", fail_before_expected_state
    )
    monkeypatch.setattr(
        publisher,
        "_restore_with_new_connection",
        lambda *_args, **_kwargs: calls.append("unexpected_restore"),
    )

    with pytest.raises(RuntimeError, match="第14条"):
        publisher.run_publish(
            mode="apply",
            backup_root=tmp_path,
            system_connection_factory=lambda: next(factory_connections),
            datasource_connection_factory=lambda: datasource,
        )

    assert "unexpected_restore" not in calls


@pytest.mark.parametrize("failure_stage", ["commit", "embedding", "retrieval"])
def test_publish_and_cas_recovery_failures_are_both_preserved(
    monkeypatch, tmp_path, failure_stage
):
    calls: list[str] = []
    read_connection = Connection("system-read", calls)
    apply_connection = Connection("system-apply", calls)
    recovery_connection = Connection("system-recovery", calls)
    datasource = Connection("datasource", calls)
    factory_connections = iter(
        (read_connection, apply_connection, recovery_connection)
    )
    _install_read_phases(monkeypatch, calls)
    skill_backup = {"skills": [{"id": 7}], "preferences": []}
    ids = list(range(100, 113))
    publish_error = RuntimeError(f"{failure_stage} publish failed")
    recovery_error = publisher.SkillRestoreConflictError("CAS conflict")
    unlock_error = RuntimeError("unlock failed")

    monkeypatch.setattr(publisher, "acquire_publish_lock", lambda _connection: None)

    def fail_unlock(_connection):
        raise unlock_error

    monkeypatch.setattr(publisher, "release_publish_lock", fail_unlock)
    monkeypatch.setattr(
        publisher, "apply_dashboard_repairs", lambda *_args, **_kwargs: 4
    )
    monkeypatch.setattr(
        publisher, "backup_and_write_skill_snapshot", lambda *_args: skill_backup
    )
    monkeypatch.setattr(publisher, "verify_skill_backup", lambda _path: skill_backup)

    def upsert(*_args, expected_states):
        expected_states.update(
            {
                skill_id: {"id": skill_id, "tenant_id": publisher.TENANT_ID}
                for skill_id in ids
            }
        )
        if failure_stage == "commit":
            raise publish_error
        return ids

    def refresh(*_args, **_kwargs):
        if failure_stage == "embedding":
            raise publish_error

    def retrieve(_checker):
        if failure_stage == "retrieval":
            raise publish_error
        return {}

    monkeypatch.setattr(publisher, "upsert_and_commit_skills", upsert)
    monkeypatch.setattr(publisher, "refresh_and_verify_embeddings", refresh)
    monkeypatch.setattr(publisher, "verify_retrieval", retrieve)
    monkeypatch.setattr(
        publisher,
        "restore_published_skills",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(recovery_error),
    )

    with pytest.raises(publisher.SkillPublishRecoveryError) as exc_info:
        publisher.run_publish(
            mode="apply",
            backup_root=tmp_path,
            system_connection_factory=lambda: next(factory_connections),
            datasource_connection_factory=lambda: datasource,
        )

    assert exc_info.value.publish_error is publish_error
    assert exc_info.value.recovery_error is recovery_error
    assert exc_info.value.unlock_error is unlock_error
    assert str(publish_error) in str(exc_info.value)
    assert str(recovery_error) in str(exc_info.value)


def test_publish_and_recovery_connection_failures_are_both_preserved(
    monkeypatch, tmp_path
):
    calls: list[str] = []
    read_connection = Connection("system-read", calls)
    apply_connection = Connection("system-apply", calls)
    datasource = Connection("datasource", calls)
    factory_calls = 0
    _install_read_phases(monkeypatch, calls)
    skill_backup = {"skills": [], "preferences": []}
    ids = list(range(100, 113))
    publish_error = publisher.RetrievalSmokeError("retrieval failed")
    recovery_error = ConnectionError("recovery connection failed")

    def system_factory():
        nonlocal factory_calls
        factory_calls += 1
        if factory_calls == 1:
            return read_connection
        if factory_calls == 2:
            return apply_connection
        raise recovery_error

    monkeypatch.setattr(publisher, "acquire_publish_lock", lambda _connection: None)
    monkeypatch.setattr(publisher, "release_publish_lock", lambda _connection: None)
    monkeypatch.setattr(
        publisher, "apply_dashboard_repairs", lambda *_args, **_kwargs: 4
    )
    monkeypatch.setattr(
        publisher, "backup_and_write_skill_snapshot", lambda *_args: skill_backup
    )
    monkeypatch.setattr(publisher, "verify_skill_backup", lambda _path: skill_backup)

    def upsert(*_args, expected_states):
        expected_states.update(
            {
                skill_id: {"id": skill_id, "tenant_id": publisher.TENANT_ID}
                for skill_id in ids
            }
        )
        return ids

    monkeypatch.setattr(publisher, "upsert_and_commit_skills", upsert)
    monkeypatch.setattr(
        publisher, "refresh_and_verify_embeddings", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        publisher,
        "verify_retrieval",
        lambda _checker: (_ for _ in ()).throw(publish_error),
    )

    with pytest.raises(publisher.SkillPublishRecoveryError) as exc_info:
        publisher.run_publish(
            mode="apply",
            backup_root=tmp_path,
            system_connection_factory=system_factory,
            datasource_connection_factory=lambda: datasource,
        )

    assert exc_info.value.publish_error is publish_error
    assert exc_info.value.recovery_error is recovery_error


def test_skill_recovery_artifact_is_independent_and_verified(
    monkeypatch, tmp_path
):
    backup_path = tmp_path / "20260716-120000"
    backup_path.mkdir()
    original_file = backup_path / "manifest.json"
    original_file.write_text('{"dashboard":"sealed"}\n', encoding="utf-8")
    original_files = set(backup_path.rglob("*"))
    backup = {
        "skills": [
            {
                "id": 7,
                "tenant_id": publisher.TENANT_ID,
                "datasource_ids": [publisher.DATASOURCE_ID],
                "prompt": "marker-a",
            }
        ],
        "preferences": [],
    }
    monkeypatch.setattr(
        publisher,
        "backup_existing_skills",
        lambda cursor, markers: backup,
    )

    class Cursor:
        def close(self):
            pass

    class DbConnection:
        def cursor(self):
            return Cursor()

    publisher.backup_and_write_skill_snapshot(
        DbConnection(),
        [{"prompt": "marker-a", "name": "Skill", "description": ""}],
        backup_path,
    )

    assert set(backup_path.rglob("*")) == original_files
    recovery_path = publisher.skill_recovery_path(backup_path)
    assert recovery_path.parent == backup_path.parent
    assert {path.name for path in recovery_path.iterdir()} == {
        "skills.json",
        "manifest.json",
    }
    assert publisher.verify_skill_backup(backup_path) == backup

    payload = json.loads((recovery_path / "skills.json").read_text("utf-8"))
    payload["backup"]["skills"][0]["prompt"] = "tampered"
    (recovery_path / "skills.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="哈希"):
        publisher.verify_skill_backup(backup_path)


def test_restore_published_skills_discovers_affected_ids_from_markers(
    monkeypatch,
):
    markers = ["marker-a", "marker-b"]
    backup = {"skills": [{"id": 7}], "preferences": []}
    observed = {}

    class Cursor:
        def close(self):
            pass

    class DbConnection:
        def __init__(self):
            self.committed = False
            self.rollback_count = 0

        def cursor(self):
            return Cursor()

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rollback_count += 1

    def load_current(cursor, requested_markers):
        observed["markers"] = list(requested_markers)
        return {"skills": [{"id": 8}, {"id": 9}], "preferences": []}

    monkeypatch.setattr(publisher, "backup_existing_skills", load_current)

    def restore(cursor, original, *, affected_ids, expected_states):
        observed["backup"] = original
        observed["affected_ids"] = list(affected_ids)
        observed["expected_states"] = expected_states

    monkeypatch.setattr(publisher, "restore_skills", restore)
    connection = DbConnection()

    expected_states = {8: {"id": 8}, 9: {"id": 9}}
    publisher.restore_published_skills(
        connection, backup, markers, expected_states=expected_states
    )

    assert observed == {
        "markers": markers,
        "backup": backup,
        "affected_ids": [8, 9],
        "expected_states": expected_states,
    }
    assert connection.committed is True
    assert connection.rollback_count == 1


def test_restore_skills_preserves_existing_preferences_and_restores_matching_rows():
    backup = {
        "skills": [{"id": 7, "tenant_id": publisher.TENANT_ID, "name": "旧名称"}],
        "preferences": [{"id": 91, "custom_prompt_id": 7, "enabled": True}],
    }
    expected = {7: {"id": 7, "tenant_id": publisher.TENANT_ID, "name": "发布名称"}}

    class Cursor:
        rowcount = 1

        def __init__(self):
            self.statements = []
            self.rows = []

        def execute(self, sql, params=None):
            normalized = " ".join(str(sql).split())
            self.statements.append((normalized, params))
            if "SELECT to_jsonb(cp)" in normalized and "id = ANY" in normalized:
                self.rows = [(dict(expected[7]),)]
            else:
                self.rows = []

        def fetchall(self):
            return self.rows

    cursor = Cursor()
    publisher.restore_skills(
        cursor, backup, affected_ids=[7], expected_states=expected
    )

    sql = "\n".join(statement for statement, _params in cursor.statements)
    assert "UPDATE custom_prompt SET" in sql
    assert "custom_prompt_user_preference" not in sql


def test_restore_skills_reports_concurrent_admin_edit_without_overwriting():
    backup = {"skills": [{"id": 7, "tenant_id": publisher.TENANT_ID, "name": "旧名称"}], "preferences": []}
    expected = {7: {"id": 7, "tenant_id": publisher.TENANT_ID, "name": "发布名称"}}

    class Cursor:
        def __init__(self):
            self.statements = []

        def execute(self, sql, params=None):
            self.statements.append(" ".join(str(sql).split()))

        def fetchall(self):
            return [({"id": 7, "tenant_id": publisher.TENANT_ID, "name": "管理员名称"},)]

    cursor = Cursor()
    with pytest.raises(publisher.SkillRestoreConflictError, match="7"):
        publisher.restore_skills(
            cursor, backup, affected_ids=[7], expected_states=expected
        )
    assert not any(sql.startswith("UPDATE custom_prompt") for sql in cursor.statements)


def test_restore_skills_accepts_already_rolled_back_original_and_missing_new_rows():
    original = {"id": 7, "tenant_id": publisher.TENANT_ID, "name": "旧名称"}
    expected = {
        7: {"id": 7, "tenant_id": publisher.TENANT_ID, "name": "发布名称"},
        8: {"id": 8, "tenant_id": publisher.TENANT_ID, "name": "新增名称"},
    }

    class Cursor:
        def __init__(self):
            self.statements = []

        def execute(self, sql, params=None):
            self.statements.append(" ".join(str(sql).split()))

        def fetchall(self):
            return [(original,)]

    cursor = Cursor()
    publisher.restore_skills(
        cursor,
        {"skills": [original], "preferences": []},
        affected_ids=[7, 8],
        expected_states=expected,
    )

    assert not any(
        sql.startswith(("UPDATE custom_prompt", "DELETE FROM custom_prompt"))
        for sql in cursor.statements
    )


@pytest.mark.parametrize("concurrent_edit", [False, True])
def test_restore_new_skill_deletes_only_when_published_state_still_matches(concurrent_edit):
    expected = {8: {"id": 8, "tenant_id": publisher.TENANT_ID, "name": "发布名称"}}

    class Cursor:
        rowcount = 1

        def __init__(self):
            self.statements = []

        def execute(self, sql, params=None):
            self.statements.append(" ".join(str(sql).split()))

        def fetchall(self):
            row = dict(expected[8])
            if concurrent_edit:
                row["description"] = "管理员修改"
            return [(row,)]

    cursor = Cursor()
    if concurrent_edit:
        with pytest.raises(publisher.SkillRestoreConflictError, match="8"):
            publisher.restore_skills(
                cursor,
                {"skills": [], "preferences": []},
                affected_ids=[8],
                expected_states=expected,
            )
        assert not any(sql.startswith("DELETE FROM custom_prompt ") for sql in cursor.statements)
    else:
        publisher.restore_skills(
            cursor,
            {"skills": [], "preferences": []},
            affected_ids=[8],
            expected_states=expected,
        )
        sql = "\n".join(cursor.statements)
        assert "DELETE FROM custom_prompt_user_preference" in sql
        assert "DELETE FROM custom_prompt" in sql


def test_preflight_rejects_duplicate_current_marker():
    skills = [{"prompt": f"marker-{index}"} for index in range(13)]

    class Cursor:
        def execute(self, _sql, _params=None):
            pass

        def fetchall(self):
            return [(7, "marker-0"), (8, "heading\nmarker-0")]

    with pytest.raises(RuntimeError, match="marker-0.*重复|重复.*marker-0"):
        publisher.validate_skill_preflight(Cursor(), skills)


@pytest.mark.parametrize(
    "extra_prompt",
    [
        "marker-0",
        "<!-- data-skill-source:xiuxian:dashboard:expired-topic -->",
    ],
)
def test_post_publish_requires_exactly_thirteen_unique_target_skills(extra_prompt):
    skills = [
        {"name": f"Skill {index}", "description": "", "prompt": f"marker-{index}"}
        for index in range(13)
    ]
    rows = [
        (
            {
                "id": index + 1,
                "tenant_id": publisher.TENANT_ID,
                "type": "DATA_SKILL",
                "name": f"Skill {index}",
                "description": "",
                "target_scope": "ALL",
                "active": True,
                "visible": True,
                "visibility_scope": "ADMIN_PUBLIC",
                "prompt": f"marker-{index}",
                "specific_ds": True,
                "datasource_ids": [publisher.DATASOURCE_ID],
            },
        )
        for index in range(13)
    ]
    rows.append((dict(rows[0][0], id=99, prompt=extra_prompt),))

    class Cursor:
        def execute(self, _sql, _params=None):
            pass

        def fetchall(self):
            return rows

    with pytest.raises(RuntimeError, match="13|重复|额外"):
        publisher.validate_published_skill_set(Cursor(), skills, list(range(1, 14)))


def test_verify_retrieval_checks_all_five_topics_and_serverpaylog_marker():
    responses = {
        "最近七天新增用户趋势": "修仙新增用户总量与系统归因",
        "最近一个月 DAU WAU MAU": "修仙 DAU、WAU 与 MAU",
        "各渠道新增用户次日留存": "修仙新增 cohort 留存",
        "最近七天收入和 ARPPU": (
            "修仙 ServerPayLog 收入与 ARPU/ARPPU\nServerPayLog"
        ),
        "英雄升级与升星情况": "修仙英雄养成",
    }
    seen: list[str] = []

    def checker(question: str) -> str:
        seen.append(question)
        return responses[question]

    result = publisher.verify_retrieval(checker)

    assert seen == [case.question for case in publisher.RETRIEVAL_SMOKE_CASES]
    assert result == responses


def test_verify_retrieval_rejects_legacy_payment_marker():
    def checker(question: str) -> str:
        expected = next(
            case.expected_skill
            for case in publisher.RETRIEVAL_SMOKE_CASES
            if case.question == question
        )
        suffix = "\nServerPayLog" if "ARPPU" in question else ""
        return expected + suffix + "\npaybuyret-monetization-arppu"

    with pytest.raises(publisher.RetrievalSmokeError, match="旧付费 marker"):
        publisher.verify_retrieval(checker)


def test_cli_defaults_to_dry_run_and_has_no_scope_override_arguments():
    args = publisher.build_parser().parse_args([])
    assert args.mode == "dry-run"

    with pytest.raises(SystemExit):
        publisher.build_parser().parse_args(["--tenant-id", "1"])
    with pytest.raises(SystemExit):
        publisher.build_parser().parse_args(["--datasource-id", "1"])


def test_invalid_mode_is_rejected_before_opening_connections(tmp_path):
    opened = []

    with pytest.raises(ValueError, match="dry-run|apply"):
        publisher.run_publish(
            mode="preview",
            backup_root=tmp_path,
            system_connection_factory=lambda: opened.append("system"),
            datasource_connection_factory=lambda: opened.append("datasource"),
        )

    assert opened == []
