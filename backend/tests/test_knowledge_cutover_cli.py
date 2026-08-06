"""Verify safe command-line behavior for knowledge cutover."""

from __future__ import annotations

import json

from sqlalchemy.exc import ProgrammingError

from apps.knowledge_base.cutover_cli import main
from apps.knowledge_base.cutover_readiness import CutoverReadinessReport


class _Session:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def rollback(self) -> None:
        return None


class _Service:
    def __init__(self, report: CutoverReadinessReport) -> None:
        self.report = report

    def status(self) -> CutoverReadinessReport:
        return self.report

    def verify(self) -> CutoverReadinessReport:
        return self.report

    def enter_barrier(self) -> CutoverReadinessReport:
        return self.report


class _MissingSchemaService(_Service):
    def status(self) -> CutoverReadinessReport:
        raise ProgrammingError("select", {}, Exception("missing table"))


def _report(ready: bool) -> CutoverReadinessReport:
    return CutoverReadinessReport(
        phase="LEGACY_OPEN",
        revision=0,
        ready_for_cutover=ready,
        legacy_backfill_remaining=0 if ready else 2,
        parity_mismatch_count=0,
        mismatch_ids=(),
        pending_index_count=0,
        pending_projection_count=0,
        active_publish_job_count=0,
        overdue_publish_job_count=0,
        storage_probe_ready=ready,
        compatible_builds_confirmed=ready,
        expected_worker_count=1 if ready else 0,
        code="READY" if ready else "KNOWLEDGE_CUTOVER_NOT_READY",
        message="知识库已满足切换条件。" if ready else "仍有 2 条旧知识未完成 V2 回填。",
    )


def _factory(report: CutoverReadinessReport):
    return lambda *_args, **_kwargs: _Service(report)


def test_verify_returns_nonzero_and_chinese_report_when_not_ready(capsys) -> None:
    result = main(
        ["verify"],
        service_factory=_factory(_report(False)),
        session_factory=_Session,
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["ready_for_cutover"] is False
    assert "未完成 V2 回填" in payload["message"]


def test_mutation_requires_expected_phase_confirmation(capsys) -> None:
    result = main(
        ["enter-barrier"],
        service_factory=_factory(_report(True)),
        session_factory=_Session,
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["code"] == "KNOWLEDGE_CUTOVER_ARGUMENT_INVALID"
    assert payload["message"].endswith("--confirm-phase LEGACY_OPEN。")


def test_enter_barrier_accepts_explicit_worker_and_phase(capsys) -> None:
    captured = {}

    def factory(_session, **kwargs):
        captured.update(kwargs)
        return _Service(_report(True))

    result = main(
        [
            "enter-barrier",
            "--worker",
            "worker-1@local-test",
            "--compatible-builds-confirmed",
            "--confirm-phase",
            "LEGACY_OPEN",
        ],
        service_factory=factory,
        session_factory=_Session,
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["ready_for_cutover"] is True
    assert captured["active_consumers"] == (("worker-1", "local-test"),)
    assert captured["compatible_builds_confirmed"] is True


def test_invalid_worker_format_returns_safe_chinese_error(capsys) -> None:
    result = main(
        ["status", "--worker", "worker-without-queue"],
        service_factory=_factory(_report(True)),
        session_factory=_Session,
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload == {
        "ok": False,
        "code": "KNOWLEDGE_CUTOVER_ARGUMENT_INVALID",
        "message": "Worker 参数格式必须为 WORKER_ID@QUEUE。",
    }


def test_missing_migration_schema_returns_specific_chinese_error(capsys) -> None:
    result = main(
        ["status"],
        service_factory=lambda *_args, **_kwargs: _MissingSchemaService(_report(False)),
        session_factory=_Session,
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload == {
        "ok": False,
        "code": "KNOWLEDGE_MIGRATION_SCHEMA_MISSING",
        "message": "数据库尚未执行知识库 V2 结构迁移，请先核对 Alembic 版本并完成备份。",
    }
