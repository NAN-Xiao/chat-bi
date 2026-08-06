"""Application service for draft, validation, rollback, and archive transitions."""

from __future__ import annotations

import json
from typing import Any, Protocol

from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.lifecycle_models import KnowledgeVersionStatus
from apps.knowledge_base.normalizers import content_hash_for_payload, normalize_payload
from apps.knowledge_base.permissions import KnowledgePermissionService
from apps.knowledge_base.schemas import KnowledgePayload, KnowledgePayloadAdapter
from apps.knowledge_base.validators import ValidationContext, validate_payload
from apps.knowledge_base.version_repository import SourceFileRef
from apps.system.crud.tenant import DEFAULT_TENANT_ID


class LifecycleRepository(Protocol):
    def get_knowledge_base(self, *, tenant_id: int, knowledge_base_id: int): ...
    def lock_knowledge_base(self, *, tenant_id: int, knowledge_base_id: int): ...
    def get_version(self, *, tenant_id: int, knowledge_base_id: int, version_id: int, for_update: bool = False): ...
    def get_active_draft(self, *, tenant_id: int, knowledge_base_id: int, for_update: bool = False): ...
    def add_draft(self, **kwargs): ...
    def save_draft_if_revision_matches(self, **kwargs): ...
    def mark_validating_if_revision_matches(self, **kwargs): ...
    def set_validation_state_if_revision_matches(self, **kwargs): ...
    def upsert_workspace_override(self, **kwargs): ...
    def delete_unpublished(self, **kwargs): ...


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
                        "suggestion": "检查知识类型和必填字段。",
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
                self.repository.delete_unpublished(record=record)
                return None
            # Archiving is an explicit discard boundary for an unpublished draft.
            active.status = KnowledgeVersionStatus.ARCHIVED
            record.draft_version_id = None
        if bool(getattr(record, "archived", False)):
            return record
        if current_id is None:
            self.repository.delete_unpublished(record=record)
            return None
        current = self._load_version(tenant_id, knowledge_base_id, int(current_id))
        current.status = KnowledgeVersionStatus.ARCHIVED
        record.current_version_id = None
        record.draft_version_id = None
        record.publishing_version_id = None
        record.archived = True
        record.active = False
        record.update_by = actor_id
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

    def _assert_editable(self, record: Any, version: Any, version_id: int) -> None:
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
