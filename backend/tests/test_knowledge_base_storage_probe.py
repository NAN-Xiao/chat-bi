"""Verify shared-storage probe generation and Worker readiness."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.pool import NullPool
from sqlmodel import Session

from apps.knowledge_base.lifecycle_models import (
    KnowledgeStorageProbe,
    KnowledgeStorageProbeReceipt,
)
from apps.knowledge_base.storage_probe import (
    StorageProbeError,
    _postgresql_receipt_upsert,
    publishing_workers_ready,
    record_storage_probe_receipt,
    rotate_storage_probe_generation,
)
from common.core.task_queue import registered_task_names
from common.core.task_registry import register_builtin_tasks


class _ReceiptSession(Session):
    _id_lock = Lock()
    _next_id = 1

    def add(self, instance, *args, **kwargs):
        if isinstance(instance, KnowledgeStorageProbeReceipt) and instance.id is None:
            with self._id_lock:
                instance.id = self._next_id
                type(self)._next_id += 1
        return super().add(instance, *args, **kwargs)


@pytest.fixture
def probe_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'storage-probe.db'}",
        poolclass=NullPool,
        connect_args={"timeout": 30},
    )
    KnowledgeStorageProbe.__table__.create(engine)
    KnowledgeStorageProbeReceipt.__table__.create(engine)
    with Session(engine) as session:
        session.add(KnowledgeStorageProbe(id=1, generation=0))
        session.commit()
    yield engine
    engine.dispose()


def _locked_session_factory(engine):
    def factory():
        session = _ReceiptSession(engine)
        session.exec(text("BEGIN IMMEDIATE"))
        return session

    return factory


def test_concurrent_api_startup_keeps_one_probe_generation(
    probe_engine,
    tmp_path,
) -> None:
    factory = _locked_session_factory(probe_engine)

    with ThreadPoolExecutor(max_workers=8) as executor:
        generations = list(
            executor.map(
                lambda _index: rotate_storage_probe_generation(
                    factory,
                    config_hash="same",
                    upload_dir=tmp_path,
                ),
                range(8),
            )
        )

    assert set(generations) == {1}
    files = list(Path(tmp_path).glob("knowledge_storage_probe_*.json"))
    assert len(files) == 1
    assert files[0].name != "knowledge_storage_probe_1.json"
    with Session(probe_engine) as session:
        probe = session.get(KnowledgeStorageProbe, 1)
        assert probe is not None
        assert probe.generation == 1
        assert probe.config_fingerprint == "same"


def test_force_rotation_advances_generation_and_invalidates_old_receipts(
    probe_engine,
    tmp_path,
) -> None:
    factory = _locked_session_factory(probe_engine)
    first = rotate_storage_probe_generation(
        factory,
        config_hash="same",
        upload_dir=tmp_path,
    )
    with _ReceiptSession(probe_engine) as session:
        record_storage_probe_receipt(
            session,
            generation=first,
            worker_id="worker-1",
            queue_name="local-test",
            upload_dir=tmp_path,
        )
    second = rotate_storage_probe_generation(
        factory,
        config_hash="same",
        force=True,
        upload_dir=tmp_path,
    )

    assert second == first + 1
    with _ReceiptSession(probe_engine) as session:
        assert not publishing_workers_ready(
            session,
            active_consumers=[("worker-1", "local-test")],
        )


def test_stale_session_cannot_acknowledge_an_old_generation(
    probe_engine,
    tmp_path,
) -> None:
    factory = _locked_session_factory(probe_engine)
    first = rotate_storage_probe_generation(
        factory,
        config_hash="same",
        upload_dir=tmp_path,
    )
    with _ReceiptSession(probe_engine, expire_on_commit=False) as stale_session:
        cached = stale_session.get(KnowledgeStorageProbe, 1)
        assert cached is not None and cached.generation == first
        stale_session.commit()

        second = rotate_storage_probe_generation(
            factory,
            config_hash="same",
            force=True,
            upload_dir=tmp_path,
        )
        assert second == first + 1

        with pytest.raises(StorageProbeError) as caught:
            record_storage_probe_receipt(
                stale_session,
                generation=first,
                worker_id="worker-1",
                queue_name="local-test",
                upload_dir=tmp_path,
            )
        assert caught.value.code == "KNOWLEDGE_STORAGE_PROBE_STALE_GENERATION"


def test_readiness_requires_fresh_current_receipt_from_every_active_worker(
    probe_engine,
    tmp_path,
) -> None:
    generation = rotate_storage_probe_generation(
        _locked_session_factory(probe_engine),
        config_hash="same",
        upload_dir=tmp_path,
    )
    now = datetime.utcnow()
    with _ReceiptSession(probe_engine) as session:
        record_storage_probe_receipt(
            session,
            generation=generation,
            worker_id="worker-1",
            queue_name="local-test",
            now=now,
            upload_dir=tmp_path,
        )
        assert not publishing_workers_ready(
            session,
            active_consumers=[
                ("worker-1", "local-test"),
                ("worker-2", "local-test"),
            ],
            now=now,
        )
        record_storage_probe_receipt(
            session,
            generation=generation,
            worker_id="worker-2",
            queue_name="local-test",
            now=now,
            upload_dir=tmp_path,
        )
        assert publishing_workers_ready(
            session,
            active_consumers=[
                ("worker-1", "local-test"),
                ("worker-2", "local-test"),
            ],
            now=now,
        )
        assert not publishing_workers_ready(
            session,
            active_consumers=[
                ("worker-1", "local-test"),
                ("worker-2", "local-test"),
            ],
            now=now + timedelta(minutes=3),
            freshness_seconds=120,
        )


def test_tampered_probe_is_rejected_without_receipt(probe_engine, tmp_path) -> None:
    generation = rotate_storage_probe_generation(
        _locked_session_factory(probe_engine),
        config_hash="same",
        upload_dir=tmp_path,
    )
    with Session(probe_engine) as session:
        probe = session.get(KnowledgeStorageProbe, 1)
        assert probe is not None and probe.file_id
        (Path(tmp_path) / probe.file_id).write_bytes(b"tampered")

    with _ReceiptSession(probe_engine) as session:
        with pytest.raises(StorageProbeError) as caught:
            record_storage_probe_receipt(
                session,
                generation=generation,
                worker_id="worker-1",
                queue_name="local-test",
                upload_dir=tmp_path,
            )
        assert caught.value.code == "KNOWLEDGE_STORAGE_PROBE_HASH_MISMATCH"
        assert str(caught.value) == "共享文件存储校验失败，请检查 API 与 Worker 的存储挂载。"

        receipts = session.exec(
            text("SELECT COUNT(*) FROM knowledge_storage_probe_receipt")
        ).one()[0]
        assert receipts == 0


def test_empty_active_consumer_set_fails_closed(probe_engine, tmp_path) -> None:
    rotate_storage_probe_generation(
        _locked_session_factory(probe_engine),
        config_hash="same",
        upload_dir=tmp_path,
    )
    with _ReceiptSession(probe_engine) as session:
        assert publishing_workers_ready(session, active_consumers=[]) is False


def test_postgresql_receipt_upsert_is_atomic() -> None:
    statement = _postgresql_receipt_upsert(
        generation=3,
        worker_id="worker-1",
        queue_name="local-test",
        content_hash="a" * 64,
        now=datetime.utcnow(),
    )

    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT ON CONSTRAINT uq_knowledge_storage_probe_receipt_consumer" in sql
    assert "DO UPDATE SET content_hash" in sql


def test_publish_recovery_tasks_are_registered() -> None:
    register_builtin_tasks()

    names = registered_task_names()
    assert "knowledge_base.reconcile_publish_jobs" in names
    assert "knowledge_base.storage_probe" in names
