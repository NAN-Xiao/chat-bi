"""Idempotent projection of legacy knowledge rows into V2 versions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from apps.knowledge_base.lifecycle_models import (
    KnowledgeBaseVersion,
    KnowledgeIndexStatus,
    KnowledgeVersionStatus,
)
from apps.knowledge_base.models import KnowledgeBase
from apps.knowledge_base.normalizers import content_hash_for_payload, normalize_markdown
from apps.knowledge_base.repository import KnowledgeMigrationStateRepository
from apps.knowledge_base.schemas import DocumentPayload

MIGRATION_VERSION = "legacy-knowledge-v1"


@dataclass(frozen=True)
class BackfillReport:
    scanned: int = 0
    created: int = 0
    skipped: int = 0
    archived: int = 0
    remaining: int = 0
    cursor: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "created": self.created,
            "skipped": self.skipped,
            "archived": self.archived,
            "remaining": self.remaining,
            "cursor": self.cursor,
        }


def legacy_source_fingerprint(record: Any) -> str:
    """Hash only stable legacy source attributes; never include full content in logs."""
    payload = {
        "legacy_id": int(getattr(record, "id", 0) or 0),
        "content_hash": hashlib.sha256(
            normalize_markdown(str(getattr(record, "content", "") or "")).encode("utf-8")
        ).hexdigest(),
        "update_time": _iso(getattr(record, "update_time", None)),
        "file_id": str(getattr(record, "file_id", "") or ""),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def backfill_v2_page(
    session: Session,
    *,
    page_size: int = 100,
    restart_scan: bool = False,
) -> BackfillReport:
    """Backfill one primary-key page and persist its cursor atomically."""
    state = KnowledgeMigrationStateRepository.lock_for_legacy_write(session)
    if restart_scan:
        state.scan_cursor = None
    cursor = int(state.scan_cursor or 0)
    records = session.exec(
        select(KnowledgeBase)
        .where(KnowledgeBase.id > cursor)
        .order_by(KnowledgeBase.id)
        .limit(max(1, int(page_size)))
    ).all()
    if not records:
        state.scan_cursor = None
        state.last_caught_up_at = datetime.utcnow()
        state.revision = int(state.revision or 0) + 1
        state.update_time = datetime.utcnow()
        session.add(state)
        session.commit()
        return BackfillReport(cursor=None)

    created = skipped = archived = 0
    for record in records:
        fingerprint = legacy_source_fingerprint(record)
        versions = session.exec(
            select(KnowledgeBaseVersion).where(
                KnowledgeBaseVersion.knowledge_base_id == int(record.id),
                KnowledgeBaseVersion.tenant_id == int(record.tenant_id),
            )
        ).all()
        if any(_migration_fingerprint(version) == fingerprint for version in versions):
            skipped += 1
            continue
        for version in versions:
            if _migration_fingerprint(version) is not None and _is_active_draft(version):
                version.status = KnowledgeVersionStatus.ARCHIVED
                session.add(version)
                archived += 1
        version = _build_version(record, fingerprint, versions)
        session.add(version)
        session.flush()
        if _is_ready_record(record):
            record.current_version_id = int(version.id)
        else:
            record.draft_version_id = int(version.id)
        record.update_by = None
        record.update_time = datetime.utcnow()
        session.add(record)
        created += 1

    state.scan_cursor = int(records[-1].id)
    state.revision = int(state.revision or 0) + 1
    state.update_time = datetime.utcnow()
    session.add(state)
    session.commit()
    return BackfillReport(
        scanned=len(records),
        created=created,
        skipped=skipped,
        archived=archived,
        cursor=int(records[-1].id),
    )


def run_backfill_v2(
    session: Session,
    *,
    page_size: int = 100,
    restart_scan: bool = False,
    max_pages: int | None = None,
) -> BackfillReport:
    """Run resumable pages until the source cursor is exhausted."""
    total = BackfillReport()
    first = True
    pages = 0
    while max_pages is None or pages < max(1, int(max_pages)):
        page = backfill_v2_page(
            session,
            page_size=page_size,
            restart_scan=restart_scan if first else False,
        )
        first = False
        pages += 1
        total = BackfillReport(
            scanned=total.scanned + page.scanned,
            created=total.created + page.created,
            skipped=total.skipped + page.skipped,
            archived=total.archived + page.archived,
            cursor=page.cursor,
        )
        if page.scanned == 0:
            return total
    return total


def catch_up_changed_sources(session: Session, *, page_size: int = 100) -> BackfillReport:
    """Rescan all legacy sources; unchanged fingerprints are skipped."""
    return run_backfill_v2(session, page_size=page_size, restart_scan=True)


def _build_version(record: Any, fingerprint: str, versions: list[Any]) -> KnowledgeBaseVersion:
    markdown = normalize_markdown(str(getattr(record, "content", "") or ""))
    payload = DocumentPayload(knowledge_type="DOCUMENT", markdown=markdown).model_dump(
        mode="json", exclude_none=True
    )
    ready = _is_ready_record(record)
    now = datetime.utcnow()
    return KnowledgeBaseVersion(
        knowledge_base_id=int(record.id),
        tenant_id=int(record.tenant_id),
        version_number=max((int(getattr(item, "version_number", 0) or 0) for item in versions), default=0) + 1,
        revision=1,
        status=KnowledgeVersionStatus.PUBLISHED if ready else KnowledgeVersionStatus.DRAFT,
        index_status=KnowledgeIndexStatus.PENDING if ready else KnowledgeIndexStatus.NOT_REQUIRED,
        payload=payload,
        normalized_content=markdown,
        content_hash=content_hash_for_payload(DocumentPayload(**payload)),
        validation_report={
            "valid": bool(ready),
            "errors": [] if ready else [{"code": "LEGACY_SOURCE_NOT_READY", "message": "旧知识尚未完成解析。"}],
            "warnings": [],
            "migration": {
                "source": "legacy_knowledge_base",
                "source_fingerprint": fingerprint,
                "migration_version": MIGRATION_VERSION,
            },
        },
        file_id=getattr(record, "file_id", None),
        file_name=getattr(record, "file_name", None),
        file_ext=getattr(record, "file_ext", None),
        parser_version=MIGRATION_VERSION,
        create_by=getattr(record, "create_by", None),
        create_time=now,
        publish_by=getattr(record, "publish_by", None) if ready else None,
        publish_time=getattr(record, "update_time", None) if ready else None,
        error_message=None if ready else "旧知识尚未完成解析，已创建可编辑草稿。",
    )


def _migration_fingerprint(version: Any) -> str | None:
    report = getattr(version, "validation_report", None) or {}
    migration = report.get("migration") if isinstance(report, dict) else None
    value = migration.get("source_fingerprint") if isinstance(migration, dict) else None
    return str(value) if value else None


def _is_ready_record(record: Any) -> bool:
    return (
        str(getattr(getattr(record, "status", None), "value", getattr(record, "status", ""))) == "READY"
        and bool(str(getattr(record, "content", "") or "").strip())
    )


def _is_active_draft(version: Any) -> bool:
    return str(getattr(getattr(version, "status", None), "value", getattr(version, "status", ""))) in {
        "DRAFT", "VALIDATING", "VALIDATION_FAILED", "READY_TO_PUBLISH", "PUBLISH_FAILED"
    }


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)
