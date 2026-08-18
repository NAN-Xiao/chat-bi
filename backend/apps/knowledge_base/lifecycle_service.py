"""Application service for draft, validation, rollback, and archive transitions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.lifecycle_models import KnowledgeVersionStatus
from apps.knowledge_base.normalizers import (
    content_hash_for_payload,
    normalize_markdown,
    normalize_payload,
)
from apps.knowledge_base.permissions import KnowledgePermissionService
from apps.knowledge_base.schemas import (
    DocumentBlock,
    DocumentPayload,
    KnowledgePayload,
    KnowledgePayloadAdapter,
)
from apps.knowledge_base.validators import ValidationContext, validate_payload
from apps.knowledge_base.version_repository import SourceFileRef
from apps.system.crud.tenant import DEFAULT_TENANT_ID


class LifecycleRepository(Protocol):
    def get_knowledge_base(self, *, tenant_id: int, knowledge_base_id: int): ...
    def lock_knowledge_base(self, *, tenant_id: int, knowledge_base_id: int): ...
    def get_version(self, *, tenant_id: int, knowledge_base_id: int, version_id: int, for_update: bool = False): ...
    def get_active_draft(self, *, tenant_id: int, knowledge_base_id: int, for_update: bool = False): ...
    def get_latest_archived_published_version(self, *, tenant_id: int, knowledge_base_id: int, for_update: bool = False): ...
    def add_draft(self, **kwargs): ...
    def save_draft_if_revision_matches(self, **kwargs): ...
    def update_locked_draft(self, **kwargs): ...
    def add_document_block_audit(self, **kwargs): ...
    def mark_validating_if_revision_matches(self, **kwargs): ...
    def set_validation_state_if_revision_matches(self, **kwargs): ...
    def upsert_workspace_override(self, **kwargs): ...
    def delete_all(self, **kwargs): ...


@dataclass(frozen=True)
class KnowledgeRemovalResult:
    archived_record: Any | None = None
    source_file_ids: tuple[str, ...] = ()

    @property
    def archived(self) -> bool:
        return self.archived_record is not None


def _status(version: Any) -> str:
    value = getattr(version, "status", "")
    return value.value if isinstance(value, KnowledgeVersionStatus) else str(value)


class KnowledgeLifecycleService:
    """Keep state transitions explicit and make every write tenant-scoped."""

    def __init__(
        self,
        repository: LifecycleRepository,
        *,
        permissions: KnowledgePermissionService | None = None,
    ) -> None:
        self.repository = repository
        self.permissions = permissions or KnowledgePermissionService()

    def create_draft(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        payload: KnowledgePayload,
        actor_id: int | None,
        current_user: Any | None = None,
        source_file: SourceFileRef | None = None,
    ):
        record = self.repository.lock_knowledge_base(
            tenant_id=tenant_id, knowledge_base_id=knowledge_base_id
        )
        self.permissions.require_manage(current_user, record)
        self._assert_not_archived(record)
        active = self.repository.get_active_draft(
            tenant_id=tenant_id, knowledge_base_id=knowledge_base_id, for_update=True
        )
        if active is not None:
            raise self._draft_exists()
        return self.repository.add_draft(
            record=record,
            payload=normalize_payload(payload),
            normalized_content=_normalized_content(payload),
            content_hash=content_hash_for_payload(payload),
            actor_id=actor_id,
            source_file=source_file,
        )

    def save_draft(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        draft_version_id: int,
        revision: int,
        payload: KnowledgePayload,
        actor_id: int | None,
        current_user: Any | None = None,
        source_file: SourceFileRef | None = None,
    ):
        record = self.repository.lock_knowledge_base(
            tenant_id=tenant_id, knowledge_base_id=knowledge_base_id
        )
        self.permissions.require_manage(current_user, record)
        version = self._load_version(tenant_id, knowledge_base_id, draft_version_id)
        self._assert_editable(record, version, draft_version_id)
        saved = self.repository.save_draft_if_revision_matches(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            version_id=draft_version_id,
            expected_revision=revision,
            payload=normalize_payload(payload),
            normalized_content=_normalized_content(payload),
            content_hash=content_hash_for_payload(payload),
            actor_id=actor_id,
            source_file=source_file,
        )
        if saved is None:
            raise self._draft_conflict()
        record.draft_version_id = draft_version_id
        record.update_by = actor_id
        return saved

    def save_document_block(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        draft_version_id: int,
        block_id: str,
        block_revision: int,
        title: str,
        markdown: str,
        enabled: bool,
        actor_id: int | None,
        current_user: Any | None = None,
    ):
        record, version, payload = self._lock_document_draft(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            draft_version_id=draft_version_id,
            current_user=current_user,
        )
        block_index = next(
            (index for index, block in enumerate(payload.blocks) if block.id == block_id),
            None,
        )
        if block_index is None:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_DOCUMENT_BLOCK_DELETED",
                message="该知识块已被其他用户删除，本地内容已保留。",
                status_code=409,
                error_type="CONFLICT",
                suggestion="复制本地内容，刷新后新建知识块再保存。",
                details={
                    "conflict_type": "BLOCK_DELETED",
                    "block_id": block_id,
                    "structure_revision": payload.structure_revision,
                    "server_payload": normalize_payload(payload),
                },
            )
        server_block = payload.blocks[block_index]
        if server_block.block_revision != block_revision:
            raise self._block_conflict(payload, server_block)
        blocks = list(payload.blocks)
        updated_block = DocumentBlock(
            id=server_block.id,
            title=title,
            markdown=markdown,
            enabled=enabled,
            block_revision=server_block.block_revision + 1,
        )
        blocks[block_index] = updated_block
        updated = payload.model_copy(update={"blocks": blocks})
        saved = self._persist_locked_document(
            record=record,
            version=version,
            payload=updated,
            actor_id=actor_id,
        )
        operation_types: list[str] = []
        if (
            updated_block.title != server_block.title
            or normalize_markdown(updated_block.markdown)
            != normalize_markdown(server_block.markdown)
        ):
            operation_types.append("UPDATE_BLOCK")
        if updated_block.enabled != server_block.enabled:
            operation_types.append(
                "ENABLE_BLOCK" if updated_block.enabled else "DISABLE_BLOCK"
            )
        self.repository.add_document_block_audit(
            record=record,
            version=saved,
            actor_id=actor_id,
            operation_types=operation_types or ["UPDATE_BLOCK"],
            block_ids=[block_id],
        )
        return saved

    def save_document_structure(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        draft_version_id: int,
        structure_revision: int,
        payload: DocumentPayload,
        actor_id: int | None,
        current_user: Any | None = None,
    ):
        record, version, server_payload = self._lock_document_draft(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            draft_version_id=draft_version_id,
            current_user=current_user,
        )
        if server_payload.structure_revision != structure_revision:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_DOCUMENT_STRUCTURE_CONFLICT",
                message="知识块结构已被其他用户更新，本地修改已保留。",
                status_code=409,
                error_type="CONFLICT",
                suggestion="比较最新结构后重新执行新增、删除或排序。",
                details={
                    "conflict_type": "STRUCTURE",
                    "structure_revision": server_payload.structure_revision,
                    "server_payload": normalize_payload(server_payload),
                },
            )
        if not payload.blocks:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_DOCUMENT_BLOCK_REQUIRED",
                message="知识文档至少需要保留一个知识块。",
                status_code=422,
                field_path="blocks",
                error_type="VALIDATION",
            )
        server_by_id = {block.id: block for block in server_payload.blocks}
        seen: set[str] = set()
        merged_blocks: list[DocumentBlock] = []
        for submitted in payload.blocks:
            if submitted.id in seen:
                raise KnowledgeBusinessError(
                    code="KNOWLEDGE_DOCUMENT_BLOCK_ID_DUPLICATE",
                    message="知识块标识重复，请刷新后重试。",
                    status_code=422,
                    field_path="blocks",
                    error_type="VALIDATION",
                )
            seen.add(submitted.id)
            server_block = server_by_id.get(submitted.id)
            merged_blocks.append(
                server_block
                if server_block is not None
                else submitted.model_copy(update={"block_revision": 1})
            )
        server_ids = [block.id for block in server_payload.blocks]
        submitted_ids = [block.id for block in merged_blocks]
        server_id_set = set(server_ids)
        submitted_id_set = set(submitted_ids)
        added_ids = [block_id for block_id in submitted_ids if block_id not in server_id_set]
        deleted_ids = [block_id for block_id in server_ids if block_id not in submitted_id_set]
        old_common = [block_id for block_id in server_ids if block_id in submitted_id_set]
        new_common = [block_id for block_id in submitted_ids if block_id in server_id_set]
        reordered_ids = new_common if old_common != new_common else []
        updated = server_payload.model_copy(update={
            "blocks": merged_blocks,
            "structure_revision": server_payload.structure_revision + 1,
        })
        saved = self._persist_locked_document(
            record=record,
            version=version,
            payload=updated,
            actor_id=actor_id,
        )
        operation_types = []
        if added_ids:
            operation_types.append("ADD_BLOCK")
        if deleted_ids:
            operation_types.append("DELETE_BLOCK")
        if reordered_ids:
            operation_types.append("REORDER_BLOCKS")
        self.repository.add_document_block_audit(
            record=record,
            version=saved,
            actor_id=actor_id,
            operation_types=operation_types or ["UPDATE_STRUCTURE"],
            block_ids=list(dict.fromkeys(added_ids + deleted_ids + reordered_ids)),
            added_block_ids=added_ids,
            deleted_block_ids=deleted_ids,
            reordered_block_ids=reordered_ids,
        )
        return saved

    def validate_draft(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        draft_version_id: int,
        revision: int,
        content_hash: str,
        actor_id: int | None = None,
        current_user: Any | None = None,
        context: ValidationContext | None = None,
    ):
        record = self.repository.lock_knowledge_base(
            tenant_id=tenant_id, knowledge_base_id=knowledge_base_id
        )
        self.permissions.require_manage(current_user, record)
        version = self._load_version(tenant_id, knowledge_base_id, draft_version_id)
        self._assert_editable(record, version, draft_version_id)
        if int(getattr(version, "revision", -1)) != int(revision) or getattr(version, "content_hash", None) != content_hash:
            raise self._draft_conflict()
        if _status(version) == KnowledgeVersionStatus.VALIDATING.value:
            raise self._validating()
        marked = self.repository.mark_validating_if_revision_matches(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            version_id=draft_version_id,
            expected_revision=revision,
            content_hash=content_hash,
        )
        if marked is None:
            raise self._draft_conflict()
        try:
            payload = KnowledgePayloadAdapter.validate_python(getattr(marked, "payload", {}))
        except Exception:
            report = {
                "valid": False,
                "errors": [
                    {
                        "code": "KNOWLEDGE_PAYLOAD_INVALID",
                        "message": "知识内容格式不正确，请修正后重新校验。",
                        "field_path": None,
                        "error_type": "ERROR",
                        "suggestion": "检查知识文档内容和必填字段。",
                    }
                ],
                "warnings": [],
            }
        else:
            report = validate_payload(payload, context=context).model_dump(mode="json")
        final_status = (
            KnowledgeVersionStatus.READY_TO_PUBLISH
            if report["valid"]
            else KnowledgeVersionStatus.VALIDATION_FAILED
        )
        finalized = self.repository.set_validation_state_if_revision_matches(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            version_id=draft_version_id,
            expected_revision=revision,
            content_hash=content_hash,
            status=final_status,
            validation_report=report,
        )
        if finalized is None:
            raise self._draft_conflict()
        return finalized

    def rollback_to_new_draft(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        target_version_id: int,
        actor_id: int | None,
        current_user: Any | None = None,
    ):
        record = self.repository.lock_knowledge_base(
            tenant_id=tenant_id, knowledge_base_id=knowledge_base_id
        )
        self.permissions.require_manage(current_user, record)
        self._assert_not_archived(record)
        active = self.repository.get_active_draft(
            tenant_id=tenant_id, knowledge_base_id=knowledge_base_id, for_update=True
        )
        if active is not None:
            if _status(active) == KnowledgeVersionStatus.PUBLISHING.value:
                raise self._publishing()
            raise self._draft_exists()
        target = self._load_version(tenant_id, knowledge_base_id, target_version_id)
        if _status(target) not in {
            KnowledgeVersionStatus.PUBLISHED.value,
            KnowledgeVersionStatus.SUPERSEDED.value,
            KnowledgeVersionStatus.ARCHIVED.value,
        }:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_VERSION_INVALID",
                message="只能从已发布历史版本创建回滚草稿。",
                status_code=400,
                error_type="VALIDATION",
            )
        payload = KnowledgePayloadAdapter.validate_python(getattr(target, "payload", {}))
        source_file = (
            SourceFileRef(
                file_id=target.file_id,
                file_name=target.file_name,
                file_ext=target.file_ext,
                parser_version=target.parser_version,
            )
            if getattr(target, "file_id", None)
            else None
        )
        return self.repository.add_draft(
            record=record,
            payload=normalize_payload(payload),
            normalized_content=getattr(target, "normalized_content", None) or _normalized_content(payload),
            content_hash=content_hash_for_payload(payload),
            actor_id=actor_id,
            source_file=source_file,
        )

    def archive_or_delete(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        actor_id: int | None,
        current_user: Any | None = None,
    ):
        record = self.repository.lock_knowledge_base(
            tenant_id=tenant_id, knowledge_base_id=knowledge_base_id
        )
        self.permissions.require_manage(current_user, record)
        current_id = getattr(record, "current_version_id", None)
        active = self.repository.get_active_draft(
            tenant_id=tenant_id, knowledge_base_id=knowledge_base_id, for_update=True
        )
        if active is not None:
            if _status(active) == KnowledgeVersionStatus.PUBLISHING.value:
                raise self._publishing()
            if _status(active) == KnowledgeVersionStatus.VALIDATING.value:
                raise self._validating()
            if current_id is None:
                return KnowledgeRemovalResult(
                    source_file_ids=self.repository.delete_all(record=record)
                )
            # Archiving is an explicit discard boundary for an unpublished draft.
            active.status = KnowledgeVersionStatus.ARCHIVED
            record.draft_version_id = None
        if bool(getattr(record, "archived", False)):
            return KnowledgeRemovalResult(archived_record=record)
        if current_id is None:
            return KnowledgeRemovalResult(
                source_file_ids=self.repository.delete_all(record=record)
            )
        current = self._load_version(tenant_id, knowledge_base_id, int(current_id))
        current.status = KnowledgeVersionStatus.ARCHIVED
        record.current_version_id = None
        record.draft_version_id = None
        record.publishing_version_id = None
        record.archived = True
        record.active = False
        record.update_by = actor_id
        return KnowledgeRemovalResult(archived_record=record)

    def permanently_delete_archived(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        current_user: Any | None = None,
    ) -> KnowledgeRemovalResult:
        record = self.repository.lock_knowledge_base(
            tenant_id=tenant_id, knowledge_base_id=knowledge_base_id
        )
        self.permissions.require_manage(current_user, record)
        if not bool(getattr(record, "archived", False)):
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_PERMANENT_DELETE_REQUIRES_ARCHIVE",
                message="请先归档知识库，再执行永久删除。",
                status_code=409,
                error_type="CONFLICT",
                suggestion="归档后可在已归档列表中永久删除。",
            )
        return KnowledgeRemovalResult(
            source_file_ids=self.repository.delete_all(record=record)
        )

    def restore(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        actor_id: int | None,
        current_user: Any | None = None,
    ):
        record = self.repository.lock_knowledge_base(
            tenant_id=tenant_id, knowledge_base_id=knowledge_base_id
        )
        self.permissions.require_manage(current_user, record)
        if not bool(getattr(record, "archived", False)):
            return record
        version = self.repository.get_latest_archived_published_version(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            for_update=True,
        )
        if version is None:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_RESTORE_VERSION_NOT_FOUND",
                message="未找到可恢复的已发布版本。",
                status_code=409,
                error_type="CONFLICT",
                suggestion="请确认该知识库曾成功发布后再恢复。",
            )
        version.status = KnowledgeVersionStatus.PUBLISHED
        record.current_version_id = int(version.id)
        record.draft_version_id = None
        record.publishing_version_id = None
        record.archived = False
        record.active = True
        record.publish_time = getattr(version, "publish_time", None)
        record.update_by = actor_id
        record.update_time = datetime.now()
        return record

    def set_workspace_enabled(
        self,
        *,
        knowledge_base_id: int,
        workspace_tenant_id: int,
        enabled: bool,
        actor_id: int | None,
        current_user: Any | None = None,
        reason: str | None = None,
    ):
        record = self.repository.lock_knowledge_base(
            tenant_id=DEFAULT_TENANT_ID, knowledge_base_id=knowledge_base_id
        )
        self._assert_not_archived(record)
        authorized_tenant_id = self.permissions.require_workspace_override(current_user, record)
        if int(authorized_tenant_id) != int(workspace_tenant_id):
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_TENANT_CONTEXT_MISMATCH",
                message="当前工作空间与请求上下文不一致。",
                status_code=403,
                error_type="FORBIDDEN",
            )
        return self.repository.upsert_workspace_override(
            tenant_id=workspace_tenant_id,
            knowledge_base_id=knowledge_base_id,
            enabled=enabled,
            actor_id=actor_id,
            reason=reason,
        )

    def _load_version(self, tenant_id: int, knowledge_base_id: int, version_id: int):
        version = self.repository.get_version(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            version_id=version_id,
            for_update=True,
        )
        if version is None:
            raise self._not_found()
        return version

    def _lock_document_draft(
        self,
        *,
        tenant_id: int,
        knowledge_base_id: int,
        draft_version_id: int,
        current_user: Any | None,
    ) -> tuple[Any, Any, DocumentPayload]:
        record = self.repository.lock_knowledge_base(
            tenant_id=tenant_id, knowledge_base_id=knowledge_base_id
        )
        self.permissions.require_manage(current_user, record)
        version = self._load_version(tenant_id, knowledge_base_id, draft_version_id)
        self._assert_editable(record, version, draft_version_id)
        parsed = KnowledgePayloadAdapter.validate_python(getattr(version, "payload", {}))
        if not isinstance(parsed, DocumentPayload):
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_DOCUMENT_OPERATION_UNSUPPORTED",
                message="只有普通文档支持知识块编辑。",
                status_code=422,
                error_type="VALIDATION",
            )
        return record, version, parsed

    def _persist_locked_document(
        self,
        *,
        record: Any,
        version: Any,
        payload: DocumentPayload,
        actor_id: int | None,
    ):
        saved = self.repository.update_locked_draft(
            version=version,
            payload=normalize_payload(payload),
            normalized_content=_normalized_content(payload),
            content_hash=content_hash_for_payload(payload),
            actor_id=actor_id,
        )
        record.draft_version_id = int(version.id)
        record.update_by = actor_id
        return saved

    @staticmethod
    def _block_conflict(payload: DocumentPayload, block: DocumentBlock) -> KnowledgeBusinessError:
        return KnowledgeBusinessError(
            code="KNOWLEDGE_DOCUMENT_BLOCK_CONFLICT",
            message="该知识块已被其他用户更新，本地内容已保留。",
            status_code=409,
            error_type="CONFLICT",
            suggestion="比较服务端与本地内容后，选择载入服务端或基于最新版本重试。",
            details={
                "conflict_type": "BLOCK",
                "block_id": block.id,
                "structure_revision": payload.structure_revision,
                "server_block": block.model_dump(mode="json"),
            },
        )

    def _assert_editable(self, record: Any, version: Any, version_id: int) -> None:
        self._assert_not_archived(record)
        if getattr(record, "draft_version_id", None) != version_id:
            raise self._draft_conflict()
        current_status = _status(version)
        if current_status == KnowledgeVersionStatus.PUBLISHING.value:
            raise self._publishing()
        if current_status == KnowledgeVersionStatus.VALIDATING.value:
            raise self._validating()
        if current_status not in {
            KnowledgeVersionStatus.DRAFT.value,
            KnowledgeVersionStatus.VALIDATION_FAILED.value,
            KnowledgeVersionStatus.READY_TO_PUBLISH.value,
            KnowledgeVersionStatus.PUBLISH_FAILED.value,
        }:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_VERSION_NOT_EDITABLE",
                message="当前版本不可编辑，请刷新后重试。",
                status_code=409,
                error_type="CONFLICT",
            )

    @staticmethod
    def _assert_not_archived(record: Any) -> None:
        if bool(getattr(record, "archived", False)):
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_ARCHIVED_READ_ONLY",
                message="归档知识库为只读，请先恢复后再修改。",
                status_code=409,
                error_type="CONFLICT",
            )

    @staticmethod
    def _draft_conflict() -> KnowledgeBusinessError:
        return KnowledgeBusinessError(
            code="KNOWLEDGE_DRAFT_CONFLICT",
            message="该知识已被其他用户更新，请刷新后重新编辑。",
            status_code=409,
            error_type="CONFLICT",
            suggestion="刷新后比较最新版本，再重新保存。",
        )

    @staticmethod
    def _draft_exists() -> KnowledgeBusinessError:
        return KnowledgeBusinessError(
            code="KNOWLEDGE_DRAFT_ALREADY_EXISTS",
            message="该知识已有未发布草稿，请先处理当前草稿后再回滚。",
            status_code=409,
            error_type="CONFLICT",
        )

    @staticmethod
    def _publishing() -> KnowledgeBusinessError:
        return KnowledgeBusinessError(
            code="KNOWLEDGE_PUBLISHING",
            message="该知识正在发布中，请稍后再试。",
            status_code=409,
            error_type="CONFLICT",
        )

    @staticmethod
    def _validating() -> KnowledgeBusinessError:
        return KnowledgeBusinessError(
            code="KNOWLEDGE_VALIDATING",
            message="该知识正在校验中，请稍后再试。",
            status_code=409,
            error_type="CONFLICT",
        )

    @staticmethod
    def _not_found() -> KnowledgeBusinessError:
        return KnowledgeBusinessError(
            code="KNOWLEDGE_NOT_FOUND",
            message="知识不存在或已被删除。",
            status_code=404,
            error_type="NOT_FOUND",
        )


def _normalized_content(payload: KnowledgePayload) -> str:
    normalized = normalize_payload(payload)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
