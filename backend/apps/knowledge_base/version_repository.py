"""Database operations for knowledge-base drafts and immutable versions.

The repository owns row locks and conditional writes.  Lifecycle decisions stay
in ``lifecycle_service.py`` so route handlers do not need to know SQL details.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, update
from sqlmodel import Session, select

from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.lifecycle_models import (
    ACTIVE_DRAFT_STATUSES,
    ACTIVE_PUBLISH_JOB_STATUSES,
    KnowledgeBaseVersion,
    KnowledgePublishJob,
    KnowledgeVersionStatus,
)
from apps.knowledge_base.models import KnowledgeBase
from apps.knowledge_base.retrieval_models import KnowledgeBaseWorkspaceOverride
from common.audit.models.log_model import OperationStatus, OperationType, SystemLog

KNOWLEDGE_VERSION_RETENTION_LIMIT = 10


@dataclass(frozen=True)
class SourceFileRef:
    """Request-private file metadata that is safe to persist on a version."""

    file_id: str
    file_name: str | None = None
    file_ext: str | None = None
    parser_version: str | None = None


def _status_value(status: KnowledgeVersionStatus | str) -> str:
    return status.value if isinstance(status, KnowledgeVersionStatus) else str(status)


class KnowledgeVersionRepository:
    """Small persistence boundary for the knowledge version state machine."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_knowledge_base(self, *, tenant_id: int, knowledge_base_id: int) -> KnowledgeBase | None:
        return self.session.exec(
            select(KnowledgeBase)
            .where(
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.tenant_id == tenant_id,
            )
            .execution_options(populate_existing=True)
        ).first()

    def lock_knowledge_base(self, *, tenant_id: int, knowledge_base_id: int) -> KnowledgeBase:
        record = self.session.exec(
            select(KnowledgeBase)
            .where(
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.tenant_id == tenant_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
        if record is None:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_NOT_FOUND",
                message="知识不存在或已被删除。",
                status_code=404,
                error_type="NOT_FOUND",
            )
        return record

    def get_version(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        version_id: int,
        for_update: bool = False,
    ) -> KnowledgeBaseVersion | None:
        statement = select(KnowledgeBaseVersion).where(
            KnowledgeBaseVersion.id == version_id,
            KnowledgeBaseVersion.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseVersion.tenant_id == tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.exec(
            statement.execution_options(populate_existing=True)
        ).first()

    def get_active_draft(
        self, *, tenant_id: int, knowledge_base_id: int, for_update: bool = False
    ) -> KnowledgeBaseVersion | None:
        statement = select(KnowledgeBaseVersion).where(
            KnowledgeBaseVersion.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseVersion.tenant_id == tenant_id,
            KnowledgeBaseVersion.status.in_(ACTIVE_DRAFT_STATUSES),
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.exec(
            statement.execution_options(populate_existing=True)
        ).first()

    def get_latest_archived_published_version(
        self, *, tenant_id: int, knowledge_base_id: int, for_update: bool = False
    ) -> KnowledgeBaseVersion | None:
        statement = (
            select(KnowledgeBaseVersion)
            .where(
                KnowledgeBaseVersion.knowledge_base_id == knowledge_base_id,
                KnowledgeBaseVersion.tenant_id == tenant_id,
                KnowledgeBaseVersion.status == KnowledgeVersionStatus.ARCHIVED.value,
                KnowledgeBaseVersion.publish_time.is_not(None),
            )
            .order_by(
                KnowledgeBaseVersion.publish_time.desc(),
                KnowledgeBaseVersion.version_number.desc(),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.exec(
            statement.execution_options(populate_existing=True)
        ).first()

    def next_version_number(self, *, knowledge_base_id: int) -> int:
        current = self.session.exec(
            select(func.max(KnowledgeBaseVersion.version_number)).where(
                KnowledgeBaseVersion.knowledge_base_id == knowledge_base_id
            )
        ).one()
        return int(current or 0) + 1

    def add_draft(
        self,
        *,
        record: KnowledgeBase,
        payload: dict[str, Any],
        normalized_content: str,
        content_hash: str,
        actor_id: int | None,
        source_file: SourceFileRef | None = None,
        status: KnowledgeVersionStatus = KnowledgeVersionStatus.DRAFT,
    ) -> KnowledgeBaseVersion:
        version = KnowledgeBaseVersion(
            knowledge_base_id=int(record.id),
            tenant_id=int(record.tenant_id),
            version_number=self.next_version_number(knowledge_base_id=int(record.id)),
            revision=1,
            status=status,
            payload=payload,
            normalized_content=normalized_content,
            content_hash=content_hash,
            create_by=actor_id,
            create_time=datetime.now(),
            file_id=source_file.file_id if source_file else None,
            file_name=source_file.file_name if source_file else None,
            file_ext=source_file.file_ext if source_file else None,
            parser_version=source_file.parser_version if source_file else None,
        )
        self.session.add(version)
        self.session.flush()
        record.draft_version_id = int(version.id)
        record.update_by = actor_id
        record.update_time = datetime.now()
        self.session.flush()
        return version

    def prune_versions(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        retain: int = KNOWLEDGE_VERSION_RETENTION_LIMIT,
    ) -> tuple[str, ...]:
        """Delete versions outside the bounded history and return source-file candidates."""
        if retain < 1:
            raise ValueError("retain must be at least 1")

        record = self.lock_knowledge_base(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
        )
        versions = self.session.exec(
            select(KnowledgeBaseVersion)
            .where(
                KnowledgeBaseVersion.knowledge_base_id == knowledge_base_id,
                KnowledgeBaseVersion.tenant_id == tenant_id,
            )
            .order_by(KnowledgeBaseVersion.version_number.desc())
        ).all()
        if len(versions) <= retain:
            return ()

        protected_ids = {
            int(version_id)
            for version_id in (
                record.current_version_id,
                record.draft_version_id,
                record.publishing_version_id,
            )
            if version_id is not None
        }
        protected_ids.update(
            int(version_id)
            for version_id in self.session.exec(
                select(KnowledgePublishJob.version_id).where(
                    KnowledgePublishJob.knowledge_base_id == knowledge_base_id,
                    KnowledgePublishJob.tenant_id == tenant_id,
                    KnowledgePublishJob.status.in_(ACTIVE_PUBLISH_JOB_STATUSES),
                )
            ).all()
        )

        keep_ids = {
            int(version.id)
            for version in versions
            if int(version.id) in protected_ids
        }
        for version in versions:
            if len(keep_ids) >= retain:
                break
            keep_ids.add(int(version.id))

        discarded = tuple(
            version for version in versions if int(version.id) not in keep_ids
        )
        discarded_ids = tuple(int(version.id) for version in discarded)
        if not discarded_ids:
            return ()

        source_file_ids = tuple(
            sorted(
                {
                    str(version.file_id)
                    for version in discarded
                    if getattr(version, "file_id", None)
                }
            )
        )
        self.session.exec(
            delete(KnowledgePublishJob).where(
                KnowledgePublishJob.knowledge_base_id == knowledge_base_id,
                KnowledgePublishJob.tenant_id == tenant_id,
                KnowledgePublishJob.version_id.in_(discarded_ids),
            )
        )
        self.session.exec(
            delete(KnowledgeBaseVersion).where(
                KnowledgeBaseVersion.knowledge_base_id == knowledge_base_id,
                KnowledgeBaseVersion.tenant_id == tenant_id,
                KnowledgeBaseVersion.id.in_(discarded_ids),
            )
        )
        self.session.flush()
        return source_file_ids

    def save_draft_if_revision_matches(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        version_id: int,
        expected_revision: int,
        payload: dict[str, Any],
        normalized_content: str,
        content_hash: str,
        actor_id: int | None,
        source_file: SourceFileRef | None = None,
    ) -> KnowledgeBaseVersion | None:
        values: dict[str, Any] = {
            "payload": payload,
            "normalized_content": normalized_content,
            "content_hash": content_hash,
            "revision": KnowledgeBaseVersion.revision + 1,
            "status": KnowledgeVersionStatus.DRAFT.value,
            "validation_report": None,
            "error_message": None,
        }
        if source_file is not None:
            values.update(
                file_id=source_file.file_id,
                file_name=source_file.file_name,
                file_ext=source_file.file_ext,
                parser_version=source_file.parser_version,
            )
        result = self.session.exec(
            update(KnowledgeBaseVersion)
            .where(
                KnowledgeBaseVersion.id == version_id,
                KnowledgeBaseVersion.knowledge_base_id == knowledge_base_id,
                KnowledgeBaseVersion.tenant_id == tenant_id,
                KnowledgeBaseVersion.revision == expected_revision,
                KnowledgeBaseVersion.status.in_(
                    (
                        KnowledgeVersionStatus.DRAFT.value,
                        KnowledgeVersionStatus.VALIDATION_FAILED.value,
                        KnowledgeVersionStatus.READY_TO_PUBLISH.value,
                        KnowledgeVersionStatus.PUBLISH_FAILED.value,
                    )
                ),
            )
            .values(**values)
        )
        self.session.flush()
        if result.rowcount != 1:
            return None
        return self.get_version(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            version_id=version_id,
            for_update=False,
        )

    def update_locked_draft(
        self,
        *,
        version: KnowledgeBaseVersion,
        payload: dict[str, Any],
        normalized_content: str,
        content_hash: str,
        actor_id: int | None,
    ) -> KnowledgeBaseVersion:
        """Persist a payload already protected by the knowledge/version row locks."""
        version.payload = payload
        version.normalized_content = normalized_content
        version.content_hash = content_hash
        version.revision = int(version.revision) + 1
        version.status = KnowledgeVersionStatus.DRAFT
        version.validation_report = None
        version.error_message = None
        self.session.add(version)
        self.session.flush()
        return version

    def add_document_block_audit(
        self,
        *,
        record: KnowledgeBase,
        version: KnowledgeBaseVersion,
        actor_id: int | None,
        operation_types: list[str],
        block_ids: list[str],
        added_block_ids: list[str] | None = None,
        deleted_block_ids: list[str] | None = None,
        reordered_block_ids: list[str] | None = None,
    ) -> SystemLog:
        """Write a block mutation audit in the same transaction as the draft."""
        detail = {
            "document_id": int(record.id),
            "version_id": int(version.id),
            "version_number": int(version.version_number),
            "version_revision": int(version.revision),
            "operation_types": operation_types,
            "block_ids": block_ids,
            "added_block_ids": added_block_ids or [],
            "deleted_block_ids": deleted_block_ids or [],
            "reordered_block_ids": reordered_block_ids or [],
        }
        audit = SystemLog(
            tenant_id=int(record.tenant_id),
            operation_type=OperationType.UPDATE.value,
            operation_detail=json.dumps(detail, ensure_ascii=False, sort_keys=True),
            user_id=actor_id,
            operation_status=OperationStatus.SUCCESS.value,
            module="knowledge_base",
            resource_id=str(record.id),
            resource_name=getattr(record, "name", None),
            create_time=datetime.now(),
        )
        self.session.add(audit)
        self.session.flush()
        return audit

    def set_validation_state_if_revision_matches(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        version_id: int,
        expected_revision: int,
        content_hash: str,
        status: KnowledgeVersionStatus,
        validation_report: dict[str, Any],
    ) -> KnowledgeBaseVersion | None:
        result = self.session.exec(
            update(KnowledgeBaseVersion)
            .where(
                KnowledgeBaseVersion.id == version_id,
                KnowledgeBaseVersion.knowledge_base_id == knowledge_base_id,
                KnowledgeBaseVersion.tenant_id == tenant_id,
                KnowledgeBaseVersion.revision == expected_revision,
                KnowledgeBaseVersion.content_hash == content_hash,
                KnowledgeBaseVersion.status.in_(
                    (
                        KnowledgeVersionStatus.DRAFT.value,
                        KnowledgeVersionStatus.VALIDATING.value,
                    )
                ),
            )
            .values(status=status.value, validation_report=validation_report)
        )
        self.session.flush()
        if result.rowcount != 1:
            return None
        return self.get_version(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            version_id=version_id,
        )

    def mark_validating_if_revision_matches(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        version_id: int,
        expected_revision: int,
        content_hash: str,
    ) -> KnowledgeBaseVersion | None:
        result = self.session.exec(
            update(KnowledgeBaseVersion)
            .where(
                KnowledgeBaseVersion.id == version_id,
                KnowledgeBaseVersion.knowledge_base_id == knowledge_base_id,
                KnowledgeBaseVersion.tenant_id == tenant_id,
                KnowledgeBaseVersion.revision == expected_revision,
                KnowledgeBaseVersion.content_hash == content_hash,
                KnowledgeBaseVersion.status.in_(
                    (
                        KnowledgeVersionStatus.DRAFT.value,
                        KnowledgeVersionStatus.VALIDATION_FAILED.value,
                        KnowledgeVersionStatus.PUBLISH_FAILED.value,
                    )
                ),
            )
            .values(status=KnowledgeVersionStatus.VALIDATING.value)
        )
        self.session.flush()
        if result.rowcount != 1:
            return None
        return self.get_version(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            version_id=version_id,
        )

    def upsert_workspace_override(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        enabled: bool,
        actor_id: int | None,
        reason: str | None = None,
    ) -> KnowledgeBaseWorkspaceOverride:
        # Serialize first creation as well as updates on the platform item row.
        self.session.exec(
            select(KnowledgeBase)
            .where(KnowledgeBase.id == knowledge_base_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
        override = self.session.exec(
            select(KnowledgeBaseWorkspaceOverride).where(
                KnowledgeBaseWorkspaceOverride.tenant_id == tenant_id,
                KnowledgeBaseWorkspaceOverride.knowledge_base_id == knowledge_base_id,
            )
        ).first()
        now = datetime.now()
        if override is None:
            override = KnowledgeBaseWorkspaceOverride(
                tenant_id=tenant_id,
                knowledge_base_id=knowledge_base_id,
                enabled=enabled,
                reason=reason,
                update_by=actor_id,
                update_time=now,
            )
            self.session.add(override)
        else:
            override.enabled = enabled
            override.reason = reason
            override.update_by = actor_id
            override.update_time = now
        self.session.flush()
        return override

    def delete_all(self, *, record: KnowledgeBase) -> tuple[str, ...]:
        file_ids = {
            str(file_id)
            for file_id in self.session.exec(
                select(KnowledgeBaseVersion.file_id).where(
                    KnowledgeBaseVersion.knowledge_base_id == record.id,
                    KnowledgeBaseVersion.tenant_id == record.tenant_id,
                    KnowledgeBaseVersion.file_id.is_not(None),
                )
            ).all()
            if file_id
        }
        if record.file_id:
            file_ids.add(str(record.file_id))

        record.draft_version_id = None
        record.current_version_id = None
        record.publishing_version_id = None
        self.session.add(record)
        self.session.flush()
        self.session.exec(
            delete(KnowledgePublishJob).where(
                KnowledgePublishJob.knowledge_base_id == record.id,
                KnowledgePublishJob.tenant_id == record.tenant_id,
            )
        )
        self.session.exec(
            delete(KnowledgeBaseVersion).where(
                KnowledgeBaseVersion.knowledge_base_id == record.id,
                KnowledgeBaseVersion.tenant_id == record.tenant_id,
            )
        )
        self.session.delete(record)
        self.session.flush()
        return tuple(sorted(file_ids))
