"""
脚本说明：这个脚本放后端业务的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from sqlalchemy import desc, or_
from sqlmodel import select

from apps.knowledge_base.api._helpers import validate_workspace_tenant
from apps.knowledge_base.models import (
    KnowledgeBase,
    KnowledgeBaseItem,
    KnowledgeBaseStatusEnum,
    KnowledgeBaseVisibilityScopeEnum,
)
from apps.knowledge_base.repository import KnowledgeMigrationStateRepository
from apps.knowledge_base.tasks import process_knowledge_base_document
from apps.system.crud.tenant import (
    DEFAULT_TENANT_ID,
    TENANT_ADMIN_ROLES,
    normalize_tenant_role,
)
from apps.system.crud.user import is_platform_admin, is_platform_workspace_delegate
from apps.system.schemas.access_context import (
    current_tenant_id,
    require_current_tenant_id,
)
from common.core.config import settings
from common.core.deps import CurrentUser, SessionDep
from common.core.task_queue import enqueue_task
from common.core.task_registry import register_builtin_tasks
from common.utils.file_utils import AppFileUtils

router = APIRouter(tags=["KnowledgeBase"], prefix="/knowledge-base", include_in_schema=False)

ALLOWED_EXTENSIONS = {".md", ".markdown", ".docx"}
KNOWLEDGE_FILE_MAX_BYTES = settings.KNOWLEDGE_FILE_MAX_BYTES


def _now() -> datetime:
    """
    是什么：_now 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把后端业务里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return datetime.now()


def _parse_scope(value: str | None) -> KnowledgeBaseVisibilityScopeEnum:
    """
    是什么：_parse_scope 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把后端业务的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    try:
        return KnowledgeBaseVisibilityScopeEnum(value or KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unsupported knowledge base visibility scope") from exc


def _is_global_platform_admin(current_user: CurrentUser) -> bool:
    """
    是什么：_is_global_platform_admin 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把后端业务里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return is_platform_admin(current_user) and not is_platform_workspace_delegate(current_user)


def _can_manage_workspace_public(current_user: CurrentUser) -> bool:
    """
    是什么：_can_manage_workspace_public 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把后端业务里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if _is_global_platform_admin(current_user):
        return True
    tenant_role = normalize_tenant_role(getattr(current_user, "tenant_role", None))
    return is_platform_admin(current_user) or tenant_role in TENANT_ADMIN_ROLES


def _scope_tenant_id(current_user: CurrentUser, scope: KnowledgeBaseVisibilityScopeEnum) -> int:
    """
    是什么：_scope_tenant_id 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把后端业务里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC:
        return DEFAULT_TENANT_ID
    return require_current_tenant_id(current_user)


def _requested_tenant_id(current_user: CurrentUser, tenant_id: int | None) -> int:
    if tenant_id is not None:
        requested = int(tenant_id)
        if _is_global_platform_admin(current_user) or current_tenant_id(current_user) == requested:
            return requested
        raise HTTPException(status_code=403, detail="Cannot access another workspace knowledge base")
    if _is_global_platform_admin(current_user):
        raise HTTPException(status_code=400, detail="Please select a workspace")
    return _scope_tenant_id(current_user, KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC)


def _require_scope_manage(current_user: CurrentUser, scope: KnowledgeBaseVisibilityScopeEnum) -> None:
    """
    是什么：_require_scope_manage 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：检查后端业务里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC:
        if not _is_global_platform_admin(current_user):
            raise HTTPException(status_code=403, detail="Only SaaS admin can maintain SaaS knowledge base")
        return
    if scope == KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC:
        if not _can_manage_workspace_public(current_user):
            raise HTTPException(status_code=403, detail="Only workspace admin can maintain workspace knowledge base")


def _require_record_manage(current_user: CurrentUser, record: KnowledgeBase) -> None:
    """
    是什么：_require_record_manage 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：检查后端业务里的数据、权限或配置是否合法，不对就及时拦住。
    """
    scope = _parse_scope(record.visibility_scope)
    if _is_global_platform_admin(current_user):
        if scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC and int(record.tenant_id) != DEFAULT_TENANT_ID:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        _require_scope_manage(current_user, scope)
        return
    if int(record.tenant_id) != _scope_tenant_id(current_user, scope):
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    _require_scope_manage(current_user, scope)


def _can_manage_record(current_user: CurrentUser, record: KnowledgeBase) -> bool:
    """
    是什么：_can_manage_record 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把后端业务里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        _require_record_manage(current_user, record)
        return True
    except HTTPException:
        return False


def _serialize_record(current_user: CurrentUser, record: KnowledgeBase) -> KnowledgeBaseItem:
    """
    是什么：_serialize_record 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把后端业务的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
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
    """
    是什么：_save_upload 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：创建或保存后端业务需要的东西，让后续流程能继续往下走。
    """
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


async def list_legacy_knowledge_base(
    session: SessionDep,
    current_user: CurrentUser,
    visibility_scope: str | None = Query(None),
    keyword: str | None = Query(None),
    tenant_id: int | None = Query(None, ge=1),
):
    """
    是什么：list_knowledge_base 是一个接口入口，负责接住后端业务相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把后端业务需要的数据找出来，整理成后面好用的样子。
    """
    scope = _parse_scope(visibility_scope)
    if tenant_id is not None and scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC:
        raise HTTPException(status_code=400, detail="Platform knowledge base does not accept workspace selection")
    target_tenant_id = (
        DEFAULT_TENANT_ID
        if scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC
        else _requested_tenant_id(current_user, tenant_id)
    )
    if scope == KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC:
        validate_workspace_tenant(session, target_tenant_id)
    filters = [
        KnowledgeBase.visibility_scope == scope.value,
        KnowledgeBase.tenant_id == target_tenant_id,
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
    id: int | None = Form(None),
    name: str = Form(...),
    description: str = Form(""),
    active: bool = Form(True),
    visibility_scope: str = Form(KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC.value),
    file: UploadFile | None = File(None),
    tenant_id: int | None = Form(None),
):
    """
    是什么：save_knowledge_base 是一个接口入口，负责接住后端业务相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：创建或保存后端业务需要的东西，让后续流程能继续往下走。
    """
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Knowledge base name is required")

    requested_scope = _parse_scope(visibility_scope)
    if requested_scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC and tenant_id is not None:
        raise HTTPException(status_code=400, detail="Platform knowledge base does not accept workspace selection")
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
        target_tenant_id = (
            DEFAULT_TENANT_ID
            if scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC
            else _requested_tenant_id(current_user, tenant_id)
        )
        if scope == KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC:
            validate_workspace_tenant(session, target_tenant_id)
        record = KnowledgeBase(
            tenant_id=target_tenant_id,
            create_by=int(current_user.id),
            name=clean_name,
            description=description.strip(),
            active=active,
            visibility_scope=scope,
            status=KnowledgeBaseStatusEnum.PENDING,
            create_time=now,
            update_time=now,
        )

    KnowledgeMigrationStateRepository.lock_for_legacy_write(session)
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
        KnowledgeMigrationStateRepository.lock_for_legacy_write(session)
        try:
            register_builtin_tasks()
            task = await enqueue_task(
                "knowledge_base.process_document",
                {"id": int(record.id), "tenant_id": int(record.tenant_id)},
                created_by=int(current_user.id),
                tenant_id=int(record.tenant_id),
            )
            record.task_id = task.get("id")
        except Exception:
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


async def delete_legacy_knowledge_base(session: SessionDep, current_user: CurrentUser, id: int):
    """
    是什么：delete_knowledge_base 是一个接口入口，负责接住后端业务相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把后端业务不再需要的数据、缓存或临时内容清理掉。
    """
    record = session.get(KnowledgeBase, int(id))
    if not record:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    _require_record_manage(current_user, record)
    KnowledgeMigrationStateRepository.lock_for_legacy_write(session)
    AppFileUtils.delete_file(record.file_id)
    session.delete(record)
    return {"id": id}


# Keep the callable names used by the legacy tests and integrations while the
# phase-aware management router owns the public path registrations.
list_knowledge_base = list_legacy_knowledge_base
delete_knowledge_base = delete_legacy_knowledge_base
