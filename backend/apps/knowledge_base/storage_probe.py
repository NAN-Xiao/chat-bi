"""Generation-scoped shared-storage probes for publishing Workers."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlmodel import Session, select

from apps.knowledge_base.lifecycle_models import (
    KnowledgeStorageProbe,
    KnowledgeStorageProbeReceipt,
)
from common.core.config import settings

STORAGE_PROBE_MESSAGE = "共享文件存储校验失败，请检查 API 与 Worker 的存储挂载。"
STORAGE_PROBE_STALE_MESSAGE = "共享文件存储校验代次已过期，请重试。"


class StorageProbeError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _probe_directory(upload_dir: str | Path | None) -> Path:
    path = Path(upload_dir or settings.UPLOAD_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _probe_content(generation: int, token: str) -> bytes:
    return json.dumps(
        {"generation": generation, "token": token},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_probe_atomic(directory: Path, file_id: str, content: bytes) -> Path:
    target = directory / file_id
    temporary = directory / f".{file_id}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_bytes(content)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def rotate_storage_probe_generation(
    session_factory: Callable[[], Session],
    *,
    config_hash: str,
    force: bool = False,
    upload_dir: str | Path | None = None,
    now: datetime | None = None,
) -> int:
    resolved_now = now or datetime.utcnow()
    with session_factory() as session:
        probe = session.exec(
            select(KnowledgeStorageProbe)
            .where(KnowledgeStorageProbe.id == 1)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()
        if (
            not force
            and int(probe.generation) > 0
            and probe.config_fingerprint == config_hash
        ):
            generation = int(probe.generation)
            session.commit()
            return generation

        generation = int(probe.generation) + 1
        token = secrets.token_urlsafe(32)
        content = _probe_content(generation, token)
        file_id = (
            f"knowledge_storage_probe_{generation}_{secrets.token_urlsafe(18)}.json"
        )
        target = _write_probe_atomic(_probe_directory(upload_dir), file_id, content)
        try:
            probe.generation = generation
            probe.config_fingerprint = config_hash
            probe.file_id = file_id
            probe.token_hash = _sha256(token.encode("utf-8"))
            probe.content_hash = _sha256(content)
            probe.update_time = resolved_now
            session.add(probe)
            session.commit()
        except Exception:
            session.rollback()
            target.unlink(missing_ok=True)
            raise
        return generation


def _load_verified_probe(
    probe: KnowledgeStorageProbe,
    *,
    upload_dir: str | Path | None,
) -> str:
    if not probe.file_id or not probe.content_hash or not probe.token_hash:
        raise StorageProbeError("KNOWLEDGE_STORAGE_PROBE_INCOMPLETE", STORAGE_PROBE_MESSAGE)
    path = _probe_directory(upload_dir) / probe.file_id
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise StorageProbeError(
            "KNOWLEDGE_STORAGE_PROBE_UNREADABLE",
            STORAGE_PROBE_MESSAGE,
        ) from exc
    if _sha256(content) != probe.content_hash:
        raise StorageProbeError(
            "KNOWLEDGE_STORAGE_PROBE_HASH_MISMATCH",
            STORAGE_PROBE_MESSAGE,
        )
    try:
        payload = json.loads(content)
        payload_generation = int(payload["generation"])
        token = str(payload["token"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise StorageProbeError(
            "KNOWLEDGE_STORAGE_PROBE_INVALID",
            STORAGE_PROBE_MESSAGE,
        ) from exc
    if payload_generation != int(probe.generation) or _sha256(token.encode("utf-8")) != probe.token_hash:
        raise StorageProbeError(
            "KNOWLEDGE_STORAGE_PROBE_INVALID",
            STORAGE_PROBE_MESSAGE,
        )
    return probe.content_hash


def record_storage_probe_receipt(
    session: Session,
    *,
    generation: int,
    worker_id: str,
    queue_name: str,
    upload_dir: str | Path | None = None,
    now: datetime | None = None,
) -> KnowledgeStorageProbeReceipt:
    probe = session.exec(
        select(KnowledgeStorageProbe)
        .where(KnowledgeStorageProbe.id == 1)
        .execution_options(populate_existing=True)
    ).first()
    if probe is None:
        raise StorageProbeError("KNOWLEDGE_STORAGE_PROBE_NOT_FOUND", STORAGE_PROBE_MESSAGE)
    if int(probe.generation) != int(generation):
        raise StorageProbeError(
            "KNOWLEDGE_STORAGE_PROBE_STALE_GENERATION",
            STORAGE_PROBE_STALE_MESSAGE,
        )
    content_hash = _load_verified_probe(probe, upload_dir=upload_dir)
    resolved_now = now or datetime.utcnow()
    if session.get_bind().dialect.name == "postgresql":
        session.exec(
            _postgresql_receipt_upsert(
                generation=int(generation),
                worker_id=str(worker_id),
                queue_name=str(queue_name),
                content_hash=content_hash,
                now=resolved_now,
            )
        )
        session.commit()
        return session.exec(
            select(KnowledgeStorageProbeReceipt)
            .where(
                KnowledgeStorageProbeReceipt.generation == int(generation),
                KnowledgeStorageProbeReceipt.worker_id == str(worker_id),
                KnowledgeStorageProbeReceipt.queue_name == str(queue_name),
            )
            .execution_options(populate_existing=True)
        ).one()

    receipt = session.exec(
        select(KnowledgeStorageProbeReceipt).where(
            KnowledgeStorageProbeReceipt.generation == int(generation),
            KnowledgeStorageProbeReceipt.worker_id == str(worker_id),
            KnowledgeStorageProbeReceipt.queue_name == str(queue_name),
        )
    ).first()
    if receipt is None:
        receipt = KnowledgeStorageProbeReceipt(
            generation=int(generation),
            worker_id=str(worker_id),
            queue_name=str(queue_name),
            content_hash=content_hash,
            heartbeat_at=resolved_now,
            create_time=resolved_now,
            update_time=resolved_now,
        )
    else:
        receipt.content_hash = content_hash
        receipt.heartbeat_at = resolved_now
        receipt.update_time = resolved_now
    session.add(receipt)
    session.commit()
    return receipt


def _postgresql_receipt_upsert(
    *,
    generation: int,
    worker_id: str,
    queue_name: str,
    content_hash: str,
    now: datetime,
):
    statement = postgresql_insert(KnowledgeStorageProbeReceipt).values(
        generation=generation,
        worker_id=worker_id,
        queue_name=queue_name,
        content_hash=content_hash,
        heartbeat_at=now,
        create_time=now,
        update_time=now,
    )
    return statement.on_conflict_do_update(
        constraint="uq_knowledge_storage_probe_receipt_consumer",
        set_={
            "content_hash": statement.excluded.content_hash,
            "heartbeat_at": statement.excluded.heartbeat_at,
            "update_time": statement.excluded.update_time,
        },
    )


def publishing_workers_ready(
    session: Session,
    *,
    active_consumers: Iterable[tuple[str, str]],
    now: datetime | None = None,
    freshness_seconds: int = 120,
) -> bool:
    expected = {(str(worker_id), str(queue_name)) for worker_id, queue_name in active_consumers}
    if not expected:
        return False
    probe = session.exec(
        select(KnowledgeStorageProbe)
        .where(KnowledgeStorageProbe.id == 1)
        .execution_options(populate_existing=True)
    ).first()
    if probe is None or int(probe.generation) <= 0 or not probe.content_hash:
        return False
    cutoff = (now or datetime.utcnow()) - timedelta(seconds=max(1, int(freshness_seconds)))
    receipts = session.exec(
        select(KnowledgeStorageProbeReceipt).where(
            KnowledgeStorageProbeReceipt.generation == int(probe.generation),
            KnowledgeStorageProbeReceipt.heartbeat_at >= cutoff,
            KnowledgeStorageProbeReceipt.content_hash == probe.content_hash,
        )
    ).all()
    fresh = {(receipt.worker_id, receipt.queue_name) for receipt in receipts}
    return expected.issubset(fresh)
