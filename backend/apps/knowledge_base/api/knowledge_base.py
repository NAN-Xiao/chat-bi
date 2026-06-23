from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import desc, or_
from sqlmodel import select

from apps.knowledge_base.models import (
    KnowledgeBase,
    KnowledgeBaseItem,
    KnowledgeBaseStatusEnum,
    KnowledgeBaseVisibilityScopeEnum,
)
from apps.knowledge_base.tasks import process_knowledge_base_document
from apps.system.crud.tenant import DEFAULT_TENANT_ID, TENANT_ADMIN_ROLES, normalize_tenant_role
from apps.system.crud.user import is_platform_admin, is_platform_workspace_delegate
from apps.system.schemas.access_context import require_current_tenant_id
from common.core.config import settings
from common.core.deps import CurrentUser, SessionDep
from common.core.task_queue import enqueue_task
from common.core.task_registry import register_builtin_tasks
from common.utils.file_utils import AppFileUtils

router = APIRouter(tags=["KnowledgeBase"], prefix="/knowledge-base", include_in_schema=False)

ALLOWED_EXTENSIONS = {".md", ".markdown", ".docx"}
KNOWLEDGE_FILE_MAX_BYTES = 50 * 1024 * 1024


def _now() -> datetime:
    return datetime.now()


def _parse_scope(value: Optional[str]) -> KnowledgeBaseVisibilityScopeEnum:
    try:
        return KnowledgeBaseVisibilityScopeEnum(value or KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unsupported knowledge base visibility scope") from exc


def _is_global_platform_admin(current_user: CurrentUser) -> bool:
    return is_platform_admin(current_user) and not is_platform_workspace_delegate(current_user)


def _can_manage_workspace_public(current_user: CurrentUser) -> bool:
    if _is_global_platform_admin(current_user):
        return False
    tenant_role = normalize_tenant_role(getattr(current_user, "tenant_role", None))
    return is_platform_admin(current_user) or tenant_role in TENANT_ADMIN_ROLES


def _scope_tenant_id(current_user: CurrentUser, scope: KnowledgeBaseVisibilityScopeEnum) -> int:
    if scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC:
        return DEFAULT_TENANT_ID
    return require_current_tenant_id(current_user)


def _require_scope_manage(current_user: CurrentUser, scope: KnowledgeBaseVisibilityScopeEnum) -> None:
    if scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC:
        if not _is_global_platform_admin(current_user):
            raise HTTPException(status_code=403, detail="Only SaaS admin can maintain SaaS knowledge base")
        return
    if scope == KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC:
        if not _can_manage_workspace_public(current_user):
            raise HTTPException(status_code=403, detail="Only workspace admin can maintain workspace knowledge base")


def _require_record_manage(current_user: CurrentUser, record: KnowledgeBase) -> None:
    scope = _parse_scope(record.visibility_scope)
    if int(record.tenant_id) != _scope_tenant_id(current_user, scope):
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    _require_scope_manage(current_user, scope)


def _can_manage_record(current_user: CurrentUser, record: KnowledgeBase) -> bool:
    try:
        _require_record_manage(current_user, record)
        return True
    except HTTPException:
        return False


def _serialize_record(current_user: CurrentUser, record: KnowledgeBase) -> KnowledgeBaseItem:
    return KnowledgeBaseItem(
        id=int(record.id),
        tenant_id=int(record.tenant_id),
        create_by=record.create_by,
        name=record.name,
        description=record.description,
        content=record.content,
        visibility_scope=_parse_scope(record.visibility_scope),
        active=bool(record.active),
        status=KnowledgeBaseStatusEnum(record.status),
        file_id=record.file_id,
        file_name=record.file_name,
        file_ext=record.file_ext,
        task_id=record.task_id,
        error_message=record.error_message,
        create_time=record.create_time,
        update_time=record.update_time,
        can_manage=_can_manage_record(current_user, record),
    )


async def _save_upload(file: UploadFile) -> tuple[str, str, str]:
    file_ext = AppFileUtils.validate_extension(file.filename, ALLOWED_EXTENSIONS)
    _, file_id = AppFileUtils.safe_upload_name(file.filename, ALLOWED_EXTENSIONS)
    save_path = AppFileUtils.safe_path(settings.UPLOAD_DIR, file_id)
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as target:
        target.write(
            await AppFileUtils.read_upload_limited(
                file,
                limit_file_size=KNOWLEDGE_FILE_MAX_BYTES,
            )
        )
    return file_id, file.filename or file_id, file_ext


@router.get("/list", response_model=list[KnowledgeBaseItem])
async def list_knowledge_base(
    session: SessionDep,
    current_user: CurrentUser,
    visibility_scope: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
):
    scope = _parse_scope(visibility_scope)
    filters = [
        KnowledgeBase.visibility_scope == scope.value,
        KnowledgeBase.tenant_id == _scope_tenant_id(current_user, scope),
    ]

    value = (keyword or "").strip()
    if value:
        pattern = f"%{value}%"
        filters.append(
            or_(
                KnowledgeBase.name.ilike(pattern),
                KnowledgeBase.description.ilike(pattern),
                KnowledgeBase.content.ilike(pattern),
                KnowledgeBase.file_name.ilike(pattern),
            )
        )

    rows = session.exec(
        select(KnowledgeBase)
        .where(*filters)
        .order_by(desc(KnowledgeBase.update_time), desc(KnowledgeBase.id))
    ).all()
    return [_serialize_record(current_user, row) for row in rows]


@router.post("/save", response_model=KnowledgeBaseItem)
async def save_knowledge_base(
    session: SessionDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    id: Optional[int] = Form(None),
    name: str = Form(...),
    description: str = Form(""),
    active: bool = Form(True),
    visibility_scope: str = Form(KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC.value),
    file: Optional[UploadFile] = File(None),
):
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Knowledge base name is required")

    requested_scope = _parse_scope(visibility_scope)
    now = _now()
    should_process = file is not None

    if id:
        record = session.get(KnowledgeBase, int(id))
        if not record:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        _require_record_manage(current_user, record)
        scope = _parse_scope(record.visibility_scope)
    else:
        _require_scope_manage(current_user, requested_scope)
        if file is None:
            raise HTTPException(status_code=400, detail="Knowledge base file is required")
        scope = requested_scope
        record = KnowledgeBase(
            tenant_id=_scope_tenant_id(current_user, scope),
            create_by=int(current_user.id),
            name=clean_name,
            description=description.strip(),
            active=active,
            visibility_scope=scope,
            status=KnowledgeBaseStatusEnum.PENDING,
            create_time=now,
            update_time=now,
        )

    record.name = clean_name
    record.description = description.strip()
    record.active = active
    record.update_time = now

    if file is not None:
        old_file_id = record.file_id
        file_id, file_name, file_ext = await _save_upload(file)
        record.file_id = file_id
        record.file_name = file_name
        record.file_ext = file_ext
        record.status = KnowledgeBaseStatusEnum.PENDING
        record.error_message = None
        record.task_id = None
        if old_file_id and old_file_id != file_id:
            AppFileUtils.delete_file(old_file_id)

    session.add(record)
    session.commit()
    session.refresh(record)

    if should_process:
        try:
            register_builtin_tasks()
            task = await enqueue_task(
                "knowledge_base.process_document",
                {"id": int(record.id), "tenant_id": int(record.tenant_id)},
                created_by=int(current_user.id),
                tenant_id=int(record.tenant_id),
            )
            record.task_id = task.get("id")
        except Exception as exc:
            record.task_id = None
            record.error_message = None
            background_tasks.add_task(
                process_knowledge_base_document,
                {"id": int(record.id), "tenant_id": int(record.tenant_id)},
            )
        record.update_time = _now()
        session.add(record)
        session.commit()
        session.refresh(record)

    return _serialize_record(current_user, record)


@router.delete("/{id}")
async def delete_knowledge_base(session: SessionDep, current_user: CurrentUser, id: int):
    record = session.get(KnowledgeBase, int(id))
    if not record:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    _require_record_manage(current_user, record)
    AppFileUtils.delete_file(record.file_id)
    session.delete(record)
    return {"id": id}
