"""Verify database-authoritative recovery for knowledge publish jobs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, text, update
from sqlmodel import Session

from apps.knowledge_base import publish_jobs, reconciliation
from apps.knowledge_base.lifecycle_models import KnowledgePublishJob
from common.core.task_queue import EnqueueOutcome, EnqueueResult


@pytest.fixture
def publish_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'publish-recovery.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE knowledge_base_version ("
            "id BIGINT PRIMARY KEY, knowledge_base_id BIGINT NOT NULL, "
            "tenant_id BIGINT NOT NULL, status VARCHAR(32) NOT NULL, "
            "error_message TEXT, publish_time DATETIME)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE knowledge_base ("
            "id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, "
            "current_version_id BIGINT, draft_version_id BIGINT, "
            "publishing_version_id BIGINT, publish_time DATETIME)"
        )
    KnowledgePublishJob.__table__.create(engine)
    yield engine
    engine.dispose()


def _add_job(
    engine,
    *,
    status: str = "QUEUING",
    task_id: str | None = "task-1",
    enqueue_attempts: int = 0,
    max_attempts: int = 3,
    deadline_at: datetime | None = None,
    last_enqueue_at: datetime | None = None,
    heartbeat_at: datetime | None = None,
) -> None:
    now = datetime.utcnow()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO knowledge_base_version "
                "(id, knowledge_base_id, tenant_id, status) "
                "VALUES (1, 1, 7, 'PUBLISHING')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO knowledge_base (id, tenant_id, publishing_version_id) "
                "VALUES (1, 7, 1)"
            )
        )
    with Session(engine) as session:
        session.add(
            KnowledgePublishJob(
                id=1,
                tenant_id=7,
                knowledge_base_id=1,
                version_id=1,
                revision=1,
                content_hash="a" * 64,
                status=status,
                task_id=task_id,
                enqueue_attempts=enqueue_attempts,
                attempt=0,
                max_attempts=max_attempts,
                last_enqueue_at=last_enqueue_at or now - timedelta(minutes=2),
                heartbeat_at=heartbeat_at,
                deadline_at=deadline_at or now + timedelta(minutes=10),
                create_time=now - timedelta(minutes=2),
                update_time=now - timedelta(minutes=2),
            )
        )
        session.commit()


def _reload_job(engine) -> KnowledgePublishJob:
    with Session(engine) as session:
        job = session.get(KnowledgePublishJob, 1)
        assert job is not None
        session.expunge(job)
        return job


def test_unknown_confirmation_keeps_same_task_and_queuing(monkeypatch, publish_engine) -> None:
    _add_job(publish_engine)
    confirmed_ids = []

    async def unknown(task_id, **_kwargs):
        confirmed_ids.append(task_id)
        return EnqueueResult(
            outcome=EnqueueOutcome.UNKNOWN,
            task={"id": task_id, "status": "pending"},
            error_code="TASK_QUEUE_CONFIRMATION_REQUIRED",
        )

    monkeypatch.setattr(reconciliation, "confirm_or_repair_task", unknown)
    with Session(publish_engine) as session:
        summary = asyncio.run(reconciliation.reconcile_publish_jobs(session))

    job = _reload_job(publish_engine)
    assert confirmed_ids == ["task-1"]
    assert job.task_id == "task-1"
    assert job.status == "QUEUING"
    assert job.error_code == "TASK_QUEUE_CONFIRMATION_REQUIRED"
    assert summary["pending_confirmation"] == 1


def test_unknown_confirmation_keeps_queued_status_and_records_error(
    monkeypatch,
    publish_engine,
) -> None:
    _add_job(publish_engine, status="QUEUED")

    async def unknown(task_id, **_kwargs):
        return EnqueueResult(
            outcome=EnqueueOutcome.UNKNOWN,
            task={"id": task_id, "status": "pending"},
            error_code="TASK_QUEUE_CONFIRMATION_REQUIRED",
        )

    monkeypatch.setattr(reconciliation, "confirm_or_repair_task", unknown)
    with Session(publish_engine) as session:
        summary = asyncio.run(reconciliation.reconcile_publish_jobs(session))

    job = _reload_job(publish_engine)
    assert job.status == "QUEUED"
    assert job.task_id == "task-1"
    assert job.error_code == "TASK_QUEUE_CONFIRMATION_REQUIRED"
    assert summary["pending_confirmation"] == 1


def test_queued_transition_cas_never_moves_running_job_back(monkeypatch, publish_engine) -> None:
    _add_job(publish_engine)

    async def confirmed(task_id, **_kwargs):
        return EnqueueResult(
            outcome=EnqueueOutcome.ENQUEUED,
            task={"id": task_id, "status": "pending"},
        )

    original_mark_queued = publish_jobs.mark_publish_job_queued

    def worker_wins(session, *, job, task_id, now):
        session.exec(
            update(KnowledgePublishJob)
            .where(KnowledgePublishJob.id == job.id)
            .values(status="RUNNING", task_id=task_id, update_time=now)
        )
        session.commit()
        return original_mark_queued(session, job=job, task_id=task_id, now=now)

    monkeypatch.setattr(reconciliation, "confirm_or_repair_task", confirmed)
    monkeypatch.setattr(reconciliation, "mark_publish_job_queued", worker_wins)
    with Session(publish_engine) as session:
        asyncio.run(reconciliation.reconcile_publish_jobs(session))

    assert _reload_job(publish_engine).status == "RUNNING"


def test_timeout_fails_only_after_final_confirmation(monkeypatch, publish_engine) -> None:
    now = datetime.utcnow()
    _add_job(publish_engine, deadline_at=now - timedelta(seconds=1))
    confirmations = 0

    async def still_unknown(task_id, **_kwargs):
        nonlocal confirmations
        confirmations += 1
        return EnqueueResult(
            outcome=EnqueueOutcome.UNKNOWN,
            task={"id": task_id, "status": "pending"},
            error_code="TASK_QUEUE_CONFIRMATION_REQUIRED",
        )

    monkeypatch.setattr(reconciliation, "confirm_or_repair_task", still_unknown)
    with Session(publish_engine) as session:
        summary = asyncio.run(
            reconciliation.reconcile_publish_jobs(session, now=now)
        )

    assert confirmations == 1
    assert _reload_job(publish_engine).status == "FAILED"
    with publish_engine.connect() as connection:
        version = connection.execute(
            text("SELECT status, error_message FROM knowledge_base_version WHERE id = 1")
        ).one()
        knowledge = connection.execute(
            text("SELECT publishing_version_id FROM knowledge_base WHERE id = 1")
        ).one()
    assert version.status == "PUBLISH_FAILED"
    assert version.error_message == "发布任务无法确认，已停止本次发布。"
    assert knowledge.publishing_version_id is None
    assert summary["failed"] == 1


def test_deadline_without_task_id_attempts_final_dedupe_enqueue(
    monkeypatch,
    publish_engine,
) -> None:
    now = datetime.utcnow()
    _add_job(
        publish_engine,
        task_id=None,
        deadline_at=now - timedelta(seconds=1),
    )
    calls = []

    async def unknown(name, payload, **kwargs):
        calls.append(("enqueue", name, payload, kwargs["dedupe_key"]))
        return EnqueueResult(
            outcome=EnqueueOutcome.UNKNOWN,
            task={"id": "task-final", "status": "pending"},
            error_code="TASK_QUEUE_CONFIRMATION_REQUIRED",
        )

    async def still_unknown(task_id, **_kwargs):
        calls.append(("confirm", task_id))
        return EnqueueResult(
            outcome=EnqueueOutcome.UNKNOWN,
            task={"id": task_id, "status": "pending"},
            error_code="TASK_QUEUE_CONFIRMATION_REQUIRED",
        )

    monkeypatch.setattr(reconciliation, "enqueue_task_confirmed", unknown)
    monkeypatch.setattr(reconciliation, "confirm_or_repair_task", still_unknown)
    with Session(publish_engine) as session:
        summary = asyncio.run(reconciliation.reconcile_publish_jobs(session, now=now))

    job = _reload_job(publish_engine)
    assert calls == [
        (
            "enqueue",
            "knowledge_base.publish",
            {"job_id": 1, "tenant_id": 7},
            "knowledge-publish:1",
        ),
        ("confirm", "task-final"),
    ]
    assert job.status == "FAILED"
    assert job.task_id == "task-final"
    assert summary["failed"] == 1


@pytest.mark.parametrize(
    "task_status",
    [
        "succeeded",
        "failed",
    ],
)
def test_terminal_redis_task_cannot_promote_an_active_database_job(
    monkeypatch,
    publish_engine,
    task_status,
) -> None:
    _add_job(publish_engine)

    async def terminal(task_id, **_kwargs):
        return EnqueueResult(
            outcome=EnqueueOutcome.ENQUEUED,
            task={"id": task_id, "status": task_status},
        )

    monkeypatch.setattr(reconciliation, "confirm_or_repair_task", terminal)
    with Session(publish_engine) as session:
        asyncio.run(reconciliation.reconcile_publish_jobs(session))

    assert _reload_job(publish_engine).status == "FAILED"
    with publish_engine.connect() as connection:
        version_status = connection.execute(
            text("SELECT status FROM knowledge_base_version WHERE id = 1")
        ).scalar_one()
        pointers = connection.execute(
            text(
                "SELECT current_version_id, draft_version_id, publishing_version_id "
                "FROM knowledge_base WHERE id = 1"
            )
        ).one()
    assert version_status == "PUBLISH_FAILED"
    assert pointers == (None, None, None)


def test_missing_exact_task_reenqueues_only_after_not_found(monkeypatch, publish_engine) -> None:
    _add_job(publish_engine)
    calls = []

    async def missing(task_id, **_kwargs):
        calls.append(("confirm", task_id))
        return EnqueueResult(
            outcome=EnqueueOutcome.REJECTED,
            task=None,
            error_code="TASK_NOT_FOUND",
        )

    async def enqueue(name, payload, **kwargs):
        calls.append(("enqueue", name, payload, kwargs["dedupe_key"]))
        return EnqueueResult(
            outcome=EnqueueOutcome.ENQUEUED,
            task={"id": "task-2", "status": "pending"},
        )

    monkeypatch.setattr(reconciliation, "confirm_or_repair_task", missing)
    monkeypatch.setattr(reconciliation, "enqueue_task_confirmed", enqueue)
    with Session(publish_engine) as session:
        asyncio.run(reconciliation.reconcile_publish_jobs(session))

    job = _reload_job(publish_engine)
    assert calls == [
        ("confirm", "task-1"),
        ("enqueue", "knowledge_base.publish", {"job_id": 1, "tenant_id": 7}, "knowledge-publish:1"),
    ]
    assert job.task_id == "task-2"
    assert job.status == "QUEUED"
    assert job.enqueue_attempts == 1


def test_missing_queued_task_reenqueues_without_status_regression(
    monkeypatch,
    publish_engine,
) -> None:
    _add_job(publish_engine, status="QUEUED")

    async def missing(_task_id, **_kwargs):
        return EnqueueResult(
            outcome=EnqueueOutcome.REJECTED,
            task=None,
            error_code="TASK_NOT_FOUND",
        )

    async def enqueue(*_args, **_kwargs):
        return EnqueueResult(
            outcome=EnqueueOutcome.ENQUEUED,
            task={"id": "task-2", "status": "pending"},
        )

    monkeypatch.setattr(reconciliation, "confirm_or_repair_task", missing)
    monkeypatch.setattr(reconciliation, "enqueue_task_confirmed", enqueue)
    with Session(publish_engine) as session:
        asyncio.run(reconciliation.reconcile_publish_jobs(session))

    job = _reload_job(publish_engine)
    assert job.status == "QUEUED"
    assert job.task_id == "task-2"
    assert job.enqueue_attempts == 1


def test_missing_task_fails_without_reenqueue_when_attempts_are_exhausted(
    monkeypatch,
    publish_engine,
) -> None:
    _add_job(publish_engine, enqueue_attempts=3, max_attempts=3)
    enqueued = False

    async def missing(_task_id, **_kwargs):
        return EnqueueResult(
            outcome=EnqueueOutcome.REJECTED,
            task=None,
            error_code="TASK_NOT_FOUND",
        )

    async def enqueue(*_args, **_kwargs):
        nonlocal enqueued
        enqueued = True
        raise AssertionError("重试次数耗尽后不得创建新任务")

    monkeypatch.setattr(reconciliation, "confirm_or_repair_task", missing)
    monkeypatch.setattr(reconciliation, "enqueue_task_confirmed", enqueue)
    with Session(publish_engine) as session:
        summary = asyncio.run(reconciliation.reconcile_publish_jobs(session))

    assert enqueued is False
    assert _reload_job(publish_engine).status == "FAILED"
    assert summary["failed"] == 1


def test_permanent_enqueue_rejection_fails_without_waiting_for_deadline(
    monkeypatch,
    publish_engine,
) -> None:
    _add_job(publish_engine, task_id=None)

    async def rejected(*_args, **_kwargs):
        return EnqueueResult(
            outcome=EnqueueOutcome.REJECTED,
            task=None,
            error_code="TASK_HANDLER_NOT_REGISTERED",
        )

    monkeypatch.setattr(reconciliation, "enqueue_task_confirmed", rejected)
    with Session(publish_engine) as session:
        summary = asyncio.run(reconciliation.reconcile_publish_jobs(session))

    job = _reload_job(publish_engine)
    assert job.status == "FAILED"
    assert job.error_code == "TASK_HANDLER_NOT_REGISTERED"
    assert summary["failed"] == 1


def test_active_task_found_after_deadline_is_not_failed(monkeypatch, publish_engine) -> None:
    now = datetime.utcnow()
    _add_job(publish_engine, deadline_at=now - timedelta(seconds=1))

    async def confirmed(task_id, **_kwargs):
        return EnqueueResult(
            outcome=EnqueueOutcome.ENQUEUED,
            task={"id": task_id, "status": "pending"},
        )

    monkeypatch.setattr(reconciliation, "confirm_or_repair_task", confirmed)
    with Session(publish_engine) as session:
        asyncio.run(reconciliation.reconcile_publish_jobs(session, now=now))

    assert _reload_job(publish_engine).status == "QUEUED"


def test_publish_timeout_defaults_are_explicit() -> None:
    from common.core.config import Settings

    settings = Settings(_env_file=None, SECRET_KEY="test-secret")
    assert settings.KNOWLEDGE_PUBLISH_TIMEOUT_SECONDS == 900
    assert settings.KNOWLEDGE_PUBLISH_QUEUE_TIMEOUT_SECONDS == 60
    assert settings.KNOWLEDGE_PUBLISH_RECONCILE_INTERVAL_SECONDS == 60
