"""V2 draft, validation, version-history, rollback, and override routes."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import select

from apps.knowledge_base.api._helpers import (
    record_tenant_id,
    resolve_record,
    serialize_error,
    unexpected_error,
    v2_write_error,
)
from apps.knowledge_base.api.knowledge_base import (
    ALLOWED_EXTENSIONS,
    KNOWLEDGE_FILE_MAX_BYTES,
)
from apps.knowledge_base.cutover import get_capabilities
from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.lifecycle_models import KnowledgeBaseVersion
from apps.knowledge_base.lifecycle_service import KnowledgeLifecycleService
from apps.knowledge_base.schemas import KnowledgePayloadAdapter
from apps.knowledge_base.version_repository import (
    KnowledgeVersionRepository,
    SourceFileRef,
)
from common.core.config import settings
from common.core.deps import CurrentUser, SessionDep
from common.utils.file_utils import AppFileUtils

router = APIRouter(
    tags=["KnowledgeBase"],
    prefix="/knowledge-base",
    include_in_schema=False,
)


class DraftPayloadRequest(BaseModel):
    payload: dict[str, Any]


class SaveDraftRequest(DraftPayloadRequest):
    version_id: int
    revision: int = Field(ge=1)


class ValidateDraftRequest(BaseModel):
    version_id: int
    revision: int = Field(ge=1)
    content_hash: str
    context: dict[str, Any] = Field(default_factory=dict)


class RollbackRequest(BaseModel):
    version_id: int


class WorkspaceEnabledRequest(BaseModel):
    enabled: bool
    reason: str | None = None


def _payload(value: dict[str, Any]):
    try:
        return KnowledgePayloadAdapter.validate_python(value)
    except ValidationError as exc:
        raise KnowledgeBusinessError(
            code="KNOWLEDGE_PAYLOAD_INVALID",
            message="知识内容格式不正确，请修正后重新提交。",
            status_code=422,
            error_type="VALIDATION",
            suggestion="检查 knowledge_type 和对应类型的必填字段。",
        ) from exc


def _context(value: dict[str, Any]):
    from apps.knowledge_base.validators import ValidationContext

    return ValidationContext(
        dialect=str(value.get("dialect") or "postgres"),
        tables=value.get("tables") or {},
        json_paths=value.get("json_paths") or {},
        event_names=value.get("event_names") or (),
    )


def _version_response(version: KnowledgeBaseVersion) -> dict[str, Any]:
    return {
        "id": int(version.id),
        "knowledge_base_id": int(version.knowledge_base_id),
        "tenant_id": int(version.tenant_id),
        "version_number": int(version.version_number),
        "revision": int(version.revision),
        "status": getattr(version.status, "value", version.status),
        "index_status": getattr(version.index_status, "value", version.index_status),
        "payload": version.payload,
        "normalized_content": version.normalized_content,
        "validation_report": version.validation_report,
        "content_hash": version.content_hash,
        "file_name": version.file_name,
        "file_ext": version.file_ext,
        "parser_version": version.parser_version,
    }


@router.post("/{id}/draft")
async def create_draft(
    id: int,
    body: DraftPayloadRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    capabilities = get_capabilities(session)
    blocked = v2_write_error(capabilities)
    if blocked is not None:
        return serialize_error(blocked)
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        payload = _payload(body.payload)
        tenant_id = record_tenant_id(record, current_user)
        service = KnowledgeLifecycleService(KnowledgeVersionRepository(session))
        version = service.create_draft(
            tenant_id=tenant_id,
            knowledge_base_id=id,
            payload=payload,
            actor_id=int(current_user.id),
            current_user=current_user,
        )
        session.commit()
        return _version_response(version)
    except KnowledgeBusinessError as error:
        session.rollback()
        return serialize_error(error)
    except Exception:
        session.rollback()
        return unexpected_error()


@router.put("/{id}/draft")
async def save_draft(
    id: int,
    body: SaveDraftRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    capabilities = get_capabilities(session)
    blocked = v2_write_error(capabilities)
    if blocked is not None:
        return serialize_error(blocked)
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        payload = _payload(body.payload)
        tenant_id = record_tenant_id(record, current_user)
        version = KnowledgeLifecycleService(KnowledgeVersionRepository(session)).save_draft(
            tenant_id=tenant_id,
            knowledge_base_id=id,
            draft_version_id=body.version_id,
            revision=body.revision,
            payload=payload,
            actor_id=int(current_user.id),
            current_user=current_user,
        )
        session.commit()
        return _version_response(version)
    except KnowledgeBusinessError as error:
        session.rollback()
        return serialize_error(error)
    except Exception:
        session.rollback()
        return unexpected_error()


@router.post("/{id}/draft/file")
async def replace_draft_source_file(
    id: int,
    session: SessionDep,
    current_user: CurrentUser,
    version_id: int = Form(...),
    revision: int = Form(...),
    file: UploadFile = File(...),
):
    """Stage a source file before the draft CAS; old version files stay intact."""
    capabilities = get_capabilities(session)
    blocked = v2_write_error(capabilities)
    if blocked is not None:
        return serialize_error(blocked)
    staged_file_id: str | None = None
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        tenant_id = record_tenant_id(record, current_user)
        version = session.exec(
            select(KnowledgeBaseVersion).where(
                KnowledgeBaseVersion.id == version_id,
                KnowledgeBaseVersion.knowledge_base_id == id,
                KnowledgeBaseVersion.tenant_id == tenant_id,
            )
        ).first()
        if version is None:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_VERSION_NOT_FOUND",
                message="知识版本不存在。",
                status_code=404,
                error_type="NOT_FOUND",
            )
        try:
            extension = AppFileUtils.validate_extension(file.filename, ALLOWED_EXTENSIONS)
        except Exception as exc:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_SOURCE_FILE_INVALID",
                message="源文件格式不支持。",
                status_code=422,
                error_type="VALIDATION",
                suggestion="请上传 Markdown 或 Word 文档。",
            ) from exc
        staged_file_id = f".knowledge-stage-{uuid.uuid4().hex}{extension}"
        staged_path = AppFileUtils.safe_path(settings.UPLOAD_DIR, staged_file_id)
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_bytes(
            await AppFileUtils.read_upload_limited(
                file,
                limit_file_size=KNOWLEDGE_FILE_MAX_BYTES,
            )
        )
        payload = KnowledgePayloadAdapter.validate_python(version.payload)
        saved = KnowledgeLifecycleService(KnowledgeVersionRepository(session)).save_draft(
            tenant_id=tenant_id,
            knowledge_base_id=id,
            draft_version_id=version_id,
            revision=revision,
            payload=payload,
            actor_id=int(current_user.id),
            current_user=current_user,
            source_file=SourceFileRef(
                file_id=staged_file_id,
                file_name=Path(file.filename or staged_file_id).name,
                file_ext=extension,
            ),
        )
        session.commit()
        return _version_response(saved)
    except KnowledgeBusinessError as error:
        session.rollback()
        if staged_file_id:
            AppFileUtils.delete_file(staged_file_id)
        return serialize_error(error)
    except Exception:
        session.rollback()
        if staged_file_id:
            AppFileUtils.delete_file(staged_file_id)
        return unexpected_error()


@router.post("/{id}/draft/validate")
async def validate_draft(
    id: int,
    body: ValidateDraftRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    capabilities = get_capabilities(session)
    blocked = v2_write_error(capabilities)
    if blocked is not None:
        return serialize_error(blocked)
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        tenant_id = record_tenant_id(record, current_user)
        version = KnowledgeLifecycleService(KnowledgeVersionRepository(session)).validate_draft(
            tenant_id=tenant_id,
            knowledge_base_id=id,
            draft_version_id=body.version_id,
            revision=body.revision,
            content_hash=body.content_hash,
            actor_id=int(current_user.id),
            current_user=current_user,
            context=_context(body.context),
        )
        session.commit()
        return _version_response(version)
    except KnowledgeBusinessError as error:
        session.rollback()
        return serialize_error(error)
    except Exception:
        session.rollback()
        return unexpected_error()


@router.get("/{id}/versions")
async def list_versions(
    id: int,
    session: SessionDep,
    current_user: CurrentUser,
):
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        tenant_id = record_tenant_id(record, current_user)
        rows = session.exec(
            select(KnowledgeBaseVersion)
            .where(
                KnowledgeBaseVersion.knowledge_base_id == id,
                KnowledgeBaseVersion.tenant_id == tenant_id,
            )
            .order_by(KnowledgeBaseVersion.version_number.desc())
        ).all()
        return [_version_response(row) for row in rows]
    except KnowledgeBusinessError as error:
        return serialize_error(error)
    except Exception:
        return unexpected_error()


@router.get("/{id}/versions/{version_id}")
async def get_version(
    id: int,
    version_id: int,
    session: SessionDep,
    current_user: CurrentUser,
):
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        tenant_id = record_tenant_id(record, current_user)
        version = session.exec(
            select(KnowledgeBaseVersion).where(
                KnowledgeBaseVersion.id == version_id,
                KnowledgeBaseVersion.knowledge_base_id == id,
                KnowledgeBaseVersion.tenant_id == tenant_id,
            )
        ).first()
        if version is None:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_VERSION_NOT_FOUND",
                message="知识版本不存在。",
                status_code=404,
                error_type="NOT_FOUND",
            )
        return _version_response(version)
    except KnowledgeBusinessError as error:
        return serialize_error(error)
    except Exception:
        return unexpected_error()


@router.get("/{id}/versions/{version_id}/download")
async def download_version_source(
    id: int,
    version_id: int,
    session: SessionDep,
    current_user: CurrentUser,
):
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        tenant_id = record_tenant_id(record, current_user)
        version = session.exec(
            select(KnowledgeBaseVersion).where(
                KnowledgeBaseVersion.id == version_id,
                KnowledgeBaseVersion.knowledge_base_id == id,
                KnowledgeBaseVersion.tenant_id == tenant_id,
            )
        ).first()
        if version is None or not version.file_id:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_SOURCE_FILE_NOT_FOUND",
                message="知识源文件不存在。",
                status_code=404,
                error_type="NOT_FOUND",
            )
        file_path = AppFileUtils.safe_path(settings.UPLOAD_DIR, version.file_id)
        if not file_path.is_file():
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_SOURCE_FILE_NOT_FOUND",
                message="知识源文件不存在。",
                status_code=404,
                error_type="NOT_FOUND",
            )
        file_name = Path(version.file_name or version.file_id).name
        return FileResponse(
            path=file_path,
            filename=file_name,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file_name)}"
            },
        )
    except KnowledgeBusinessError as error:
        return serialize_error(error)
    except Exception:
        return unexpected_error()


@router.post("/{id}/rollback")
async def rollback_draft(
    id: int,
    body: RollbackRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    capabilities = get_capabilities(session)
    blocked = v2_write_error(capabilities)
    if blocked is not None:
        return serialize_error(blocked)
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        tenant_id = record_tenant_id(record, current_user)
        version = KnowledgeLifecycleService(KnowledgeVersionRepository(session)).rollback_to_new_draft(
            tenant_id=tenant_id,
            knowledge_base_id=id,
            target_version_id=body.version_id,
            actor_id=int(current_user.id),
            current_user=current_user,
        )
        session.commit()
        return _version_response(version)
    except KnowledgeBusinessError as error:
        session.rollback()
        return serialize_error(error)
    except Exception:
        session.rollback()
        return unexpected_error()


@router.put("/{id}/workspace-enabled")
async def set_workspace_enabled(
    id: int,
    body: WorkspaceEnabledRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    capabilities = get_capabilities(session)
    blocked = v2_write_error(capabilities)
    if blocked is not None:
        return serialize_error(blocked)
    try:
        from apps.system.schemas.access_context import require_current_tenant_id

        workspace_tenant_id = require_current_tenant_id(current_user)
        override = KnowledgeLifecycleService(KnowledgeVersionRepository(session)).set_workspace_enabled(
            knowledge_base_id=id,
            workspace_tenant_id=workspace_tenant_id,
            enabled=body.enabled,
            actor_id=int(current_user.id),
            current_user=current_user,
            reason=body.reason,
        )
        session.commit()
        return {
            "knowledge_base_id": id,
            "tenant_id": workspace_tenant_id,
            "enabled": bool(override.enabled),
            "reason": override.reason,
        }
    except KnowledgeBusinessError as error:
        session.rollback()
        return serialize_error(error)
    except Exception:
        session.rollback()
        return unexpected_error()
