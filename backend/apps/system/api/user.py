"""
脚本说明：这个脚本放系统管理的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
from collections import defaultdict

from fastapi import APIRouter, File, HTTPException, Path, Query, UploadFile
from sqlmodel import SQLModel, delete as sqlmodel_delete, or_, select

from apps.datasource.crud.permission import (
    list_user_datasource_ids,
    list_user_datasource_roles,
    update_user_datasources,
)
from apps.datasource.crud.binding import get_bound_datasource_id_for_tenant
from apps.datasource.models.datasource import CoreDatasource, CoreDatasourceUser
from apps.swagger.i18n import PLACEHOLDER_PREFIX
from apps.system.crud.tenant import (
    DEFAULT_TENANT_ID,
    TENANT_ROLE_ADMIN,
    TENANT_ROLE_MEMBER,
    TENANT_ROLE_OWNER,
    assign_user_to_tenant,
    ensure_user_sample_workspace_membership,
    normalize_tenant_role,
    remove_user_from_tenant,
)
from apps.system.crud.user import (
    SYSTEM_ADMIN_ROLES,
    SYSTEM_ROLE_SYSTEM_ADMIN,
    check_email_format,
    check_pwd_format,
    check_user_in_tenant,
    get_db_user,
    is_high_privilege_system_role,
    is_high_privilege_user,
    is_platform_admin,
    is_super_admin,
    normalize_system_role,
)
from apps.system.crud.user_excel import batchUpload, download_error_file, downTemplate
from apps.system.models.tenant import TenantModel, TenantUserModel
from apps.system.models.user import TrialApplicationModel, UserModel, UserPlatformModel
from apps.system.schemas.auth import (
    CacheName,
    CacheNamespace,
    TrialApplicationDTO,
    TrialApplicationReview,
)
from apps.system.schemas.permission import AppPermission, require_permissions
from apps.system.schemas.system_schema import (
    PwdEditor,
    UserCreator,
    UserEditor,
    UserGrid,
    UserInfoDTO,
    UserLanguage,
    UserStatus,
)
from common.audit.models.log_model import OperationModules, OperationType
from common.audit.schemas.logger_decorator import LogConfig, system_log
from common.core.app_cache import clear_cache
from common.core.config import settings
from common.core.deps import CurrentUser, SessionDep, Trans
from common.core.pagination import Paginator
from common.core.schemas import PaginatedResponse, PaginationParams
from common.core.security import (
    default_password_hash,
    hash_password,
    verify_stored_password,
)
from common.utils.time import get_timestamp

router = APIRouter(tags=["system_user"], prefix="/user")


def _trial_application_dto(application: TrialApplicationModel) -> TrialApplicationDTO:
    """
    是什么：_trial_application_dto 把试用申请数据库对象转成接口返回结构。
    """
    return TrialApplicationDTO.model_validate(application.model_dump(exclude={"password_hash"}))


def _current_tenant_id(current_user: CurrentUser) -> int:
    """
    是什么：_current_tenant_id 是从当前用户里取租户 ID 的小工具。
    谁调用：需要知道当前用户属于哪个租户的接口会调用它。
    做了什么：把用户上下文里的租户 ID 取出来，方便后面做权限和数据隔离。
    """
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Current tenant is required")
    return int(tenant_id)


def _require_user_in_current_tenant(session: SessionDep, current_user: CurrentUser, user_id: int) -> None:
    """
    是什么：_require_user_in_current_tenant 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if is_platform_admin(current_user):
        return
    if not check_user_in_tenant(session=session, user_id=int(user_id), tenant_id=_current_tenant_id(current_user)):
        raise HTTPException(status_code=404, detail="User not found in current tenant")


def _get_user_tenant_role(session: SessionDep, user_id: int, tenant_id: int) -> str:
    """
    是什么：_get_user_tenant_role 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    membership = session.exec(
        select(TenantUserModel).where(
            TenantUserModel.user_id == int(user_id),
            TenantUserModel.tenant_id == int(tenant_id),
            TenantUserModel.status == 1,
        )
    ).first()
    return normalize_tenant_role(membership.role if membership else TENANT_ROLE_MEMBER)


def _get_user_visible_tenant_role(session: SessionDep, current_user: CurrentUser, user_id: int) -> str | None:
    """
    是什么：_get_user_visible_tenant_role 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    if not is_platform_admin(current_user):
        return _get_user_tenant_role(session, user_id, _current_tenant_id(current_user))
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id:
        current_role = _get_user_tenant_role(session, user_id, int(tenant_id))
        if check_user_in_tenant(session=session, user_id=int(user_id), tenant_id=int(tenant_id)):
            return current_role
    row = session.exec(
        select(TenantUserModel.role)
        .join(TenantModel, TenantModel.id == TenantUserModel.tenant_id)
        .where(
            TenantUserModel.user_id == int(user_id),
            TenantUserModel.status == 1,
            TenantModel.status == 1,
        )
        .order_by(TenantUserModel.is_primary.desc(), TenantModel.name)
    ).first()
    return normalize_tenant_role(row) if row else None


def _user_active_tenant_summary(session: SessionDep, user_ids: list[int]) -> dict[int, dict]:
    """
    是什么：_user_active_tenant_summary 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not user_ids:
        return {}
    rows = session.exec(
        select(
            TenantUserModel.user_id,
            TenantUserModel.tenant_id,
            TenantModel.name,
            TenantUserModel.role,
        )
        .join(TenantModel, TenantModel.id == TenantUserModel.tenant_id)
        .where(
            TenantUserModel.user_id.in_(user_ids),
            TenantUserModel.status == 1,
            TenantModel.status == 1,
        )
        .order_by(TenantUserModel.is_primary.desc(), TenantModel.name)
    ).all()
    summary: dict[int, dict] = {}
    for user_id, tenant_id, name, role in rows:
        item = summary.setdefault(
            int(user_id),
            {"tenant_ids": [], "tenant_names": [], "tenant_roles": {}},
        )
        item["tenant_ids"].append(int(tenant_id))
        item["tenant_names"].append(name or str(tenant_id))
        item["tenant_roles"][str(tenant_id)] = normalize_tenant_role(role)
    return summary


def _normalize_editable_tenant_role(
    role: str | None,
    current_user: CurrentUser,
    *,
    current_role: str | None = None,
) -> str:
    """
    是什么：_normalize_editable_tenant_role 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    normalized = normalize_tenant_role(role)
    if normalized == TENANT_ROLE_OWNER:
        if is_super_admin(current_user):
            return TENANT_ROLE_OWNER
        return TENANT_ROLE_ADMIN
    return normalized


def _ensure_tenant_owner_manageable(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: int,
    *,
    requested_role: str | None = None,
) -> str:
    """
    是什么：_ensure_tenant_owner_manageable 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    current_role = _get_user_tenant_role(session, user_id, _current_tenant_id(current_user))
    if is_super_admin(current_user):
        return current_role
    if current_role == TENANT_ROLE_OWNER:
        raise HTTPException(status_code=403, detail="Only system admin can manage tenant owner")
    return current_role


def _user_payload_data(
    user_payload: UserCreator | UserEditor,
    current_user: CurrentUser,
    current_model: UserModel | None = None,
) -> dict:
    """
    是什么：_user_payload_data 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    exclude = {
        "project_ids",
        "project_role_map",
        "tenant_role",
        "tenant_id",
        "tenant_ids",
        "tenant_names",
        "tenant_roles",
        "origin",
    }
    data = user_payload.model_dump(exclude=exclude)
    requested_system_role = normalize_system_role(data.get("system_role"))
    if is_super_admin(current_user):
        data["system_role"] = requested_system_role
    else:
        if current_model is not None:
            data["system_role"] = current_model.system_role
        else:
            data["system_role"] = "viewer"
    return data


def _target_tenant_id_for_payload(current_user: CurrentUser, tenant_id: int | None = None) -> int:
    """
    是什么：_target_tenant_id_for_payload 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return tenant_id if tenant_id and is_platform_admin(current_user) else _current_tenant_id(current_user)


def _should_assign_tenant_from_payload(current_user: CurrentUser, tenant_id: int | None = None) -> bool:
    """
    是什么：_should_assign_tenant_from_payload 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return not is_platform_admin(current_user) or tenant_id is not None


def _clean_user_value(value: str | None) -> str:
    """
    是什么：_clean_user_value 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理不再需要的数据、缓存或临时内容清理掉。
    """
    return (value or "").strip()


def _normalize_user_identity(user_payload: UserCreator | UserEditor) -> None:
    """
    是什么：_normalize_user_identity 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    user_payload.account = _clean_user_value(user_payload.account)
    user_payload.name = _clean_user_value(user_payload.name)
    user_payload.email = _clean_user_value(user_payload.email)


def _existing_user_by_account(session: SessionDep, account: str) -> UserModel | None:
    """
    是什么：_existing_user_by_account 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return session.exec(select(UserModel).where(UserModel.account == _clean_user_value(account))).first()


def _existing_user_by_name(session: SessionDep, name: str, exclude_user_id: int | None = None) -> UserModel | None:
    """
    是什么：_existing_user_by_name 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    statement = select(UserModel).where(UserModel.name == _clean_user_value(name))
    if exclude_user_id is not None:
        statement = statement.where(UserModel.id != int(exclude_user_id))
    return session.exec(statement).first()


def _require_unique_user_name(
    session: SessionDep,
    trans: Trans,
    name: str,
    exclude_user_id: int | None = None,
) -> None:
    """
    是什么：_require_unique_user_name 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    normalized_name = _clean_user_value(name)
    if _existing_user_by_name(session, normalized_name, exclude_user_id=exclude_user_id):
        raise Exception(trans('i18n_exist', msg=f"{trans('i18n_user.name')} [{normalized_name}]"))


async def _join_existing_user_to_tenant(
    session: SessionDep,
    current_user: CurrentUser,
    existing_user: UserModel,
    creator: UserCreator,
):
    """
    是什么：_join_existing_user_to_tenant 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if is_platform_admin(current_user) and creator.tenant_id is None:
        raise Exception("User already exists")
    target_tenant_id = _target_tenant_id_for_payload(current_user, creator.tenant_id)
    if check_user_in_tenant(session=session, user_id=int(existing_user.id), tenant_id=target_tenant_id):
        raise Exception("User already exists in current tenant")
    if is_high_privilege_user(existing_user) and not is_super_admin(current_user):
        raise Exception("Only system admin can add administrator accounts to tenant")
    assign_user_to_tenant(
        session,
        int(existing_user.id),
        tenant_id=target_tenant_id,
        role=_normalize_editable_tenant_role(creator.tenant_role, current_user),
        is_primary=False,
    )
    if creator.project_ids is not None:
        update_user_datasources(
            session,
            current_user,
            int(existing_user.id),
            creator.project_ids,
            creator.project_role_map,
        )
    return existing_user


def _remove_current_tenant_project_permissions(session: SessionDep, current_user: CurrentUser, user_id: int) -> None:
    """
    是什么：_remove_current_tenant_project_permissions 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理不再需要的数据、缓存或临时内容清理掉。
    """
    datasource_id = get_bound_datasource_id_for_tenant(session, _current_tenant_id(current_user))
    if datasource_id is None:
        return
    session.exec(
        sqlmodel_delete(CoreDatasourceUser).where(
            CoreDatasourceUser.user_id == int(user_id),
            CoreDatasourceUser.ds_id == int(datasource_id),
        )
    )


def _delete_global_user(session: SessionDep, current_user: CurrentUser, user_id: int) -> None:
    """
    是什么：_delete_global_user 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理不再需要的数据、缓存或临时内容清理掉。
    """
    user_model = get_db_user(session=session, user_id=user_id)
    if not user_model:
        raise HTTPException(status_code=404, detail="User not found")
    if int(user_model.id) == int(current_user.id) or is_super_admin(user_model):
        raise HTTPException(status_code=403, detail="System admin cannot be deleted")
    if is_high_privilege_user(user_model) and not is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="Only system admin can delete administrator roles")
    _ensure_user_not_sole_active_owner(session, user_id)
    session.exec(sqlmodel_delete(CoreDatasourceUser).where(CoreDatasourceUser.user_id == int(user_id)))
    session.exec(sqlmodel_delete(TenantUserModel).where(TenantUserModel.user_id == int(user_id)))
    session.exec(sqlmodel_delete(UserPlatformModel).where(UserPlatformModel.uid == int(user_id)))
    session.delete(user_model)
    session.flush()


def _remove_user_from_current_tenant(session: SessionDep, current_user: CurrentUser, user_id: int) -> None:
    """
    是什么：_remove_user_from_current_tenant 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理不再需要的数据、缓存或临时内容清理掉。
    """
    if is_platform_admin(current_user):
        _delete_global_user(session, current_user, user_id)
        return
    _require_user_in_current_tenant(session, current_user, user_id)
    _ensure_tenant_owner_manageable(session, current_user, user_id)
    user_model = get_db_user(session=session, user_id=user_id)
    if is_super_admin(user_model):
        raise Exception("System admin cannot be removed from tenant")
    if is_high_privilege_user(user_model) and not is_super_admin(current_user):
        raise Exception("Administrator roles cannot be removed")
    remove_user_from_tenant(session, user_id, tenant_id=_current_tenant_id(current_user))
    _remove_current_tenant_project_permissions(session, current_user, user_id)


def _ensure_user_not_sole_active_owner(session: SessionDep, user_id: int) -> None:
    """
    是什么：_ensure_user_not_sole_active_owner 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    owner_tenant_ids = session.exec(
        select(TenantUserModel.tenant_id).where(
            TenantUserModel.user_id == int(user_id),
            TenantUserModel.role == TENANT_ROLE_OWNER,
            TenantUserModel.status == 1,
        )
    ).all()
    if not owner_tenant_ids:
        return
    blocked_tenants = []
    for tenant_id in owner_tenant_ids:
        tenant = session.get(TenantModel, int(tenant_id))
        if tenant is None or int(getattr(tenant, "status", 1)) != 1 or int(tenant.id) == DEFAULT_TENANT_ID:
            continue
        other_owner = session.exec(
            select(TenantUserModel.id)
            .join(UserModel, UserModel.id == TenantUserModel.user_id)
            .where(
                TenantUserModel.tenant_id == int(tenant_id),
                TenantUserModel.role == TENANT_ROLE_OWNER,
                TenantUserModel.status == 1,
                TenantUserModel.user_id != int(user_id),
                UserModel.status == 1,
            )
        ).first()
        if not other_owner:
            blocked_tenants.append(tenant.name or str(tenant.id))
    if blocked_tenants:
        names = "、".join(blocked_tenants[:5])
        suffix = "..." if len(blocked_tenants) > 5 else ""
        raise HTTPException(
            status_code=400,
            detail=f"Transfer workspace ownership before deleting or disabling this account: {names}{suffix}",
        )


@router.get("/template", include_in_schema=False)
@require_permissions(permission=AppPermission(role=['admin']))
async def templateExcel(trans: Trans):
    """
    是什么：templateExcel 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return await downTemplate(trans)

@router.post("/batchImport", include_in_schema=False)
@require_permissions(permission=AppPermission(role=['admin']))
async def upload_excel(session: SessionDep, trans: Trans, _current_user: CurrentUser, file: UploadFile = File(...)):
    """
    是什么：upload_excel 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return await batchUpload(session, trans, file)


@router.get("/errorRecord/{file_id}", include_in_schema=False)
@require_permissions(permission=AppPermission(role=['admin']))
async def download_error(file_id: str):
    """
    是什么：download_error 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return download_error_file(file_id)

@router.get("/info", summary=f"{PLACEHOLDER_PREFIX}system_user_current_user", description=f"{PLACEHOLDER_PREFIX}system_user_current_user_desc")
async def user_info(current_user: CurrentUser) -> UserInfoDTO:
    """
    是什么：user_info 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return current_user


@router.get("/defaultPwd", include_in_schema=False)
@require_permissions(permission=AppPermission(role=['admin']))
async def default_pwd() -> str:
    """
    是什么：default_pwd 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if settings.APP_ENV == "production":
        raise HTTPException(status_code=403, detail="Default password is not exposed in production")
    return settings.DEFAULT_PWD


@router.get("/trial-applications", response_model=list[TrialApplicationDTO], include_in_schema=False)
@require_permissions(permission=AppPermission(role=['admin']))
async def list_trial_applications(
    session: SessionDep,
    current_user: CurrentUser,
    status: str | None = Query("pending"),
) -> list[TrialApplicationDTO]:
    """
    是什么：list_trial_applications 返回平台管理员可审核的试用账号申请。
    """
    if not is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="Only platform admin can review trial applications")
    statement = select(TrialApplicationModel).order_by(TrialApplicationModel.create_time.desc())
    if status:
        statement = statement.where(TrialApplicationModel.status == status)
    return [_trial_application_dto(item) for item in session.exec(statement).all()]


@router.post("/trial-applications/{application_id}/review", response_model=TrialApplicationDTO, include_in_schema=False)
@require_permissions(permission=AppPermission(role=['admin']))
async def review_trial_application(
    session: SessionDep,
    current_user: CurrentUser,
    trans: Trans,
    application_id: int,
    review: TrialApplicationReview,
) -> TrialApplicationDTO:
    """
    是什么：review_trial_application 审核试用申请；通过后创建启用的本地账号。
    """
    if not is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="Only platform admin can review trial applications")
    application = session.get(TrialApplicationModel, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Trial application not found")
    if application.status != "pending":
        raise HTTPException(status_code=400, detail="Trial application has already been reviewed")
    now = get_timestamp()
    application.reviewer_user_id = int(current_user.id)
    application.review_comment = review.review_comment
    application.review_time = now
    application.update_time = now
    if not review.approved:
        application.status = "rejected"
        session.add(application)
        return _trial_application_dto(application)

    if _existing_user_by_account(session, application.account):
        raise HTTPException(status_code=400, detail="Account already exists")
    _require_unique_user_name(session, trans, application.name)
    user_model = UserModel(
        account=application.account,
        name=application.name,
        email=application.email,
        password=application.password_hash,
        status=1,
        origin=0,
        language="zh-CN",
        system_role="viewer",
    )
    session.add(user_model)
    session.flush()
    ensure_user_sample_workspace_membership(session, user_model)
    application.status = "approved"
    application.approved_user_id = int(user_model.id)
    session.add(application)
    return _trial_application_dto(application)

@router.get("/pager/{pageNum}/{pageSize}", response_model=PaginatedResponse[UserGrid], summary=f"{PLACEHOLDER_PREFIX}system_user_grid", description=f"{PLACEHOLDER_PREFIX}system_user_grid")
@require_permissions(permission=AppPermission(role=['admin']))
async def pager(
    session: SessionDep,
    current_user: CurrentUser,
    pageNum: int = Path(..., title=f"{PLACEHOLDER_PREFIX}page_num", description=f"{PLACEHOLDER_PREFIX}page_num"),
    pageSize: int = Path(..., title=f"{PLACEHOLDER_PREFIX}page_size", description=f"{PLACEHOLDER_PREFIX}page_size"),
    keyword: str | None = Query(None, description=f"{PLACEHOLDER_PREFIX}keyword"),
    status: int | None = Query(None, description=f"{PLACEHOLDER_PREFIX}status"),
    origins: list[int] | None = Query(None, description=f"{PLACEHOLDER_PREFIX}origin"),
):
    """
    是什么：pager 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    pagination = PaginationParams(page=pageNum, size=pageSize)
    paginator = Paginator(session)
    filters = {}

    if is_platform_admin(current_user):
        origin_stmt = select(UserModel.id, UserModel.account).order_by(UserModel.account)
    else:
        origin_stmt = (
            select(UserModel.id, UserModel.account)
            .join(TenantUserModel, TenantUserModel.user_id == UserModel.id)
            .where(
                TenantUserModel.tenant_id == _current_tenant_id(current_user),
                TenantUserModel.status == 1,
                ~UserModel.system_role.in_(SYSTEM_ADMIN_ROLES),
            )
            .distinct()
            .order_by(UserModel.account)
        )

    if origins:
        origin_stmt = origin_stmt.where(UserModel.origin.in_(origins))
    if status is not None:
        origin_stmt = origin_stmt.where(UserModel.status == status)
    if keyword:
        keyword_pattern = f"%{keyword}%"
        origin_stmt = origin_stmt.where(
            or_(
                UserModel.account.ilike(keyword_pattern),
                UserModel.name.ilike(keyword_pattern),
                UserModel.email.ilike(keyword_pattern)
            )
        )

    user_page = await paginator.get_paginated_response(
        stmt=origin_stmt,
        pagination=pagination,
        **filters)
    uid_list = [item.get('id') for item in user_page.items]
    if not uid_list:
        return user_page
    users = session.exec(
        select(UserModel).where(UserModel.id.in_(uid_list)).order_by(UserModel.account, UserModel.create_time)
    ).all()
    tenant_summary = _user_active_tenant_summary(session, [int(item) for item in uid_list]) if is_platform_admin(current_user) else {}
    result = []
    for user in users:
        item = user.model_dump()
        item["tenant_role"] = _get_user_visible_tenant_role(session, current_user, int(user.id))
        if is_platform_admin(current_user):
            item["tenant_ids"] = []
            item["tenant_names"] = []
            item["tenant_roles"] = {}
        item.update(tenant_summary.get(int(user.id), {}))
        result.append(item)
    project_rows = []
    current_tenant_id = getattr(current_user, "tenant_id", None)
    if current_tenant_id and not is_platform_admin(current_user):
        bound_datasource_id = get_bound_datasource_id_for_tenant(session, int(current_tenant_id))
        if bound_datasource_id is None:
            project_rows = []
        else:
            project_rows = session.exec(
                select(CoreDatasourceUser.user_id, CoreDatasourceUser.ds_id, CoreDatasourceUser.role)
                .where(
                    CoreDatasourceUser.user_id.in_(uid_list),
                    CoreDatasourceUser.ds_id == int(bound_datasource_id),
                )
            ).all()
    project_map = defaultdict(list)
    project_role_map = defaultdict(dict)
    for user_id, ds_id, role in project_rows:
        project_map[int(user_id)].append(int(ds_id))
        project_role_map[int(user_id)][int(ds_id)] = role or "viewer"
    for item in result:
        item["project_ids"] = project_map.get(int(item["id"]), [])
        item["project_role_map"] = project_role_map.get(int(item["id"]), {})
    user_page.items = result
    return user_page

def format_user_dict(row) -> dict:
    """
    是什么：format_user_dict 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    result_dict = {}
    for item, key in zip(row, row._fields, strict=False):
        if isinstance(item, SQLModel):
            result_dict.update(item.model_dump())
        else:
            result_dict[key] = item

    return result_dict

@router.get("/{id}", response_model=UserEditor, summary=f"{PLACEHOLDER_PREFIX}user_detail_api", description=f"{PLACEHOLDER_PREFIX}user_detail_api")
@require_permissions(permission=AppPermission(role=['admin']))
async def query(session: SessionDep, current_user: CurrentUser, _trans: Trans, id: int = Path(description=f"{PLACEHOLDER_PREFIX}uid")) -> UserEditor:
    """
    是什么：query 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    _require_user_in_current_tenant(session, current_user, id)
    db_user: UserModel = get_db_user(session = session, user_id = id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    if is_high_privilege_user(db_user) and not is_super_admin(current_user):
        raise Exception("Only system admin can manage administrator roles")
    result = UserEditor.model_validate(db_user.model_dump())
    result.tenant_role = _get_user_visible_tenant_role(session, current_user, id)
    if is_platform_admin(current_user):
        result.project_ids = []
        result.project_role_map = {}
    else:
        result.project_ids = list_user_datasource_ids(session, id, current_user)
        result.project_role_map = list_user_datasource_roles(session, id, current_user)
    summary = _user_active_tenant_summary(session, [id]).get(int(id), {})
    for key, value in summary.items():
        setattr(result, key, value)
    return result


@router.post("", summary=f"{PLACEHOLDER_PREFIX}user_create_api", description=f"{PLACEHOLDER_PREFIX}user_create_api")
@require_permissions(permission=AppPermission(role=['admin']))
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.USER,
    result_id_expr="id"
))
async def user_create(session: SessionDep, current_user: CurrentUser, creator: UserCreator, trans: Trans):
    """
    是什么：user_create 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return await create(session=session, current_user=current_user, creator=creator, trans=trans)

async def create(session: SessionDep, current_user: CurrentUser, creator: UserCreator, trans: Trans):
    """
    是什么：create 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    _normalize_user_identity(creator)
    existing_user = _existing_user_by_account(session, creator.account)
    if existing_user:
        return await _join_existing_user_to_tenant(session, current_user, existing_user, creator)
    _require_unique_user_name(session, trans, creator.name)
    """ if check_email_exists(session=session, email=creator.email):
        raise Exception(trans('i18n_exist', msg = f"{trans('i18n_user.email')} [{creator.email}]")) """
    if not check_email_format(creator.email):
        raise Exception(trans('i18n_format_invalid', key = f"{trans('i18n_user.email')} [{creator.email}]"))
    #data = creator.model_dump(exclude_unset=True)
    data = _user_payload_data(creator, current_user)
    if is_high_privilege_system_role(data["system_role"]) and not is_super_admin(current_user):
        raise Exception("Only system admin can grant administrator roles")
    user_model = UserModel.model_validate(data)
    #user_model.create_time = get_timestamp()
    user_model.language = "zh-CN"
    session.add(user_model)
    session.flush()
    assigned_to_tenant = _should_assign_tenant_from_payload(current_user, creator.tenant_id)
    if assigned_to_tenant:
        target_tenant_id = _target_tenant_id_for_payload(current_user, creator.tenant_id)
        assign_user_to_tenant(
            session,
            int(user_model.id),
            tenant_id=target_tenant_id,
            role=_normalize_editable_tenant_role(creator.tenant_role, current_user),
            is_primary=True,
        )
    if assigned_to_tenant and creator.project_ids is not None:
        update_user_datasources(
            session,
            current_user,
            user_model.id,
            creator.project_ids,
            creator.project_role_map,
        )
    ensure_user_sample_workspace_membership(session, user_model)
    return user_model


@router.put("", summary=f"{PLACEHOLDER_PREFIX}user_update_api", description=f"{PLACEHOLDER_PREFIX}user_update_api")
@require_permissions(permission=AppPermission(role=['admin']))
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="editor.id")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.USER,
    resource_id_expr="editor.id"
))
async def update(session: SessionDep, current_user: CurrentUser, editor: UserEditor, trans: Trans):
    """
    是什么：update 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理相关的信息改成最新状态，并保存这些变化。
    """
    _normalize_user_identity(editor)
    user_model: UserModel = get_db_user(session = session, user_id = editor.id)
    if not user_model:
        raise Exception(f"User with id [{editor.id}] not found!")
    _require_user_in_current_tenant(session, current_user, editor.id)
    if editor.account != user_model.account:
        raise Exception("account cannot be changed!")
    _require_unique_user_name(session, trans, editor.name, exclude_user_id=int(user_model.id))
    """ if editor.email != user_model.email and check_email_exists(session=session, email=editor.email):
        raise Exception(trans('i18n_exist', msg = f"{trans('i18n_user.email')} [{editor.email}]")) """
    if not check_email_format(editor.email):
        raise Exception(trans('i18n_format_invalid', key = f"{trans('i18n_user.email')} [{editor.email}]"))
    data = _user_payload_data(editor, current_user, user_model)
    should_update_tenant_membership = not is_platform_admin(current_user) or editor.tenant_id is not None
    current_tenant_role = TENANT_ROLE_MEMBER
    if should_update_tenant_membership:
        current_tenant_role = _ensure_tenant_owner_manageable(
            session,
            current_user,
            int(user_model.id),
            requested_role=editor.tenant_role,
        )
    if is_high_privilege_user(user_model) and not is_super_admin(current_user):
        raise Exception("Only system admin can manage administrator roles")
    if is_high_privilege_system_role(data["system_role"]) and not is_super_admin(current_user):
        raise Exception("Only system admin can grant administrator roles")
    if is_super_admin(user_model) and data["system_role"] != SYSTEM_ROLE_SYSTEM_ADMIN:
        raise Exception("System admin role cannot be removed from this endpoint")
    if is_super_admin(user_model) and int(data.get("status", 1) or 0) != 1:
        raise Exception("System admin cannot be disabled")
    if int(data.get("status", 1) or 0) == 0:
        _ensure_user_not_sole_active_owner(session, int(user_model.id))
    user_model.sqlmodel_update(data)
    session.add(user_model)
    if should_update_tenant_membership:
        target_tenant_id = _target_tenant_id_for_payload(current_user, editor.tenant_id)
        assign_user_to_tenant(
            session,
            int(user_model.id),
            tenant_id=target_tenant_id,
            role=_normalize_editable_tenant_role(editor.tenant_role, current_user, current_role=current_tenant_role),
            is_primary=True,
        )
    if should_update_tenant_membership and editor.project_ids is not None:
        update_user_datasources(
            session,
            current_user,
            user_model.id,
            editor.project_ids,
            editor.project_role_map,
        )
    ensure_user_sample_workspace_membership(session, user_model)

@router.delete("/{id}", summary=f"{PLACEHOLDER_PREFIX}user_del_api", description=f"{PLACEHOLDER_PREFIX}user_del_api")
@require_permissions(permission=AppPermission(role=['admin']))
@system_log(LogConfig(
    operation_type=OperationType.DELETE,
    module=OperationModules.USER,
    resource_id_expr="id"
))
async def delete(session: SessionDep, current_user: CurrentUser, id: int = Path(description=f"{PLACEHOLDER_PREFIX}uid")):
    """
    是什么：delete 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理不再需要的数据、缓存或临时内容清理掉。
    """
    _remove_user_from_current_tenant(session, current_user, id)

@router.delete("", summary=f"{PLACEHOLDER_PREFIX}user_batchdel_api", description=f"{PLACEHOLDER_PREFIX}user_batchdel_api")
@require_permissions(permission=AppPermission(role=['admin']))
@system_log(LogConfig(operation_type=OperationType.DELETE,module=OperationModules.USER,resource_id_expr="id_list"))
async def batch_del(session: SessionDep, current_user: CurrentUser, id_list: list[int]):
    """
    是什么：batch_del 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    for id in id_list:
        _remove_user_from_current_tenant(session, current_user, id)

@router.put("/language", summary=f"{PLACEHOLDER_PREFIX}language_change", description=f"{PLACEHOLDER_PREFIX}language_change")
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="current_user.id")
async def langChange(session: SessionDep, current_user: CurrentUser, trans: Trans, language: UserLanguage):
    """
    是什么：langChange 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    lang = language.language
    if lang not in ["zh-CN", "zh-TW", "en", "ko-KR"]:
        raise Exception(trans('i18n_user.language_not_support', key = lang))
    db_user: UserModel = get_db_user(session=session, user_id=current_user.id)
    db_user.language = lang
    session.add(db_user)


@router.patch("/pwd/{id}", summary=f"{PLACEHOLDER_PREFIX}reset_pwd", description=f"{PLACEHOLDER_PREFIX}reset_pwd")
@require_permissions(permission=AppPermission(role=['admin']))
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="id")
@system_log(LogConfig(operation_type=OperationType.RESET_PWD,module=OperationModules.USER,resource_id_expr="id"))
async def pwdReset(session: SessionDep, current_user: CurrentUser, trans: Trans, id: int = Path(description=f"{PLACEHOLDER_PREFIX}uid")):
    """
    是什么：pwdReset 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    _require_user_in_current_tenant(session, current_user, id)
    if not is_platform_admin(current_user):
        _ensure_tenant_owner_manageable(session, current_user, id)
    db_user: UserModel = get_db_user(session=session, user_id=id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    if is_high_privilege_user(db_user) and not is_super_admin(current_user):
        raise Exception(trans('i18n_permission.no_permission', url = " patch[/user/pwd/id],", msg = trans('i18n_permission.only_admin')))
    db_user.password = default_password_hash()
    session.add(db_user)

@router.put("/pwd", summary=f"{PLACEHOLDER_PREFIX}update_pwd", description=f"{PLACEHOLDER_PREFIX}update_pwd")
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="current_user.id")
@system_log(LogConfig(operation_type=OperationType.UPDATE_PWD,module=OperationModules.USER,result_id_expr="id"))
async def pwdUpdate(session: SessionDep, current_user: CurrentUser, trans: Trans, editor: PwdEditor):
    """
    是什么：pwdUpdate 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    new_pwd = editor.new_pwd
    if not check_pwd_format(new_pwd):
        raise Exception(trans('i18n_format_invalid', key = trans('i18n_user.password')))
    db_user: UserModel = get_db_user(session=session, user_id=current_user.id)
    valid_password, _needs_rehash = verify_stored_password(editor.pwd, db_user.password)
    if not valid_password:
        raise Exception(trans('i18n_error', key = trans('i18n_user.password')))
    db_user.password = hash_password(new_pwd)
    session.add(db_user)
    return db_user


@router.patch("/status", summary=f"{PLACEHOLDER_PREFIX}update_status", description=f"{PLACEHOLDER_PREFIX}update_status")
@require_permissions(permission=AppPermission(role=['admin']))
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="statusDto.id")
@system_log(LogConfig(operation_type=OperationType.UPDATE_STATUS,module=OperationModules.USER, resource_id_expr="statusDto.id"))
async def statusChange(session: SessionDep, current_user: CurrentUser, trans: Trans, statusDto: UserStatus):
    """
    是什么：statusChange 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    status = statusDto.status
    if status not in [0, 1]:
        return {"message": "status not supported"}
    if not is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="Only system admin can change SaaS account status")
    if not is_super_admin(current_user):
        _require_user_in_current_tenant(session, current_user, statusDto.id)
    if status == 0 and not is_super_admin(current_user):
        _ensure_tenant_owner_manageable(session, current_user, statusDto.id)
    db_user: UserModel = get_db_user(session=session, user_id=statusDto.id)
    if is_high_privilege_user(db_user) and status == 0 and not is_super_admin(current_user):
        raise Exception(trans('i18n_permission.no_permission', url = ", ", msg = trans('i18n_permission.only_admin')))
    if is_super_admin(db_user) and status == 0:
        raise Exception("System admin cannot be disabled")
    if status == 0:
        _ensure_user_not_sole_active_owner(session, int(db_user.id))
    db_user.status = status
    session.add(db_user)
