"""Phase-aware list/detail/delete management routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import select

from apps.datasource.crud.permission_scope import (
    PermissionScopeService,
    PermissionScopeUnavailableError,
)
from apps.knowledge_base.api._helpers import (
    record_tenant_id,
    resolve_record,
    serialize_error,
    serialize_record,
    unexpected_error,
    visible_tenant_ids,
)
from apps.knowledge_base.api.knowledge_base import (
    delete_legacy_knowledge_base,
    list_legacy_knowledge_base,
)
from apps.knowledge_base.cutover import get_capabilities
from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.lifecycle_service import KnowledgeLifecycleService
from apps.knowledge_base.models import KnowledgeBase
from apps.knowledge_base.permissions import KnowledgePermissionService
from apps.knowledge_base.retrieval import KnowledgeRetrievalService
from apps.knowledge_base.version_repository import KnowledgeVersionRepository
from apps.system.schemas.access_context import current_tenant_id
from common.core.deps import CurrentUser, SessionDep

router = APIRouter(
    tags=["KnowledgeBase"],
    prefix="/knowledge-base",
    include_in_schema=False,
)


class RetrievalPreviewRequest(BaseModel):
    datasource_id: int
    query: str = Field(min_length=1, max_length=4000)
    surface: str = Field(default="RETRIEVAL_PREVIEW", max_length=64)
    top_k: int | None = Field(default=None, ge=1, le=20)
    max_context_chars: int | None = Field(default=None, ge=100, le=50000)


@router.post("/retrieval-preview")
async def retrieval_preview(
    body: RetrievalPreviewRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    tenant_id = current_tenant_id(current_user)
    if tenant_id is None:
        return serialize_error(
            KnowledgeBusinessError(
                code="KNOWLEDGE_PERMISSION_CONTEXT_INVALID",
                message="当前工作空间上下文无效，请重新进入工作空间。",
                status_code=400,
                error_type="VALIDATION",
            )
        )
    try:
        snapshot = PermissionScopeService.build_snapshot(
            session=session,
            current_user=current_user,
            tenant_id=int(tenant_id),
            datasource_id=int(body.datasource_id),
        )
        result = KnowledgeRetrievalService().search(
            session=session,
            tenant_id=int(tenant_id),
            datasource_id=int(body.datasource_id),
            surface=body.surface,
            query=body.query,
            permission_snapshot=snapshot,
            top_k=body.top_k,
            max_context_chars=body.max_context_chars,
        )
        return {
            "query_hash": result.query_hash,
            "model_signature": result.model_signature,
            "context": result.context,
            "citations": [
                {
                    "chunk_id": item.chunk_id,
                    "knowledge_base_id": item.knowledge_base_id,
                    "version_id": item.version_id,
                    "section_path": item.section_path,
                    "score": item.score,
                    "content": item.content,
                    "visibility_scope": item.visibility_scope,
                }
                for item in result.citations
            ],
            "warnings": list(result.warnings),
            "failure_type": result.failure_type,
            "latency_ms": result.latency_ms,
        }
    except PermissionScopeUnavailableError as exc:
        return serialize_error(
            KnowledgeBusinessError(
                code="KNOWLEDGE_PERMISSION_CONTEXT_INVALID",
                message=str(exc) or "权限上下文不可用，请刷新后重试。",
                status_code=409,
                error_type="CONFLICT",
            )
        )
    except KnowledgeBusinessError as error:
        return serialize_error(error)
    except Exception:
        return unexpected_error()


@router.get("/capabilities")
async def knowledge_capabilities(session: SessionDep, current_user: CurrentUser):
    _ = current_user
    capabilities = get_capabilities(session)
    return {
        "phase": capabilities.phase.value,
        "management_mode": capabilities.management_mode,
        "legacy_write_enabled": capabilities.legacy_write_enabled,
        "v2_write_enabled": capabilities.v2_write_enabled,
        "runtime_context_enabled": capabilities.runtime_context_enabled,
    }


@router.get("/list")
async def list_knowledge_base(
    session: SessionDep,
    current_user: CurrentUser,
    visibility_scope: str | None = None,
    keyword: str | None = None,
):
    capabilities = get_capabilities(session)
    if capabilities.phase.value != "V2_ACTIVE":
        return await list_legacy_knowledge_base(
            session=session,
            current_user=current_user,
            visibility_scope=visibility_scope,
            keyword=keyword,
        )
    try:
        filters = [
            KnowledgeBase.tenant_id.in_(visible_tenant_ids(current_user)),
            KnowledgeBase.archived.is_(False),
        ]
        if visibility_scope:
            filters.append(KnowledgeBase.visibility_scope == visibility_scope)
        value = (keyword or "").strip()
        if value:
            pattern = f"%{value}%"
            filters.append(
                KnowledgeBase.name.ilike(pattern)
                | KnowledgeBase.description.ilike(pattern)
            )
        rows = session.exec(
            select(KnowledgeBase)
            .where(*filters)
            .order_by(KnowledgeBase.update_time.desc(), KnowledgeBase.id.desc())
        ).all()
        permission = KnowledgePermissionService()
        result = []
        for row in rows:
            try:
                permission.require_read(current_user, row)
            except KnowledgeBusinessError:
                continue
            try:
                permission.require_manage(current_user, row)
            except KnowledgeBusinessError:
                can_manage = False
            else:
                can_manage = True
            result.append(serialize_record(row, can_manage=can_manage))
        return result
    except KnowledgeBusinessError as error:
        return serialize_error(error)
    except Exception:
        return unexpected_error()


@router.get("/{id}")
async def get_knowledge_base_detail(
    id: int,
    session: SessionDep,
    current_user: CurrentUser,
):
    capabilities = get_capabilities(session)
    if capabilities.phase.value != "V2_ACTIVE":
        return serialize_error(
            KnowledgeBusinessError(
                code="KNOWLEDGE_V2_NOT_READY",
                message="知识库管理尚未升级完成，请稍后重试。",
                status_code=409,
                error_type="CONFLICT",
            )
        )
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        permission = KnowledgePermissionService()
        try:
            permission.require_manage(current_user, record)
        except KnowledgeBusinessError:
            can_manage = False
        else:
            can_manage = True
        return serialize_record(record, can_manage=can_manage)
    except KnowledgeBusinessError as error:
        return serialize_error(error)
    except Exception:
        return unexpected_error()


@router.delete("/{id}")
async def delete_knowledge_base(
    id: int,
    session: SessionDep,
    current_user: CurrentUser,
):
    capabilities = get_capabilities(session)
    if capabilities.phase.value != "V2_ACTIVE":
        return await delete_legacy_knowledge_base(
            session=session, current_user=current_user, id=id
        )
    from apps.knowledge_base.api._helpers import v2_write_error

    blocked = v2_write_error(capabilities)
    if blocked is not None:
        return serialize_error(blocked)
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        tenant_id = record_tenant_id(record, current_user)
        service = KnowledgeLifecycleService(KnowledgeVersionRepository(session))
        result = service.archive_or_delete(
            tenant_id=tenant_id,
            knowledge_base_id=id,
            actor_id=int(current_user.id),
            current_user=current_user,
        )
        session.commit()
        return {"id": id, "archived": result is not None}
    except KnowledgeBusinessError as error:
        session.rollback()
        return serialize_error(error)
    except Exception:
        session.rollback()
        return unexpected_error()
