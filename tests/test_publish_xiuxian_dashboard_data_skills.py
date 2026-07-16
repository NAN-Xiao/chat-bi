from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

publisher = importlib.import_module("publish_xiuxian_dashboard_data_skills")


class Connection:
    def __init__(self, name: str, calls: list[str]):
        self.name = name
        self.calls = calls
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _install_read_phases(monkeypatch, calls, *, repairs=None, skills=None):
    repairs = repairs or {f"view-{index}": f"SELECT {index}" for index in range(11)}
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
        calls.append("11_equivalence")
        return repairs

    def explain(rewritten, connection):
        assert rewritten is repairs
        calls.append("11_explain")

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
        "11_equivalence",
        "11_explain",
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
    assert report.repaired_view_count == 11
    assert report.skill_count == len(skills)


def test_apply_stops_before_writes_when_one_result_differs(monkeypatch, tmp_path):
    calls: list[str] = []
    system = Connection("system-read", calls)
    datasource = Connection("datasource", calls)
    _install_read_phases(monkeypatch, calls)

    def mismatch(*_args):
        calls.append("11_equivalence")
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

    assert calls[:4] == ["load", "backup", "verify_backup", "11_equivalence"]
    assert "apply_dashboards" not in calls


def test_apply_restores_skills_and_releases_lock_when_retrieval_fails(
    monkeypatch, tmp_path
):
    calls: list[str] = []
    read_connection = Connection("system-read", calls)
    apply_connection = Connection("system-apply", calls)
    datasource = Connection("datasource", calls)
    factory_connections = iter((read_connection, apply_connection))
    dashboards, repairs, skills, backup_path = _install_read_phases(monkeypatch, calls)
    skill_backup = {"skills": [{"id": 7}], "preferences": []}
    ids = list(range(100, 113))

    monkeypatch.setattr(
        publisher,
        "acquire_publish_lock",
        lambda connection: calls.append("lock"),
    )
    monkeypatch.setattr(
        publisher,
        "release_publish_lock",
        lambda connection: calls.append("unlock"),
    )
    monkeypatch.setattr(
        publisher,
        "apply_dashboard_repairs",
        lambda connection, rows, rewritten, **kwargs: (
            calls.append("apply_dashboards") or 4
        ),
    )
    monkeypatch.setattr(
        publisher,
        "backup_and_write_skill_snapshot",
        lambda connection, generated, path: (
            calls.append("backup_skills") or skill_backup
        ),
    )
    monkeypatch.setattr(
        publisher,
        "upsert_and_commit_skills",
        lambda connection, generated: calls.append("upsert_skills") or ids,
    )
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
        lambda connection, backup, affected: calls.append("restore_skills"),
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

    assert calls.index("lock") < calls.index("apply_dashboards")
    assert calls.index("apply_dashboards") < calls.index("backup_skills")
    assert calls.index("backup_skills") < calls.index("upsert_skills")
    assert calls.index("upsert_skills") < calls.index("embeddings")
    assert calls.index("embeddings") < calls.index("retrieval")
    assert calls.index("retrieval") < calls.index("restore_skills")
    assert calls.index("restore_skills") < calls.index("unlock")
    assert backup_path == Path("backup/20260716-120000")
    assert len(repairs) == 11
    assert len(skills) == 13


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
