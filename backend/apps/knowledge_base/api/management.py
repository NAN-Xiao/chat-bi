"""Phase-aware list/detail/delete management routes."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

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
    validate_workspace_tenant,
    visible_tenant_ids,
)
from apps.knowledge_base.api.knowledge_base import (
    delete_legacy_knowledge_base,
    list_legacy_knowledge_base,
)
from apps.knowledge_base.audit import new_request_id, write_retrieval_audit
from apps.knowledge_base.cutover import get_capabilities
from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.lifecycle_models import (
    KnowledgeBaseVersion,
    KnowledgeVersionStatus,
)
from apps.knowledge_base.lifecycle_service import KnowledgeLifecycleService
from apps.knowledge_base.models import (
    KnowledgeBase,
    KnowledgeBaseStatusEnum,
    KnowledgeBaseVisibilityScopeEnum,
)
from apps.knowledge_base.permissions import KnowledgePermissionService
from apps.knowledge_base.retrieval import KnowledgeRetrievalService
from apps.knowledge_base.retrieval_models import (
    KnowledgeApplicabilityStatus,
    KnowledgeBaseApplicability,
)
from apps.knowledge_base.source_file_cleanup import cleanup_unreferenced_source_files
from apps.knowledge_base.version_repository import KnowledgeVersionRepository
from apps.system.crud.tenant import DEFAULT_TENANT_ID
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


class CreateKnowledgeBaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    visibility_scope: KnowledgeBaseVisibilityScopeEnum = KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC
    tenant_id: int | None = Field(default=None, ge=1)
    knowledge_type: str = "DOCUMENT"


class SetKnowledgeBaseActiveRequest(BaseModel):
    active: bool


def _applicability_response(*, knowledge_base_id: int, datasource_id: int, schema_hash: str, row=None, version_id: int | None = None):
    status = getattr(row, "status", None) if row is not None else KnowledgeApplicabilityStatus.STALE.value
    status = getattr(status, "value", status) or KnowledgeApplicabilityStatus.STALE.value
    report = getattr(row, "report", None) if row is not None else None
    report = report if isinstance(report, dict) else {}
    reference_statuses = report.get("reference_statuses")
    if not isinstance(reference_statuses, list):
        reference_statuses = []
    resolved_count = sum(1 for item in reference_statuses if isinstance(item, dict) and item.get("status") == "RESOLVED")
    warnings = report.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    if not warnings:
        warnings = {
            KnowledgeApplicabilityStatus.INVALID.value: ["存在未解析、歧义或被当前工作空间停用的对象引用。"],
            KnowledgeApplicabilityStatus.STALE.value: ["当前数据源尚未完成适用性检查。"],
            KnowledgeApplicabilityStatus.ERROR.value: ["适用性检查失败，当前知识暂不可确认是否适用。"],
        }.get(status, [])
    return {
        "knowledge_base_id": int(knowledge_base_id),
        "version_id": int(version_id) if version_id is not None else None,
        "datasource_id": int(datasource_id),
        "status": status,
        "status_text": {
            KnowledgeApplicabilityStatus.VALID.value: "可用",
            KnowledgeApplicabilityStatus.INVALID.value: "不适用",
            KnowledgeApplicabilityStatus.STALE.value: "待检查",
            KnowledgeApplicabilityStatus.ERROR.value: "检查失败",
        }.get(status, "待检查"),
        "schema_hash_prefix": str(schema_hash or "")[:12] or None,
        "reference_count": len(reference_statuses),
        "resolved_count": resolved_count,
        "warnings": [str(item) for item in warnings if str(item).strip()][:10],
        "checked_at": getattr(row, "checked_at", None) if row is not None else None,
    }


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
        request_id = new_request_id()
        retrieval = KnowledgeRetrievalService(
            audit_writer=lambda **kwargs: write_retrieval_audit(
                session=session,
                request_id=request_id,
                surface=body.surface,
                snapshot=snapshot,
                result=kwargs["result"],
                user_id=getattr(current_user, "id", None),
            )
        )
        result = retrieval.search(
            session=session,
            tenant_id=int(tenant_id),
            datasource_id=int(body.datasource_id),
            surface=body.surface,
            query=body.query,
            permission_snapshot=snapshot,
            top_k=body.top_k,
            max_context_chars=body.max_context_chars,
            request_id=request_id,
            user_id=getattr(current_user, "id", None),
        )
        return {
            "query_hash": result.query_hash,
            "model_signature": result.model_signature,
            "context": result.context,
            "citations": [
                {
                    "chunk_id": item.chunk_id,
                    "knowledge_base_id": item.knowledge_base_id,
                    "knowledge_base_name": item.knowledge_base_name,
                    "version_id": item.version_id,
                    "version_number": item.version_number,
                    "section_path": item.section_path,
                    "source_block_id": item.source_block_id,
                    "source_file_name": item.source_file_name,
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


@router.get("/{id}/applicability")
async def knowledge_applicability(
    id: int,
    datasource_id: int,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Return the last applicability result for the active workspace datasource."""
    try:
        tenant_id = current_tenant_id(current_user)
        if tenant_id is None:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_PERMISSION_CONTEXT_INVALID",
                message="当前未进入工作空间，无法检查知识适用性。",
                status_code=400,
                error_type="VALIDATION",
            )
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        version_id = int(record.current_version_id) if record.current_version_id else None
        snapshot = PermissionScopeService.build_snapshot(
            session=session,
            current_user=current_user,
            tenant_id=int(tenant_id),
            datasource_id=int(datasource_id),
        )
        if version_id is None:
            return _applicability_response(
                knowledge_base_id=id,
                datasource_id=int(datasource_id),
                schema_hash=snapshot.schema_hash,
            )
        version = session.get(KnowledgeBaseVersion, version_id)
        if version is None or version.status != KnowledgeVersionStatus.PUBLISHED.value:
            return _applicability_response(
                knowledge_base_id=id,
                datasource_id=int(datasource_id),
                schema_hash=snapshot.schema_hash,
                version_id=version_id,
            )
        row = session.exec(
            select(KnowledgeBaseApplicability).where(
                KnowledgeBaseApplicability.knowledge_base_id == int(id),
                KnowledgeBaseApplicability.version_id == int(version_id),
                KnowledgeBaseApplicability.tenant_id == int(tenant_id),
                KnowledgeBaseApplicability.datasource_id == int(datasource_id),
                KnowledgeBaseApplicability.physical_schema_hash == snapshot.schema_hash,
            )
        ).first()
        return _applicability_response(
            knowledge_base_id=id,
            datasource_id=int(datasource_id),
            schema_hash=snapshot.schema_hash,
            row=row,
            version_id=version_id,
        )
    except PermissionScopeUnavailableError as exc:
        return serialize_error(
            KnowledgeBusinessError(
                code="KNOWLEDGE_PERMISSION_CONTEXT_INVALID",
                message=str(exc) or "当前数据源权限上下文不可用，请刷新后重试。",
                status_code=409,
                error_type="CONFLICT",
            )
        )
    except KnowledgeBusinessError as error:
        return serialize_error(error)
    except Exception:
        return unexpected_error()


@router.post("/create")
async def create_knowledge_base(
    body: CreateKnowledgeBaseRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    capabilities = get_capabilities(session)
    from apps.knowledge_base.api._helpers import v2_write_error

    blocked = v2_write_error(capabilities)
    if blocked is not None:
        return serialize_error(blocked)
    try:
        clean_name = body.name.strip()
        if not clean_name:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_NAME_REQUIRED",
                message="知识库名称不能为空。",
                status_code=422,
                error_type="VALIDATION",
            )
        scope = KnowledgeBaseVisibilityScopeEnum(body.visibility_scope)
        knowledge_type = str(body.knowledge_type or "").strip().upper()
        if knowledge_type not in {"DOCUMENT", "BUSINESS", "EVENT", "JSON_FIELD"}:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_TYPE_INVALID",
                message="知识类型不受支持。",
                status_code=422,
                field_path="knowledge_type",
                error_type="VALIDATION",
            )
        if scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC and body.tenant_id is not None:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_WORKSPACE_NOT_APPLICABLE",
                message="平台知识库不能指定工作空间。",
                status_code=400,
                error_type="VALIDATION",
            )
        if scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC:
            target_tenant_id = DEFAULT_TENANT_ID
        else:
            if (
                KnowledgePermissionService().is_global_platform_admin(current_user)
                and body.tenant_id is None
            ):
                raise KnowledgeBusinessError(
                    code="KNOWLEDGE_WORKSPACE_REQUIRED",
                    message="请选择要管理的工作空间。",
                    status_code=400,
                    error_type="VALIDATION",
                )
            target_tenant_id = int(body.tenant_id or current_tenant_id(current_user) or 0)
            visible_tenant_ids(current_user, target_tenant_id)
            target_tenant_id = validate_workspace_tenant(session, target_tenant_id)
        record = KnowledgeBase(
            tenant_id=target_tenant_id,
            create_by=int(current_user.id),
            update_by=int(current_user.id),
            name=clean_name,
            description=body.description.strip() or None,
            visibility_scope=scope,
            active=True,
            status=KnowledgeBaseStatusEnum.PENDING,
            stable_key=f"kb-{uuid4().hex}",
            knowledge_type=knowledge_type,
            create_time=datetime.utcnow(),
            update_time=datetime.utcnow(),
        )
        KnowledgePermissionService().require_manage(current_user, record)
        session.add(record)
        session.commit()
        session.refresh(record)
        return serialize_record(record, can_manage=True)
    except KnowledgeBusinessError as error:
        session.rollback()
        return serialize_error(error)
    except Exception:
        session.rollback()
        return unexpected_error()


@router.get("/list")
async def list_knowledge_base(
    session: SessionDep,
    current_user: CurrentUser,
    visibility_scope: str | None = None,
    keyword: str | None = None,
    tenant_id: int | None = None,
    archived: bool = False,
):
    capabilities = get_capabilities(session)
    if capabilities.phase.value != "V2_ACTIVE":
        if archived:
            return []
        return await list_legacy_knowledge_base(
            session=session,
            current_user=current_user,
            visibility_scope=visibility_scope,
            keyword=keyword,
            tenant_id=tenant_id,
        )
    try:
        if tenant_id is not None and visibility_scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC.value:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_WORKSPACE_NOT_APPLICABLE",
                message="平台知识库不能指定工作空间。",
                status_code=400,
                error_type="VALIDATION",
            )
        permission = KnowledgePermissionService()
        if (
            visibility_scope == KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC.value
            and permission.is_global_platform_admin(current_user)
            and tenant_id is None
        ):
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_WORKSPACE_REQUIRED",
                message="请选择要管理的工作空间。",
                status_code=400,
                error_type="VALIDATION",
            )
        tenant_ids = visible_tenant_ids(current_user, tenant_id)
        if tenant_id is not None:
            validate_workspace_tenant(session, int(tenant_id))
        filters = [
            KnowledgeBase.tenant_id.in_(tenant_ids),
            KnowledgeBase.archived.is_(archived),
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


@router.post("/{id}/restore")
async def restore_knowledge_base(
    id: int,
    session: SessionDep,
    current_user: CurrentUser,
):
    capabilities = get_capabilities(session)
    from apps.knowledge_base.api._helpers import v2_write_error

    blocked = v2_write_error(capabilities)
    if blocked is not None:
        return serialize_error(blocked)
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        tenant_id = record_tenant_id(record, current_user)
        restored = KnowledgeLifecycleService(KnowledgeVersionRepository(session)).restore(
            tenant_id=tenant_id,
            knowledge_base_id=id,
            actor_id=int(current_user.id),
            current_user=current_user,
        )
        session.commit()
        return serialize_record(restored, can_manage=True)
    except KnowledgeBusinessError as error:
        session.rollback()
        return serialize_error(error)
    except Exception:
        session.rollback()
        return unexpected_error()


@router.put("/{id}/active")
async def set_knowledge_base_active(
    id: int,
    body: SetKnowledgeBaseActiveRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    capabilities = get_capabilities(session)
    from apps.knowledge_base.api._helpers import v2_write_error

    blocked = v2_write_error(capabilities)
    if blocked is not None:
        return serialize_error(blocked)
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        tenant_id = record_tenant_id(record, current_user)
        updated = KnowledgeLifecycleService(KnowledgeVersionRepository(session)).set_active(
            tenant_id=tenant_id,
            knowledge_base_id=id,
            active=body.active,
            actor_id=int(current_user.id),
            current_user=current_user,
        )
        session.commit()
        return serialize_record(updated, can_manage=True)
    except KnowledgeBusinessError as error:
        session.rollback()
        return serialize_error(error)
    except Exception:
        session.rollback()
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
        cleanup = cleanup_unreferenced_source_files(session, result.source_file_ids)
        return {
            "id": id,
            "archived": result.archived,
            "deleted": not result.archived,
            "file_cleanup": cleanup.as_counts(),
        }
    except KnowledgeBusinessError as error:
        session.rollback()
        return serialize_error(error)
    except Exception:
        session.rollback()
        return unexpected_error()


@router.delete("/{id}/permanent")
async def permanently_delete_knowledge_base(
    id: int,
    session: SessionDep,
    current_user: CurrentUser,
):
    capabilities = get_capabilities(session)
    from apps.knowledge_base.api._helpers import v2_write_error

    blocked = v2_write_error(capabilities)
    if blocked is not None:
        return serialize_error(blocked)
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        tenant_id = record_tenant_id(record, current_user)
        result = KnowledgeLifecycleService(
            KnowledgeVersionRepository(session)
        ).permanently_delete_archived(
            tenant_id=tenant_id,
            knowledge_base_id=id,
            current_user=current_user,
        )
        session.commit()
        cleanup = cleanup_unreferenced_source_files(session, result.source_file_ids)
        return {
            "id": id,
            "archived": False,
            "deleted": True,
            "file_cleanup": cleanup.as_counts(),
        }
    except KnowledgeBusinessError as error:
        session.rollback()
        return serialize_error(error)
    except Exception:
        session.rollback()
        return unexpected_error()
