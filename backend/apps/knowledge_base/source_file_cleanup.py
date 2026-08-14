"""Reference-aware cleanup for knowledge source files."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, select

from apps.knowledge_base.lifecycle_models import KnowledgeBaseVersion
from apps.knowledge_base.models import KnowledgeBase
from common.utils.file_utils import AppFileUtils

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceFileCleanupResult:
    deleted: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    referenced: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()

    def as_counts(self) -> dict[str, int]:
        return {
            "deleted": len(self.deleted),
            "missing": len(self.missing),
            "referenced": len(self.referenced),
            "failed": len(self.failed),
        }


def cleanup_unreferenced_source_files(
    session: Session,
    file_ids: Iterable[str | None],
) -> SourceFileCleanupResult:
    """Delete candidate files only after every database reference is gone."""
    candidates = tuple(sorted({str(file_id) for file_id in file_ids if file_id}))
    if not candidates:
        return SourceFileCleanupResult()

    try:
        referenced = {
            str(file_id)
            for file_id in session.exec(
                select(KnowledgeBaseVersion.file_id).where(
                    KnowledgeBaseVersion.file_id.in_(candidates)
                )
            ).all()
            if file_id
        }
        referenced.update(
            str(file_id)
            for file_id in session.exec(
                select(KnowledgeBase.file_id).where(KnowledgeBase.file_id.in_(candidates))
            ).all()
            if file_id
        )
    except Exception:
        logger.exception("Failed to verify knowledge source file references")
        return SourceFileCleanupResult(failed=candidates)

    deleted: list[str] = []
    missing: list[str] = []
    failed: list[str] = []
    for file_id in candidates:
        if file_id in referenced:
            continue
        path = Path(AppFileUtils.get_file_path(file_id))
        existed = path.exists()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Failed to delete unreferenced knowledge source file %s", file_id)
            failed.append(file_id)
        else:
            (deleted if existed else missing).append(file_id)

    return SourceFileCleanupResult(
        deleted=tuple(deleted),
        missing=tuple(missing),
        referenced=tuple(sorted(referenced.intersection(candidates))),
        failed=tuple(failed),
    )
