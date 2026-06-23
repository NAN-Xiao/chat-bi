from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, inspect, or_
from sqlmodel import delete as sqlmodel_delete, select

from apps.chat.curd.custom_prompt import CustomPromptTypeEnum, CustomPromptVisibilityScopeEnum
from apps.chat.models.custom_prompt_model import CustomPrompt
from apps.dashboard.models.dashboard_model import CoreDashboard
from apps.data_training.models.data_training_model import DataTraining
from apps.datasource.crud.binding import bind_tenant_to_datasource
from apps.datasource.models.datasource import CoreDatasource, CoreDatasourceUser
from apps.datasource.crud.permission import (
    list_user_datasource_roles,
    update_user_datasources,
)
from apps.system.schemas.semantic_scope import SemanticRecordScopeEnum
from apps.system.crud.tenant import (
    DEFAULT_TENANT_ID,
    SAMPLE_TENANT_NAME,
    TENANT_ADMIN_ROLES,
    TENANT_APPLICATION_TYPE_CREATE,
    TENANT_APPLICATION_TYPE_INVITE,
    TENANT_APPLICATION_TYPE_JOIN,
    TENANT_DATA_REQUEST_TYPE_CANCEL,
    TENANT_DATA_REQUEST_TYPE_DELETE,
    TENANT_ROLE_OWNER,
    assign_user_to_tenant,
    approve_tenant_application,
    cancel_tenant_application,
    create_tenant,
    create_tenant_application,
    create_tenant_data_request,
    create_tenant_domain,
    create_tenant_invitation,
    delete_tenant,
    complete_tenant_data_request,
    ensure_user_sample_workspace_membership,
    get_tenant_membership,
    leave_tenant,
    list_tenant_data_requests,
    list_tenants,
    list_tenant_applications,
    list_tenant_domains,
    list_user_tenant_memberships,
    normalize_application_role,
    normalize_tenant_role,
    reject_tenant_application,
    remove_user_from_tenant,
    review_tenant_data_request,
    review_tenant_domain,
    search_active_tenants,
    set_tenant_status,
    transfer_tenant_owner,
    update_tenant,
    upsert_tenant_security_policy,
    get_tenant_security_policy,
    ensure_tenant_public_id,
    user_belongs_to_tenant,
)
from apps.system.crud.tenant_usage import _chat_log_total_tokens_expr, list_tenant_usage_by_user, list_tenant_usage_daily
from apps.system.crud.user import (
    SYSTEM_ROLE_VIEWER,
    check_email_format,
    is_high_privilege_user,
    is_platform_admin,
    is_platform_workspace_delegate,
    is_super_admin,
)
from apps.system.models.system_model import AiModelDetail, AssistantModel
from apps.system.models.tenant_usage import TenantUsageDailyModel
from apps.chat.models.chat_model import ChatLog
from apps.system.models.tenant import (
    TenantApplicationModel,
    TenantDataRequestModel,
    TenantDomainModel,
    TenantModel,
    TenantSecurityPolicyModel,
    TenantUserModel,
)
from apps.system.models.user import UserModel
from apps.system.schemas.tenant_schema import (
    TenantApplicationCreator,
    TenantApplicationDTO,
    TenantApplicationReview,
    TenantBulkInviteCreator,
    TenantBulkInviteResult,
    TenantBulkMemberCreator,
    TenantBulkMemberResult,
    TenantDataRequestComplete,
    TenantDataRequestCreator,
    TenantDataRequestDTO,
    TenantDataRequestReview,
    TenantDomainCreator,
    TenantDomainDTO,
    TenantDomainReview,
    TenantInvitationCreator,
    TenantMemberCreator,
    TenantMemberDTO,
    TenantMemberEditor,
    TenantCreator,
    TenantDatasourceBindingEditor,
    TenantDTO,
    TenantEditor,
    TenantOverviewAssetItemDTO,
    TenantOverviewDTO,
    TenantOverviewEventDTO,
    TenantOverviewMemberActivityDTO,
    TenantOverviewRoleItemDTO,
    TenantOverviewSummaryDTO,
    TenantOverviewTodoDTO,
    TenantOverviewTrendPointDTO,
    PlatformOverviewDTO,
    PlatformOverviewDistributionItemDTO,
    PlatformOverviewModelUsageDTO,
    PlatformOverviewRecentTenantDTO,
    PlatformOverviewSummaryDTO,
    PlatformOverviewTenantUsageDTO,
    PlatformOverviewTrendPointDTO,
    TenantOwnerTransfer,
    TenantSecurityPolicyDTO,
    TenantSecurityPolicyEditor,
    TenantSearchDTO,
    TenantStatus,
)
from apps.system.schemas.tenant_usage_schema import TenantUsageDailyDTO, TenantUsageUserDTO
from apps.terminology.models.terminology_model import Terminology
from common.audit.models.log_model import OperationModules, OperationStatus, OperationType, SystemLog
from common.audit.schemas.request_context import RequestContext
from common.core.deps import CurrentTenant, CurrentUser, SessionDep

router = APIRouter(tags=["system_tenant"], prefix="/system/tenant")


def _enum_value(value):
    return getattr(value, "value", value)


def _audit_user_name(current_user: CurrentUser) -> str | None:
    return (
        getattr(current_user, "name", None)
        or getattr(current_user, "username", None)
        or getattr(current_user, "account", None)
    )


def _model_fields_set(model) -> set[str]:
    return set(getattr(model, "model_fields_set", None) or getattr(model, "__fields_set__", set()) or set())


def _audit_tenant_id(current_user: CurrentUser, tenant_id: int | None = None) -> int:
    if is_platform_workspace_delegate(current_user):
        return DEFAULT_TENANT_ID
    try:
        return int(tenant_id or getattr(current_user, "tenant_id", None) or DEFAULT_TENANT_ID)
    except (TypeError, ValueError):
        return DEFAULT_TENANT_ID


def _audit_request_info() -> tuple[str | None, str | None, str | None, str | None]:
    try:
        request = RequestContext.get_request()
    except RuntimeError:
        return None, None, None, None
    ip_address = request.client.host if request.client else None
    if "x-forwarded-for" in request.headers:
        ip_address = request.headers["x-forwarded-for"].split(",")[0].strip()
    return (
        ip_address,
        request.headers.get("user-agent"),
        request.method,
        request.url.path,
    )


def _application_audit_remark(application: TenantApplicationModel) -> str:
    parts = [
        f"type={application.application_type}",
        f"status={application.status}",
        f"tenant_id={application.tenant_id}",
        f"requested_role={application.requested_role}",
        f"applicant_user_id={application.applicant_user_id}",
    ]
    if application.invited_by_user_id:
        parts.append(f"invited_by_user_id={application.invited_by_user_id}")
    return "; ".join(parts)


def _application_audit_tenant_id(current_user: CurrentUser, application: TenantApplicationModel) -> int:
    return _audit_tenant_id(current_user, application.tenant_id)


def _write_tenant_audit(
    session: SessionDep,
    current_user: CurrentUser,
    *,
    operation_type: OperationType,
    detail: str,
    module: OperationModules,
    tenant_id: int | None = None,
    resource_id: int | str | None = None,
    resource_name: str | None = None,
    remark: str | None = None,
) -> None:
    ip_address, user_agent, request_method, request_path = _audit_request_info()
    session.add(
        SystemLog(
            tenant_id=_audit_tenant_id(current_user, tenant_id),
            operation_type=_enum_value(operation_type),
            operation_detail=detail,
            user_id=getattr(current_user, "id", None),
            user_name=_audit_user_name(current_user),
            operation_status=OperationStatus.SUCCESS.value,
            ip_address=ip_address,
            user_agent=user_agent,
            module=_enum_value(module),
            resource_id=str(resource_id) if resource_id is not None else None,
            resource_name=resource_name,
            request_method=request_method,
            request_path=request_path,
            remark=remark,
            create_time=datetime.now(),
        )
    )


def _require_platform_admin(current_user: CurrentUser) -> None:
    if not is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="Only SaaS admin can manage tenants")


def _require_current_tenant_admin(current_user: CurrentUser) -> None:
    if is_platform_admin(current_user):
        if is_platform_workspace_delegate(current_user):
            return
        raise HTTPException(status_code=403, detail="Only tenant admin can manage tenant members")
    tenant_role = normalize_tenant_role(getattr(current_user, "tenant_role", None))
    if tenant_role not in TENANT_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Only tenant admin can manage tenant members")


def _require_current_tenant_owner(current_user: CurrentUser) -> None:
    if is_platform_admin(current_user):
        if is_platform_workspace_delegate(current_user):
            return
        raise HTTPException(status_code=403, detail="Only tenant owner can perform this operation")
    tenant_role = normalize_tenant_role(getattr(current_user, "tenant_role", None))
    if tenant_role != TENANT_ROLE_OWNER:
        raise HTTPException(status_code=403, detail="Only tenant owner can perform this operation")


def _non_platform_member_filter(session: SessionDep):
    if not _table_exists(session, UserModel.__tablename__):
        return []
    return [UserModel.system_role.not_in(("system_admin", "collab_admin"))]


def _table_exists(session: SessionDep, table_name: str) -> bool:
    try:
        return inspect(session.connection()).has_table(table_name)
    except Exception:
        return False


def _remove_tenant_project_permissions(session: SessionDep, *, tenant_id: int, user_id: int) -> None:
    if not _table_exists(session, CoreDatasource.__tablename__) or not _table_exists(
        session,
        CoreDatasourceUser.__tablename__,
    ):
        return
    datasource_ids = select(CoreDatasource.id).where(CoreDatasource.tenant_id == int(tenant_id))
    session.exec(
        sqlmodel_delete(CoreDatasourceUser).where(
            CoreDatasourceUser.user_id == int(user_id),
            CoreDatasourceUser.ds_id.in_(datasource_ids),
        )
    )


def _tenant_owner_map(session: SessionDep, tenant_ids: list[int]) -> dict[int, dict]:
    if not tenant_ids or not _table_exists(session, UserModel.__tablename__):
        return {}
    rows = session.exec(
        select(
            TenantUserModel.tenant_id,
            UserModel.id,
            UserModel.account,
            UserModel.name,
            UserModel.email,
        )
        .join(UserModel, UserModel.id == TenantUserModel.user_id)
        .where(
            TenantUserModel.tenant_id.in_(tenant_ids),
            TenantUserModel.role == TENANT_ROLE_OWNER,
            TenantUserModel.status == 1,
            UserModel.status == 1,
            *_non_platform_member_filter(session),
        )
        .order_by(TenantUserModel.is_primary.desc(), UserModel.account)
    ).all()
    result = {}
    for tenant_id, user_id, account, name, email in rows:
        result.setdefault(
            int(tenant_id),
            {
                "owner_user_id": int(user_id),
                "owner_account": account,
                "owner_name": name,
                "owner_email": email,
            },
        )
    return result


def _tenant_bound_datasource_map(session: SessionDep, tenant_ids: list[int]) -> dict[int, dict]:
    ids = [int(tenant_id) for tenant_id in tenant_ids if int(tenant_id) != DEFAULT_TENANT_ID]
    if not ids or not _table_exists(session, CoreDatasource.__tablename__):
        return {}
    rows = session.exec(
        select(CoreDatasource.tenant_id, CoreDatasource.id, CoreDatasource.name)
        .where(CoreDatasource.tenant_id.in_(ids))
        .order_by(CoreDatasource.name)
    ).all()
    result = {}
    for tenant_id, datasource_id, datasource_name in rows:
        result.setdefault(
            int(tenant_id),
            {
                "bound_datasource_id": int(datasource_id),
                "bound_datasource_name": datasource_name,
                "bound_project_id": int(datasource_id),
                "bound_project_name": datasource_name,
            },
        )
    return result


def _tenant_bound_datasource_id(session: SessionDep, tenant_id: int) -> int | None:
    if int(tenant_id) == DEFAULT_TENANT_ID or not _table_exists(session, CoreDatasource.__tablename__):
        return None
    datasource_id = session.exec(
        select(CoreDatasource.id)
        .where(CoreDatasource.tenant_id == int(tenant_id))
        .order_by(CoreDatasource.id)
    ).first()
    return int(datasource_id) if datasource_id is not None else None


def _scope_member_datasource_payload_to_bound_datasource(
    session: SessionDep,
    *,
    tenant_id: int,
    datasource_ids: list[int] | None,
    datasource_role_map: dict[int, str] | None = None,
) -> tuple[list[int] | None, dict[int, str] | None]:
    if datasource_ids is None:
        return None, datasource_role_map

    bound_datasource_id = _tenant_bound_datasource_id(session, int(tenant_id))
    if bound_datasource_id is None:
        return [], {}

    requested_ids: set[int] = set()
    for datasource_id in datasource_ids or []:
        try:
            requested_ids.add(int(datasource_id))
        except (TypeError, ValueError):
            continue
    if bound_datasource_id not in requested_ids:
        return [], {}

    role_map = datasource_role_map or {}
    return [bound_datasource_id], {
        bound_datasource_id: (
            role_map.get(bound_datasource_id)
            or role_map.get(str(bound_datasource_id))
            or "viewer"
        )
    }


def _tenant_member_stats_map(session: SessionDep, tenant_ids: list[int]) -> dict[int, dict]:
    ids = [int(tenant_id) for tenant_id in tenant_ids]
    if not ids:
        return {}
    statement = (
        select(TenantUserModel.tenant_id, TenantUserModel.role, func.count())
        .where(
            TenantUserModel.tenant_id.in_(ids),
            TenantUserModel.status == 1,
        )
        .group_by(TenantUserModel.tenant_id, TenantUserModel.role)
    )
    if _table_exists(session, UserModel.__tablename__):
        statement = (
            statement
            .join(UserModel, UserModel.id == TenantUserModel.user_id)
            .where(UserModel.system_role.not_in(("system_admin", "collab_admin")))
        )
    rows = session.exec(statement).all()
    result: dict[int, dict] = {}
    for tenant_id, role, count in rows:
        tenant_stats = result.setdefault(
            int(tenant_id),
            {
                "admin_count": 0,
                "member_count": 0,
            },
        )
        normalized_role = normalize_tenant_role(role)
        if normalized_role in TENANT_ADMIN_ROLES:
            tenant_stats["admin_count"] += int(count or 0)
        else:
            tenant_stats["member_count"] += int(count or 0)
    return result


def _tenant_public_id(tenant: TenantModel | None) -> str:
    if tenant is None:
        return ""
    return str(getattr(tenant, "public_id", None) or "")


def _tenant_public_id_map(session: SessionDep, tenant_ids: list[int]) -> dict[int, str]:
    ids = [int(tenant_id) for tenant_id in tenant_ids if tenant_id is not None]
    if not ids:
        return {}
    rows = session.exec(select(TenantModel).where(TenantModel.id.in_(ids))).all()
    result: dict[int, str] = {}
    for tenant in rows:
        ensure_tenant_public_id(session, tenant)
        result[int(tenant.id)] = _tenant_public_id(tenant)
    return result


def _tenant_dto(
    tenant: TenantModel,
    *,
    role: str = TENANT_ROLE_OWNER,
    owner: dict | None = None,
    datasource: dict | None = None,
    member_stats: dict | None = None,
    include_operations: bool | None = None,
    join_time: int | None = None,
) -> TenantDTO:
    owner = owner or {}
    datasource = datasource or {}
    member_stats = member_stats or {}
    normalized_role = normalize_tenant_role(role)
    show_operations = normalized_role in TENANT_ADMIN_ROLES if include_operations is None else include_operations
    return TenantDTO(
        id=int(tenant.id),
        public_id=_tenant_public_id(tenant),
        name=tenant.name,
        role=normalized_role,
        plan=tenant.plan if show_operations else None,
        status=int(tenant.status),
        subscription_status=(getattr(tenant, "subscription_status", None) or "active") if show_operations else None,
        billing_mode=(getattr(tenant, "billing_mode", None) or "manual") if show_operations else None,
        trial_end_time=getattr(tenant, "trial_end_time", None) if show_operations else None,
        current_period_end_time=getattr(tenant, "current_period_end_time", None) if show_operations else None,
        contract_no=getattr(tenant, "contract_no", None) if show_operations else None,
        billing_contact=getattr(tenant, "billing_contact", None) if show_operations else None,
        billing_email=getattr(tenant, "billing_email", None) if show_operations else None,
        subscription_note=getattr(tenant, "subscription_note", None) if show_operations else None,
        create_time=int(tenant.create_time or 0) if show_operations else 0,
        update_time=int(tenant.update_time or 0) if show_operations else 0,
        owner_user_id=owner.get("owner_user_id") if show_operations else None,
        owner_account=owner.get("owner_account") if show_operations else None,
        owner_name=owner.get("owner_name") if show_operations else None,
        owner_email=owner.get("owner_email") if show_operations else None,
        bound_datasource_id=datasource.get("bound_datasource_id") if show_operations else None,
        bound_datasource_name=datasource.get("bound_datasource_name") if show_operations else None,
        bound_project_id=datasource.get("bound_project_id") if show_operations else None,
        bound_project_name=datasource.get("bound_project_name") if show_operations else None,
        admin_count=int(member_stats.get("admin_count") or 0) if show_operations else 0,
        member_count=int(member_stats.get("member_count") or 0) if show_operations else 0,
        join_time=int(join_time or 0),
        is_system_default=tenant.name == SAMPLE_TENANT_NAME,
    )


def _tenant_dto_list(session: SessionDep, rows: list[tuple[TenantModel, str, int | None]]) -> list[TenantDTO]:
    for tenant, _role, _join_time in rows:
        ensure_tenant_public_id(session, tenant)
    tenant_ids = [int(tenant.id) for tenant, _role, _join_time in rows]
    owner_map = _tenant_owner_map(session, tenant_ids)
    datasource_map = _tenant_bound_datasource_map(session, tenant_ids)
    member_stats_map = _tenant_member_stats_map(session, tenant_ids)
    return [
        _tenant_dto(
            tenant,
            role=role,
            owner=owner_map.get(int(tenant.id)),
            datasource=datasource_map.get(int(tenant.id)),
            member_stats=member_stats_map.get(int(tenant.id)),
            join_time=join_time,
        )
        for tenant, role, join_time in rows
    ]


def _tenant_admin_dto(session: SessionDep, tenant: TenantModel) -> TenantDTO:
    ensure_tenant_public_id(session, tenant)
    tenant_id = int(tenant.id)
    owner = _tenant_owner_map(session, [tenant_id]).get(tenant_id)
    datasource = _tenant_bound_datasource_map(session, [tenant_id]).get(tenant_id)
    member_stats = _tenant_member_stats_map(session, [tenant_id]).get(tenant_id)
    return _tenant_dto(
        tenant,
        owner=owner,
        datasource=datasource,
        member_stats=member_stats,
        include_operations=True,
    )


def _usage_dto(row) -> TenantUsageDailyDTO:
    return TenantUsageDailyDTO(
        tenant_id=int(row.tenant_id),
        usage_date=row.usage_date,
        metric=row.metric,
        request_count=int(row.request_count or 0),
        success_count=int(row.success_count or 0),
        failure_count=int(row.failure_count or 0),
        total_tokens=int(row.total_tokens or 0),
        task_count=int(row.task_count or 0),
        update_time=int(row.update_time or 0),
    )


def _usage_user_dto(row: dict) -> TenantUsageUserDTO:
    return TenantUsageUserDTO(**row)


def _timestamp_to_millis(value) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _millis_to_datetime(value: int | None) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000)
    except (TypeError, ValueError, OSError):
        return None


def _platform_date_key_from_millis(value: int | None) -> str | None:
    parsed = _millis_to_datetime(value)
    return parsed.strftime("%Y-%m-%d") if parsed else None


def _platform_date_key_from_usage(value: str | None) -> str | None:
    raw = (value or "").strip()
    return raw[:10] if raw else None


def _platform_start_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _platform_count(session: SessionDep, statement) -> int:
    try:
        return int(session.exec(statement).one() or 0)
    except Exception:
        return 0


def _overview_event_title(row: SystemLog) -> str:
    detail = (getattr(row, "operation_detail", None) or "").strip()
    if detail:
        return detail
    operation_type = getattr(row, "operation_type", None) or OperationType.VIEW.value
    operation_map = {
        OperationType.CREATE.value: "创建记录",
        OperationType.UPDATE.value: "更新记录",
        OperationType.UPDATE_STATUS.value: "更新状态",
        OperationType.DELETE.value: "删除记录",
        OperationType.LOGIN.value: "成员登录",
        OperationType.IMPORT.value: "导入记录",
        OperationType.EXPORT.value: "导出记录",
    }
    module_label = getattr(row, "module", None) or "system"
    return f"{operation_map.get(operation_type, '执行操作')} · {module_label}"


def _overview_event_description(row: SystemLog) -> str | None:
    resource_name = (getattr(row, "resource_name", None) or "").strip()
    remark = (getattr(row, "remark", None) or "").strip()
    if resource_name and remark:
        return f"{resource_name} · {remark[:160]}"
    if resource_name:
        return resource_name
    if remark:
        return remark[:200]
    return None


def _application_user_map(session: SessionDep, user_ids: list[int]) -> dict[int, dict]:
    if not user_ids or not _table_exists(session, UserModel.__tablename__):
        return {}
    rows = session.exec(
        select(UserModel.id, UserModel.account, UserModel.name, UserModel.email)
        .where(UserModel.id.in_(user_ids))
    ).all()
    return {
        int(user_id): {
            "account": account,
            "name": name,
            "email": email,
        }
        for user_id, account, name, email in rows
    }


def _application_dto(
    application,
    *,
    applicant: dict | None = None,
    inviter: dict | None = None,
    tenant_public_id: str | None = None,
    include_user_email: bool = True,
) -> TenantApplicationDTO:
    applicant = applicant or {}
    inviter = inviter or {}
    return TenantApplicationDTO(
        id=int(application.id),
        application_type=getattr(application, "application_type", None) or TENANT_APPLICATION_TYPE_CREATE,
        applicant_user_id=int(application.applicant_user_id),
        applicant_account=applicant.get("account"),
        applicant_name=applicant.get("name"),
        applicant_email=applicant.get("email") if include_user_email else None,
        invited_by_user_id=application.invited_by_user_id,
        inviter_account=inviter.get("account"),
        inviter_name=inviter.get("name"),
        inviter_email=inviter.get("email") if include_user_email else None,
        tenant_id=application.tenant_id,
        tenant_public_id=tenant_public_id,
        tenant_name=application.tenant_name,
        plan=application.plan,
        requested_role=application.requested_role,
        reason=application.reason,
        status=application.status,
        reviewer_user_id=application.reviewer_user_id,
        review_comment=application.review_comment,
        create_time=int(application.create_time or 0),
        update_time=int(application.update_time or 0),
        review_time=application.review_time,
    )


def _application_dto_list(
    session: SessionDep,
    applications,
    *,
    include_user_email: bool = True,
) -> list[TenantApplicationDTO]:
    user_ids = {
        int(application.applicant_user_id)
        for application in applications
        if getattr(application, "applicant_user_id", None)
    }
    user_ids.update(
        int(application.invited_by_user_id)
        for application in applications
        if getattr(application, "invited_by_user_id", None)
    )
    user_map = _application_user_map(session, list(user_ids))
    tenant_ids = {
        int(application.tenant_id)
        for application in applications
        if getattr(application, "tenant_id", None)
    }
    tenant_public_id_map = _tenant_public_id_map(session, list(tenant_ids))
    return [
        _application_dto(
            application,
            applicant=user_map.get(int(application.applicant_user_id)),
            inviter=user_map.get(int(application.invited_by_user_id)) if application.invited_by_user_id else None,
            tenant_public_id=tenant_public_id_map.get(int(application.tenant_id)) if application.tenant_id else None,
            include_user_email=include_user_email,
        )
        for application in applications
    ]


def _domain_dto(row: TenantDomainModel) -> TenantDomainDTO:
    return TenantDomainDTO(
        id=int(row.id),
        tenant_id=int(row.tenant_id),
        domain=row.domain,
        auto_join_role=row.auto_join_role,
        status=row.status,
        requested_by_user_id=row.requested_by_user_id,
        verified_by_user_id=row.verified_by_user_id,
        create_time=int(row.create_time or 0),
        update_time=int(row.update_time or 0),
        verify_time=row.verify_time,
    )


def _security_policy_dto(row: TenantSecurityPolicyModel | None, tenant_id: int) -> TenantSecurityPolicyDTO:
    if row is None:
        return TenantSecurityPolicyDTO(
            id=None,
            tenant_id=int(tenant_id),
            sso_required=False,
            session_timeout_minutes=None,
        )
    return TenantSecurityPolicyDTO(
        id=int(row.id),
        tenant_id=int(row.tenant_id),
        sso_required=bool(row.sso_required),
        session_timeout_minutes=row.session_timeout_minutes,
        create_time=int(row.create_time or 0),
        update_time=int(row.update_time or 0),
    )


def _data_request_dto(row: TenantDataRequestModel) -> TenantDataRequestDTO:
    return TenantDataRequestDTO(
        id=int(row.id),
        tenant_id=int(row.tenant_id),
        request_type=row.request_type,
        status=row.status,
        requested_by_user_id=int(row.requested_by_user_id),
        reviewer_user_id=row.reviewer_user_id,
        completed_by_user_id=row.completed_by_user_id,
        reason=row.reason,
        review_comment=row.review_comment,
        export_manifest=row.export_manifest,
        create_time=int(row.create_time or 0),
        update_time=int(row.update_time or 0),
        review_time=row.review_time,
        complete_time=row.complete_time,
    )


def _tenant_member_dto(session: SessionDep, current_user: CurrentUser, user: UserModel, membership: TenantUserModel) -> TenantMemberDTO:
    bound_datasource_id = _tenant_bound_datasource_id(session, int(membership.tenant_id))
    datasource_roles = list_user_datasource_roles(session, int(user.id), current_user)
    datasource_ids = [bound_datasource_id] if bound_datasource_id is not None else []
    datasource_role_map = (
        {bound_datasource_id: datasource_roles.get(bound_datasource_id) or "viewer"}
        if bound_datasource_id is not None
        else {}
    )
    return TenantMemberDTO(
        user_id=int(user.id),
        account=user.account,
        name=user.name,
        member_remark=(getattr(membership, "member_remark", None) or None),
        tenant_role=normalize_tenant_role(membership.role),
        is_primary=bool(membership.is_primary),
        create_time=int(membership.create_time or 0),
        project_ids=datasource_ids,
        project_role_map=datasource_role_map,
    )


def _require_manageable_tenant_member(
    session: SessionDep,
    current_user: CurrentUser,
    *,
    tenant_id: int,
    user_id: int,
) -> tuple[UserModel, TenantUserModel]:
    user = session.get(UserModel, int(user_id))
    membership = get_tenant_membership(session, int(user_id), tenant_id=int(tenant_id))
    if not user or not membership:
        raise HTTPException(status_code=404, detail="Tenant member not found")
    if is_high_privilege_user(user):
        raise HTTPException(status_code=403, detail="SaaS administrator cannot be managed as tenant member")
    if normalize_tenant_role(membership.role) == TENANT_ROLE_OWNER and not is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="Only system admin can manage tenant owner")
    return user, membership


def _assign_existing_user_to_current_tenant(
    session: SessionDep,
    current_user: CurrentUser,
    *,
    tenant_id: int,
    account: str,
    tenant_role: str,
    member_remark: str | None = None,
    datasource_ids: list[int] | None = None,
    datasource_role_map: dict[int, str] | None = None,
) -> tuple[UserModel, TenantUserModel]:
    normalized_account = (account or "").strip()
    user = session.exec(select(UserModel).where(UserModel.account == normalized_account)).first()
    if not user:
        raise ValueError("User does not exist")
    if is_high_privilege_user(user):
        raise ValueError("SaaS administrator cannot be added to tenant")
    membership = get_tenant_membership(session, int(user.id), tenant_id=int(tenant_id))
    if membership:
        raise ValueError("User already belongs to tenant")
    membership = assign_user_to_tenant(
        session,
        int(user.id),
        tenant_id=int(tenant_id),
        role=normalize_application_role(tenant_role, TENANT_APPLICATION_TYPE_JOIN),
        is_primary=False,
    )
    membership.member_remark = (member_remark or "").strip() or None
    session.add(membership)
    if datasource_ids is not None:
        datasource_ids, datasource_role_map = _scope_member_datasource_payload_to_bound_datasource(
            session,
            tenant_id=int(tenant_id),
            datasource_ids=datasource_ids,
            datasource_role_map=datasource_role_map,
        )
        update_user_datasources(
            session,
            current_user,
            int(user.id),
            datasource_ids or [],
            datasource_role_map,
        )
    return user, membership


def _resolve_owner_user(session: SessionDep, creator: TenantCreator) -> UserModel | None:
    if creator.owner_user_id:
        user = session.get(UserModel, int(creator.owner_user_id))
        if not user:
            raise ValueError("Tenant owner user does not exist")
        if is_high_privilege_user(user):
            raise ValueError("SaaS administrator cannot be tenant owner")
        return user

    owner_account = (creator.owner_account or "").strip()
    if not owner_account:
        return None

    existing = session.exec(select(UserModel).where(UserModel.account == owner_account)).first()
    if existing:
        if is_high_privilege_user(existing):
            raise ValueError("SaaS administrator cannot be tenant owner")
        return existing

    owner_name = (creator.owner_name or "").strip()
    owner_email = (creator.owner_email or "").strip()
    if not owner_name:
        raise ValueError("Tenant owner name is required")
    if not owner_email or not check_email_format(owner_email):
        raise ValueError("Tenant owner email format is invalid")
    user = UserModel(
        account=owner_account,
        name=owner_name,
        email=owner_email,
        status=1,
        origin=0,
        language="zh-CN",
        system_role=SYSTEM_ROLE_VIEWER,
    )
    session.add(user)
    session.flush()
    ensure_user_sample_workspace_membership(session, user)
    return user


@router.get("/current", response_model=TenantDTO)
async def current_tenant(session: SessionDep, current_tenant: CurrentTenant):
    datasource = _tenant_bound_datasource_map(session, [int(current_tenant.id)]).get(int(current_tenant.id))
    tenant = session.get(TenantModel, int(current_tenant.id))
    ensure_tenant_public_id(session, tenant)
    return TenantDTO(
        id=current_tenant.id,
        public_id=_tenant_public_id(tenant),
        name=current_tenant.name,
        role=current_tenant.role,
        bound_datasource_id=datasource.get("bound_datasource_id") if datasource else None,
        bound_datasource_name=datasource.get("bound_datasource_name") if datasource else None,
        bound_project_id=datasource.get("bound_project_id") if datasource else None,
        bound_project_name=datasource.get("bound_project_name") if datasource else None,
    )


@router.get("/list", response_model=list[TenantDTO])
async def tenant_list(session: SessionDep, current_user: CurrentUser):
    if is_platform_admin(current_user):
        tenants = list_tenants(session)
        return _tenant_dto_list(session, [(tenant, TENANT_ROLE_OWNER, None) for tenant in tenants])
    rows = list_user_tenant_memberships(session, int(current_user.id))
    return _tenant_dto_list(session, [(tenant, membership.role, membership.create_time) for tenant, membership in rows])


@router.get("/search", response_model=list[TenantSearchDTO])
async def search_tenants(
    session: SessionDep,
    current_user: CurrentUser,
    keyword: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(20, ge=1, le=50),
):
    limit_value = limit if isinstance(limit, int) else 20
    tenants = search_active_tenants(session, keyword=keyword, limit=limit_value)
    return [
        TenantSearchDTO(
            id=int(tenant.id),
            public_id=_tenant_public_id(tenant),
            name=tenant.name,
            plan=tenant.plan,
            status=int(tenant.status),
            subscription_status=getattr(tenant, "subscription_status", None) or "active",
            already_joined=user_belongs_to_tenant(session, int(current_user.id), int(tenant.id)),
        )
        for tenant in tenants
    ]


@router.get("/platform-overview", response_model=PlatformOverviewDTO)
async def platform_overview(
    session: SessionDep,
    current_user: CurrentUser,
    days: int = Query(7, ge=7, le=90),
):
    _require_platform_admin(current_user)
    if is_platform_workspace_delegate(current_user):
        raise HTTPException(status_code=403, detail="SaaS overview is only available in SaaS context")

    now = datetime.now()
    start_date = now.date() - timedelta(days=days - 1)
    start_datetime = datetime.combine(start_date, datetime.min.time())
    start_millis = _platform_start_millis(start_datetime)
    date_keys = [(start_date + timedelta(days=index)).strftime("%Y-%m-%d") for index in range(days)]
    tenant_filters = [
        TenantModel.id != DEFAULT_TENANT_ID,
        TenantModel.status >= 0,
    ]

    tenant_total = _platform_count(
        session,
        select(func.count()).select_from(TenantModel).where(*tenant_filters),
    )
    active_tenant_count = _platform_count(
        session,
        select(func.count()).select_from(TenantModel).where(*tenant_filters, TenantModel.status == 1),
    )
    disabled_tenant_count = _platform_count(
        session,
        select(func.count()).select_from(TenantModel).where(*tenant_filters, TenantModel.status == 0),
    )
    user_total = _platform_count(session, select(func.count()).select_from(UserModel))
    active_user_count = _platform_count(
        session,
        select(func.count()).select_from(UserModel).where(UserModel.status == 1),
    )
    new_user_count = _platform_count(
        session,
        select(func.count()).select_from(UserModel).where(UserModel.create_time >= start_millis),
    )
    platform_admin_count = _platform_count(
        session,
        select(func.count())
        .select_from(UserModel)
        .where(UserModel.system_role.in_(("system_admin", "collab_admin"))),
    )
    new_tenant_count = _platform_count(
        session,
        select(func.count()).select_from(TenantModel).where(*tenant_filters, TenantModel.create_time >= start_millis),
    )
    paying_tenant_count = _platform_count(
        session,
        select(func.count())
        .select_from(TenantModel)
        .where(
            *tenant_filters,
            TenantModel.subscription_status == "active",
            or_(
                TenantModel.plan != "default",
                TenantModel.billing_mode == "contract",
                TenantModel.contract_no.is_not(None),
            ),
        ),
    )
    trial_tenant_count = _platform_count(
        session,
        select(func.count())
        .select_from(TenantModel)
        .where(*tenant_filters, TenantModel.subscription_status == "trialing"),
    )
    past_due_tenant_count = _platform_count(
        session,
        select(func.count())
        .select_from(TenantModel)
        .where(*tenant_filters, TenantModel.subscription_status == "past_due"),
    )
    suspended_tenant_count = _platform_count(
        session,
        select(func.count())
        .select_from(TenantModel)
        .where(*tenant_filters, TenantModel.subscription_status == "suspended"),
    )
    cancelled_tenant_count = _platform_count(
        session,
        select(func.count())
        .select_from(TenantModel)
        .where(*tenant_filters, TenantModel.subscription_status == "cancelled"),
    )
    contract_tenant_count = _platform_count(
        session,
        select(func.count())
        .select_from(TenantModel)
        .where(
            *tenant_filters,
            or_(
                TenantModel.billing_mode == "contract",
                TenantModel.contract_no.is_not(None),
            ),
        ),
    )
    datasource_total = _platform_count(session, select(func.count()).select_from(CoreDatasource))
    bound_tenant_count = _platform_count(
        session,
        select(func.count(func.distinct(CoreDatasource.tenant_id)))
        .select_from(CoreDatasource)
        .where(CoreDatasource.tenant_id != DEFAULT_TENANT_ID),
    )
    dashboard_total = 0
    if _table_exists(session, CoreDashboard.__tablename__):
        dashboard_total = _platform_count(
            session,
            select(func.count())
            .select_from(CoreDashboard)
            .where(
                CoreDashboard.tenant_id != DEFAULT_TENANT_ID,
                CoreDashboard.node_type == "leaf",
                or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None)),
            ),
        )

    pending_workspace_application_count = _platform_count(
        session,
        select(func.count())
        .select_from(TenantApplicationModel)
        .where(
            TenantApplicationModel.application_type == TENANT_APPLICATION_TYPE_CREATE,
            TenantApplicationModel.status == "pending",
        ),
    )
    pending_data_request_count = _platform_count(
        session,
        select(func.count())
        .select_from(TenantDataRequestModel)
        .where(TenantDataRequestModel.status == "pending"),
    )

    usage_rows = []
    if _table_exists(session, TenantUsageDailyModel.__tablename__):
        usage_rows = session.exec(
            select(
                TenantUsageDailyModel.tenant_id,
                TenantUsageDailyModel.usage_date,
                func.coalesce(func.sum(TenantUsageDailyModel.request_count), 0).label("request_count"),
                func.coalesce(func.sum(TenantUsageDailyModel.failure_count), 0).label("failure_count"),
                func.coalesce(func.sum(TenantUsageDailyModel.total_tokens), 0).label("total_tokens"),
            )
            .where(
                TenantUsageDailyModel.tenant_id != DEFAULT_TENANT_ID,
                TenantUsageDailyModel.usage_date >= start_date.isoformat(),
                TenantUsageDailyModel.usage_date <= now.date().isoformat(),
            )
            .group_by(TenantUsageDailyModel.tenant_id, TenantUsageDailyModel.usage_date)
        ).all()

    trend_map: dict[str, dict[str, int]] = {
        key: {
            "tenant_created_count": 0,
            "user_created_count": 0,
            "active_tenant_count": 0,
            "request_count": 0,
            "failure_count": 0,
            "total_tokens": 0,
        }
        for key in date_keys
    }
    tenant_usage_map: dict[int, dict[str, int]] = {}
    active_tenant_day_map: dict[str, set[int]] = {key: set() for key in date_keys}
    for tenant_id, usage_date, request_count, failure_count, total_tokens in usage_rows:
        day_key = _platform_date_key_from_usage(usage_date)
        if day_key in trend_map:
            trend_map[day_key]["request_count"] += int(request_count or 0)
            trend_map[day_key]["failure_count"] += int(failure_count or 0)
            trend_map[day_key]["total_tokens"] += int(total_tokens or 0)
            if tenant_id is not None and int(request_count or 0) > 0:
                active_tenant_day_map[day_key].add(int(tenant_id))
        if tenant_id is not None:
            bucket = tenant_usage_map.setdefault(
                int(tenant_id),
                {"request_count": 0, "failure_count": 0, "total_tokens": 0},
            )
            bucket["request_count"] += int(request_count or 0)
            bucket["failure_count"] += int(failure_count or 0)
            bucket["total_tokens"] += int(total_tokens or 0)

    created_tenant_rows = session.exec(
        select(TenantModel.create_time).where(
            *tenant_filters,
            TenantModel.create_time >= start_millis,
        )
    ).all()
    for create_time in created_tenant_rows:
        day_key = _platform_date_key_from_millis(create_time)
        if day_key in trend_map:
            trend_map[day_key]["tenant_created_count"] += 1

    created_user_rows = session.exec(
        select(UserModel.create_time).where(UserModel.create_time >= start_millis)
    ).all()
    for create_time in created_user_rows:
        day_key = _platform_date_key_from_millis(create_time)
        if day_key in trend_map:
            trend_map[day_key]["user_created_count"] += 1
    for day_key, tenant_ids in active_tenant_day_map.items():
        trend_map[day_key]["active_tenant_count"] = len(tenant_ids)

    subscription_rows = session.exec(
        select(TenantModel.subscription_status, func.count(TenantModel.id))
        .where(*tenant_filters)
        .group_by(TenantModel.subscription_status)
    ).all()
    subscription_distribution = [
        PlatformOverviewDistributionItemDTO(key=status or "active", count=int(count or 0))
        for status, count in subscription_rows
    ]
    plan_rows = session.exec(
        select(TenantModel.plan, func.count(TenantModel.id))
        .where(*tenant_filters)
        .group_by(TenantModel.plan)
    ).all()
    plan_distribution = [
        PlatformOverviewDistributionItemDTO(key=plan or "default", count=int(count or 0))
        for plan, count in plan_rows
    ]

    datasource_distribution = [
        PlatformOverviewDistributionItemDTO(key="bound", count=int(bound_tenant_count or 0)),
        PlatformOverviewDistributionItemDTO(
            key="unbound",
            count=max(0, int(tenant_total or 0) - int(bound_tenant_count or 0)),
        ),
    ]

    tenant_name_rows = (
        session.exec(
            select(TenantModel).where(TenantModel.id.in_(list(tenant_usage_map.keys())))
        ).all()
        if tenant_usage_map
        else []
    )
    tenant_name_map = {int(tenant.id): tenant.name for tenant in tenant_name_rows}
    tenant_public_id_map = {}
    for tenant in tenant_name_rows:
        ensure_tenant_public_id(session, tenant)
        tenant_public_id_map[int(tenant.id)] = _tenant_public_id(tenant)
    top_tenant_usage = [
        PlatformOverviewTenantUsageDTO(
            tenant_id=tenant_id,
            tenant_public_id=tenant_public_id_map.get(tenant_id),
            tenant_name=tenant_name_map.get(tenant_id),
            request_count=values["request_count"],
            total_tokens=values["total_tokens"],
            failure_count=values["failure_count"],
        )
        for tenant_id, values in sorted(
            tenant_usage_map.items(),
            key=lambda item: (item[1]["request_count"], item[1]["total_tokens"]),
            reverse=True,
        )[:8]
    ]

    model_usage = []
    if _table_exists(session, ChatLog.__tablename__):
        token_expr = _chat_log_total_tokens_expr(session)
        model_rows = session.exec(
            select(
                ChatLog.ai_modal_id,
                func.count(ChatLog.id),
                func.coalesce(func.sum(token_expr), 0),
            )
            .where(
                ChatLog.tenant_id != DEFAULT_TENANT_ID,
                ChatLog.local_operation == False,  # noqa: E712
                ChatLog.finish_time >= start_datetime,
            )
            .group_by(ChatLog.ai_modal_id)
            .order_by(func.coalesce(func.sum(token_expr), 0).desc(), func.count(ChatLog.id).desc())
            .limit(8)
        ).all()
        model_ids = [int(model_id) for model_id, _count, _tokens in model_rows if model_id is not None]
        model_name_map = {}
        if model_ids and _table_exists(session, AiModelDetail.__tablename__):
            model_name_rows = session.exec(
                select(AiModelDetail.id, AiModelDetail.name).where(AiModelDetail.id.in_(model_ids))
            ).all()
            model_name_map = {int(model_id): name for model_id, name in model_name_rows}
        model_usage = [
            PlatformOverviewModelUsageDTO(
                model_id=int(model_id) if model_id is not None else None,
                model_name=model_name_map.get(int(model_id), str(model_id)) if model_id is not None else "default",
                request_count=int(request_count or 0),
                total_tokens=int(total_tokens or 0),
            )
            for model_id, request_count, total_tokens in model_rows
        ]

    recent_rows = session.exec(
        select(TenantModel)
        .where(*tenant_filters)
        .order_by(TenantModel.create_time.desc(), TenantModel.id.desc())
        .limit(8)
    ).all()
    recent_ids = [int(row.id) for row in recent_rows]
    datasource_map = _tenant_bound_datasource_map(session, recent_ids)
    owner_map = _tenant_owner_map(session, recent_ids)
    recent_tenants = [
        PlatformOverviewRecentTenantDTO(
            id=int(row.id),
            public_id=_tenant_public_id(row),
            name=row.name,
            plan=row.plan,
            status=int(row.status),
            subscription_status=getattr(row, "subscription_status", None) or "active",
            create_time=int(row.create_time or 0),
            bound_datasource_name=(datasource_map.get(int(row.id)) or {}).get("bound_datasource_name"),
            owner_account=(owner_map.get(int(row.id)) or {}).get("owner_account"),
        )
        for row in recent_rows
    ]

    request_count = sum(item["request_count"] for item in trend_map.values())
    failure_count = sum(item["failure_count"] for item in trend_map.values())
    total_tokens = sum(item["total_tokens"] for item in trend_map.values())
    active_usage_tenant_count = sum(
        1 for values in tenant_usage_map.values() if int(values.get("request_count") or 0) > 0
    )
    return PlatformOverviewDTO(
        days=days,
        summary=PlatformOverviewSummaryDTO(
            tenant_total=tenant_total,
            active_tenant_count=active_tenant_count,
            disabled_tenant_count=disabled_tenant_count,
            user_total=user_total,
            active_user_count=active_user_count,
            platform_admin_count=platform_admin_count,
            new_tenant_count=new_tenant_count,
            new_user_count=new_user_count,
            paying_tenant_count=paying_tenant_count,
            trial_tenant_count=trial_tenant_count,
            past_due_tenant_count=past_due_tenant_count,
            suspended_tenant_count=suspended_tenant_count,
            cancelled_tenant_count=cancelled_tenant_count,
            contract_tenant_count=contract_tenant_count,
            active_usage_tenant_count=active_usage_tenant_count,
            revenue_data_ready=False,
            revenue_amount=None,
            datasource_total=datasource_total,
            bound_datasource_count=bound_tenant_count,
            dashboard_total=dashboard_total,
            pending_workspace_application_count=pending_workspace_application_count,
            pending_data_request_count=pending_data_request_count,
            request_count=request_count,
            total_tokens=total_tokens,
            failure_count=failure_count,
        ),
        tenant_trend=[
            PlatformOverviewTrendPointDTO(
                date=day_key,
                tenant_created_count=values["tenant_created_count"],
                user_created_count=values["user_created_count"],
                active_tenant_count=values["active_tenant_count"],
                request_count=values["request_count"],
                failure_count=values["failure_count"],
                total_tokens=values["total_tokens"],
            )
            for day_key, values in trend_map.items()
        ],
        subscription_distribution=subscription_distribution,
        plan_distribution=plan_distribution,
        datasource_distribution=datasource_distribution,
        top_tenant_usage=top_tenant_usage,
        model_usage=model_usage,
        recent_tenants=recent_tenants,
    )


@router.get("/admin/list", response_model=list[TenantDTO])
async def admin_tenant_list(session: SessionDep, current_user: CurrentUser):
    _require_platform_admin(current_user)
    tenants = list_tenants(session, include_disabled=True)
    return _tenant_dto_list(session, [(tenant, TENANT_ROLE_OWNER, None) for tenant in tenants])


@router.get("/usage", response_model=list[TenantUsageDailyDTO])
async def tenant_usage(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    tenant_id: int | None = None,
    start_date: str | None = Query(default=None, max_length=10),
    end_date: str | None = Query(default=None, max_length=10),
    metric: str | None = Query(default=None, max_length=128),
    limit: int = Query(500, ge=1, le=5000),
):
    if is_platform_workspace_delegate(current_user):
        scoped_tenant_id = int(current_tenant.id)
        if tenant_id is not None and int(tenant_id) != scoped_tenant_id:
            raise HTTPException(status_code=403, detail="Tenant usage access denied")
    elif is_platform_admin(current_user):
        scoped_tenant_id = tenant_id
    else:
        _require_current_tenant_admin(current_user)
        scoped_tenant_id = int(current_tenant.id)
        if tenant_id is not None and int(tenant_id) != scoped_tenant_id:
            raise HTTPException(status_code=403, detail="Tenant usage access denied")
    rows = list_tenant_usage_daily(
        session,
        tenant_id=scoped_tenant_id,
        start_date=start_date,
        end_date=end_date,
        metric=metric,
        limit=limit,
    )
    return [_usage_dto(row) for row in rows]


@router.get("/usage/user", response_model=list[TenantUsageUserDTO])
async def tenant_usage_by_user(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    tenant_id: int | None = None,
    start_date: str | None = Query(default=None, max_length=10),
    end_date: str | None = Query(default=None, max_length=10),
    limit: int = Query(100, ge=1, le=500),
):
    if is_platform_workspace_delegate(current_user):
        scoped_tenant_id = int(current_tenant.id)
        if tenant_id is not None and int(tenant_id) != scoped_tenant_id:
            raise HTTPException(status_code=403, detail="Tenant usage access denied")
    elif is_platform_admin(current_user):
        scoped_tenant_id = tenant_id if tenant_id is not None else int(current_tenant.id)
    else:
        _require_current_tenant_admin(current_user)
        scoped_tenant_id = int(current_tenant.id)
        if tenant_id is not None and int(tenant_id) != scoped_tenant_id:
            raise HTTPException(status_code=403, detail="Tenant usage access denied")
    rows = list_tenant_usage_by_user(
        session,
        tenant_id=int(scoped_tenant_id),
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    return [_usage_user_dto(row) for row in rows]


@router.get("/overview", response_model=TenantOverviewDTO)
async def tenant_overview(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    days: int = Query(7, ge=7, le=30),
):
    if is_platform_admin(current_user) and not is_platform_workspace_delegate(current_user):
        raise HTTPException(status_code=403, detail="SaaS admin does not have tenant overview")
    _require_current_tenant_admin(current_user)

    tenant_id = int(current_tenant.id)
    tenant_name = current_tenant.name or str(current_tenant.id)

    current_date = datetime.now()
    start_date = current_date.date() - timedelta(days=days - 1)
    start_datetime = datetime.combine(start_date, datetime.min.time())
    previous_start_datetime = start_datetime - timedelta(days=days)

    member_statement = (
        select(func.count())
        .select_from(TenantUserModel)
        .where(
            TenantUserModel.tenant_id == tenant_id,
            TenantUserModel.status == 1,
        )
    )
    if _table_exists(session, UserModel.__tablename__):
        member_statement = (
            member_statement
            .join(UserModel, UserModel.id == TenantUserModel.user_id)
            .where(UserModel.system_role.not_in(("system_admin", "collab_admin")))
        )
    member_total = session.exec(member_statement).one() or 0

    pending_member_application_count = session.exec(
        select(func.count())
        .select_from(TenantApplicationModel)
        .where(
            TenantApplicationModel.tenant_id == tenant_id,
            TenantApplicationModel.application_type == TENANT_APPLICATION_TYPE_JOIN,
            TenantApplicationModel.status == "pending",
        )
    ).one() or 0

    datasource_total = session.exec(
        select(func.count())
        .select_from(CoreDatasource)
        .where(CoreDatasource.tenant_id == tenant_id)
    ).one() or 0

    dashboard_total = 0
    if _table_exists(session, CoreDashboard.__tablename__):
        dashboard_total = session.exec(
            select(func.count())
            .select_from(CoreDashboard)
            .where(
                CoreDashboard.tenant_id == tenant_id,
                CoreDashboard.node_type == "leaf",
                or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None)),
            )
        ).one() or 0

    terminology_total = 0
    if _table_exists(session, Terminology.__tablename__):
        terminology_total = session.exec(
            select(func.count())
            .select_from(Terminology)
            .where(
                Terminology.tenant_id == tenant_id,
                Terminology.scope == SemanticRecordScopeEnum.TENANT.value,
                or_(Terminology.enabled == True, Terminology.enabled.is_(None)),
            )
        ).one() or 0

    training_total = 0
    if _table_exists(session, DataTraining.__tablename__):
        training_total = session.exec(
            select(func.count())
            .select_from(DataTraining)
            .where(
                DataTraining.tenant_id == tenant_id,
                DataTraining.scope == SemanticRecordScopeEnum.TENANT.value,
                or_(DataTraining.enabled == True, DataTraining.enabled.is_(None)),
            )
        ).one() or 0

    custom_agent_total = 0
    data_skill_total = 0
    if _table_exists(session, CustomPrompt.__tablename__):
        custom_agent_total = session.exec(
            select(func.count())
            .select_from(CustomPrompt)
            .where(
                CustomPrompt.tenant_id == tenant_id,
                or_(
                    CustomPrompt.type != CustomPromptTypeEnum.DATA_SKILL.value,
                    CustomPrompt.type.is_(None),
                ),
                or_(
                    CustomPrompt.visibility_scope != CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value,
                    CustomPrompt.visibility_scope.is_(None),
                ),
            )
        ).one() or 0
        data_skill_total = session.exec(
            select(func.count())
            .select_from(CustomPrompt)
            .where(
                CustomPrompt.tenant_id == tenant_id,
                CustomPrompt.type == CustomPromptTypeEnum.DATA_SKILL.value,
                or_(
                    CustomPrompt.visibility_scope != CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value,
                    CustomPrompt.visibility_scope.is_(None),
                ),
                or_(CustomPrompt.active == True, CustomPrompt.active.is_(None)),
            )
        ).one() or 0

    embedded_total = 0
    if _table_exists(session, AssistantModel.__tablename__):
        embedded_total = session.exec(
            select(func.count())
            .select_from(AssistantModel)
            .where(
                AssistantModel.tenant_id == tenant_id,
                AssistantModel.type == 4,
            )
        ).one() or 0

    role_statement = (
        select(TenantUserModel.role, func.count())
        .where(
            TenantUserModel.tenant_id == tenant_id,
            TenantUserModel.status == 1,
        )
        .group_by(TenantUserModel.role)
    )
    if _table_exists(session, UserModel.__tablename__):
        role_statement = (
            role_statement
            .join(UserModel, UserModel.id == TenantUserModel.user_id)
            .where(UserModel.system_role.not_in(("system_admin", "collab_admin")))
        )
    role_rows = session.exec(role_statement).all()

    role_distribution = [
        TenantOverviewRoleItemDTO(role=normalize_tenant_role(role), count=int(count or 0))
        for role, count in role_rows
    ]

    activity_statement = (
        select(SystemLog.user_id, SystemLog.create_time)
        .join(
            TenantUserModel,
            (TenantUserModel.user_id == SystemLog.user_id)
            & (TenantUserModel.tenant_id == tenant_id)
            & (TenantUserModel.status == 1),
        )
        .where(
            SystemLog.tenant_id == tenant_id,
            SystemLog.operation_type != OperationType.LOGIN.value,
            SystemLog.create_time >= start_datetime,
            SystemLog.user_id.is_not(None),
        )
        .order_by(SystemLog.create_time.asc())
    )
    if _table_exists(session, UserModel.__tablename__):
        activity_statement = (
            activity_statement
            .join(UserModel, UserModel.id == SystemLog.user_id)
            .where(UserModel.system_role.not_in(("system_admin", "collab_admin")))
        )
    activity_rows = session.exec(activity_statement).all()

    login_statement = (
        select(SystemLog.user_id, SystemLog.create_time)
        .join(
            TenantUserModel,
            (TenantUserModel.user_id == SystemLog.user_id)
            & (TenantUserModel.tenant_id == tenant_id)
            & (TenantUserModel.status == 1),
        )
        .where(
            SystemLog.tenant_id == tenant_id,
            SystemLog.operation_type == OperationType.LOGIN.value,
            SystemLog.create_time >= start_datetime,
            SystemLog.user_id.is_not(None),
        )
        .order_by(SystemLog.create_time.asc())
    )
    if _table_exists(session, UserModel.__tablename__):
        login_statement = (
            login_statement
            .join(UserModel, UserModel.id == SystemLog.user_id)
            .where(UserModel.system_role.not_in(("system_admin", "collab_admin")))
        )
    login_rows = session.exec(login_statement).all()

    active_member_ids = {
        int(user_id)
        for user_id, _create_time in activity_rows
        if user_id not in (None, "")
    }

    trend_map: dict[str, dict[str, int]] = {
        (start_date + timedelta(days=index)).strftime("%Y-%m-%d"): {
            "active_member_count": 0,
            "activity_count": 0,
            "login_count": 0,
        }
        for index in range(days)
    }
    daily_member_map: dict[str, set[int]] = {key: set() for key in trend_map}

    for user_id, create_time in activity_rows:
        if create_time is None:
            continue
        day_key = create_time.strftime("%Y-%m-%d")
        if day_key not in trend_map:
            continue
        trend_map[day_key]["activity_count"] += 1
        if user_id not in (None, ""):
            daily_member_map[day_key].add(int(user_id))

    for _user_id, create_time in login_rows:
        if create_time is None:
            continue
        day_key = create_time.strftime("%Y-%m-%d")
        if day_key not in trend_map:
            continue
        trend_map[day_key]["login_count"] += 1

    activity_trend = []
    for day_key, values in trend_map.items():
        activity_trend.append(
            TenantOverviewTrendPointDTO(
                date=day_key,
                active_member_count=len(daily_member_map[day_key]),
                activity_count=int(values["activity_count"]),
                login_count=int(values["login_count"]),
            )
        )

    domain_binding_count = 0
    if _table_exists(session, TenantDomainModel.__tablename__):
        domain_binding_count = session.exec(
            select(func.count())
            .select_from(TenantDomainModel)
            .where(
                TenantDomainModel.tenant_id == tenant_id,
                TenantDomainModel.status == "verified",
            )
        ).one() or 0

    active_member_count = len(active_member_ids)
    todos: list[TenantOverviewTodoDTO] = []
    if pending_member_application_count > 0:
        todos.append(
            TenantOverviewTodoDTO(
                key="pending_member_application_count",
                level="warning",
                count=int(pending_member_application_count),
                route="/system/member-access",
            )
        )
    if dashboard_total <= 0:
        todos.append(
            TenantOverviewTodoDTO(
                key="missing_dashboard",
                level="normal",
                route="/dashboard/index",
            )
        )
    if domain_binding_count <= 0:
        todos.append(
            TenantOverviewTodoDTO(
                key="unverified_domain",
                level="normal",
                route="/system/member-access",
            )
        )
    if not todos:
        todos.append(
            TenantOverviewTodoDTO(
                key="space_ready",
                level="healthy",
                route="/system/usage",
            )
        )

    recent_event_rows = session.exec(
        select(SystemLog)
        .where(
            SystemLog.tenant_id == tenant_id,
            SystemLog.create_time >= start_datetime,
        )
        .order_by(SystemLog.create_time.desc())
        .limit(8)
    ).all()

    recent_events = [
        TenantOverviewEventDTO(
            id=str(row.id),
            title=_overview_event_title(row),
            description=_overview_event_description(row),
            create_time=_timestamp_to_millis(getattr(row, "create_time", None)),
            operator_name=getattr(row, "user_name", None),
            module=getattr(row, "module", None),
            resource_name=getattr(row, "resource_name", None),
        )
        for row in recent_event_rows
    ]

    last_activity_subquery = (
        select(
            SystemLog.user_id.label("user_id"),
            func.max(SystemLog.create_time).label("last_active_time"),
        )
        .where(
            SystemLog.tenant_id == tenant_id,
            SystemLog.operation_type != OperationType.LOGIN.value,
            SystemLog.user_id.is_not(None),
        )
        .group_by(SystemLog.user_id)
        .subquery()
    )
    member_activity_rows = []
    if _table_exists(session, UserModel.__tablename__):
        member_activity_rows = session.exec(
            select(
                TenantUserModel.user_id,
                UserModel.account,
                UserModel.name,
                TenantUserModel.role,
                last_activity_subquery.c.last_active_time,
            )
            .join(UserModel, UserModel.id == TenantUserModel.user_id)
            .outerjoin(last_activity_subquery, last_activity_subquery.c.user_id == TenantUserModel.user_id)
            .where(
                TenantUserModel.tenant_id == tenant_id,
                TenantUserModel.status == 1,
                UserModel.system_role.not_in(("system_admin", "collab_admin")),
            )
            .order_by(
                last_activity_subquery.c.last_active_time.desc().nulls_last(),
                TenantUserModel.role,
                UserModel.account,
            )
            .limit(8)
        ).all()

    member_last_activities = [
        TenantOverviewMemberActivityDTO(
            user_id=int(user_id),
            account=account,
            name=name,
            tenant_role=normalize_tenant_role(role),
            last_active_time=_timestamp_to_millis(last_active_time),
        )
        for user_id, account, name, role, last_active_time in member_activity_rows
    ]

    return TenantOverviewDTO(
        tenant_id=tenant_id,
        tenant_public_id=getattr(current_tenant, "public_id", None),
        tenant_name=tenant_name,
        days=days,
        summary=TenantOverviewSummaryDTO(
            member_total=int(member_total or 0),
            active_member_count=active_member_count,
            datasource_total=int(datasource_total or 0),
            dashboard_total=int(dashboard_total or 0),
            pending_member_application_count=int(pending_member_application_count or 0),
        ),
        activity_trend=activity_trend,
        assets=[
            TenantOverviewAssetItemDTO(key="datasource", count=int(datasource_total or 0)),
            TenantOverviewAssetItemDTO(key="dashboard", count=int(dashboard_total or 0)),
            TenantOverviewAssetItemDTO(
                key="data_skill",
                count=int(terminology_total or 0) + int(training_total or 0) + int(data_skill_total or 0),
            ),
            TenantOverviewAssetItemDTO(key="custom_agent", count=int(custom_agent_total or 0)),
            TenantOverviewAssetItemDTO(key="embedded", count=int(embedded_total or 0)),
        ],
        role_distribution=role_distribution,
        todos=todos,
        recent_events=recent_events,
        member_last_activities=member_last_activities,
    )


@router.get("/member/list", response_model=list[TenantMemberDTO])
async def tenant_member_list(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    keyword: str | None = Query(None, max_length=100),
):
    _require_current_tenant_admin(current_user)
    statement = (
        select(UserModel, TenantUserModel)
        .join(TenantUserModel, TenantUserModel.user_id == UserModel.id)
        .where(
            TenantUserModel.tenant_id == int(current_tenant.id),
            TenantUserModel.status == 1,
            *_non_platform_member_filter(session),
        )
        .order_by(TenantUserModel.role, UserModel.account)
    )
    if keyword:
        keyword_pattern = f"%{keyword.strip()}%"
        statement = statement.where(
            or_(
                UserModel.account.ilike(keyword_pattern),
                UserModel.name.ilike(keyword_pattern),
                TenantUserModel.member_remark.ilike(keyword_pattern),
            )
        )
    rows = session.exec(statement).all()
    return [
        _tenant_member_dto(session, current_user, user, membership)
        for user, membership in rows
        if not is_high_privilege_user(user)
    ]


@router.post("/member", response_model=TenantMemberDTO)
async def add_tenant_member(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    creator: TenantMemberCreator,
):
    _require_current_tenant_admin(current_user)
    try:
        user, membership = _assign_existing_user_to_current_tenant(
            session,
            current_user,
            tenant_id=int(current_tenant.id),
            account=creator.account,
            tenant_role=creator.tenant_role,
            member_remark=creator.member_remark,
            datasource_ids=creator.project_ids,
            datasource_role_map=creator.project_role_map,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.CREATE,
        detail="添加工作空间成员",
        module=OperationModules.TENANT,
        tenant_id=int(current_tenant.id),
        resource_id=user.id,
        resource_name=user.account,
        remark=f"user_id={user.id}; tenant_role={membership.role}; member_remark_set={bool(membership.member_remark)}",
    )
    return _tenant_member_dto(session, current_user, user, membership)


@router.post("/member/bulk", response_model=list[TenantBulkMemberResult])
async def bulk_add_tenant_members(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    creator: TenantBulkMemberCreator,
):
    _require_current_tenant_admin(current_user)
    results: list[TenantBulkMemberResult] = []
    seen = set()
    created_count = 0
    for raw_account in creator.accounts:
        account = (raw_account or "").strip()
        if not account or account in seen:
            continue
        seen.add(account)
        try:
            user, _membership = _assign_existing_user_to_current_tenant(
                session,
                current_user,
                tenant_id=int(current_tenant.id),
                account=account,
                tenant_role=creator.tenant_role,
            )
            created_count += 1
            results.append(TenantBulkMemberResult(account=account, status="created", user_id=int(user.id)))
        except ValueError as exc:
            results.append(TenantBulkMemberResult(account=account, status="failed", message=str(exc)))
    if created_count:
        _write_tenant_audit(
            session,
            current_user,
            operation_type=OperationType.CREATE,
            detail="批量添加工作空间成员",
            module=OperationModules.TENANT,
            tenant_id=int(current_tenant.id),
            resource_name=current_tenant.name,
            remark=f"created={created_count}; total={len(results)}",
        )
    return results


@router.put("/member/{user_id}", response_model=TenantMemberDTO)
async def update_tenant_member(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    user_id: int,
    editor: TenantMemberEditor,
):
    _require_current_tenant_admin(current_user)
    user, membership = _require_manageable_tenant_member(
        session,
        current_user,
        tenant_id=int(current_tenant.id),
        user_id=user_id,
    )
    membership.role = normalize_application_role(editor.tenant_role, TENANT_APPLICATION_TYPE_JOIN)
    membership.member_remark = (editor.member_remark or "").strip() or None
    session.add(membership)
    if editor.project_ids is not None:
        datasource_ids, datasource_role_map = _scope_member_datasource_payload_to_bound_datasource(
            session,
            tenant_id=int(current_tenant.id),
            datasource_ids=editor.project_ids,
            datasource_role_map=editor.project_role_map,
        )
        update_user_datasources(
            session,
            current_user,
            int(user.id),
            datasource_ids or [],
            datasource_role_map,
        )
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE,
        detail="更新工作空间成员属性",
        module=OperationModules.TENANT,
        tenant_id=int(current_tenant.id),
        resource_id=user.id,
        resource_name=user.account,
        remark=f"user_id={user.id}; tenant_role={membership.role}; member_remark_set={bool(membership.member_remark)}",
    )
    return _tenant_member_dto(session, current_user, user, membership)


@router.delete("/member/{user_id}", response_model=TenantMemberDTO)
async def remove_tenant_member(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    user_id: int,
):
    _require_current_tenant_admin(current_user)
    user, membership = _require_manageable_tenant_member(
        session,
        current_user,
        tenant_id=int(current_tenant.id),
        user_id=user_id,
    )
    try:
        removed_membership = remove_user_from_tenant(session, int(user.id), tenant_id=int(current_tenant.id))
        _remove_tenant_project_permissions(
            session,
            tenant_id=int(current_tenant.id),
            user_id=int(user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.DELETE,
        detail="移出工作空间成员",
        module=OperationModules.TENANT,
        tenant_id=int(current_tenant.id),
        resource_id=user.id,
        resource_name=user.account,
        remark=f"user_id={user.id}; tenant_role={membership.role}",
    )
    return _tenant_member_dto(session, current_user, user, removed_membership)


@router.post("/application", response_model=TenantApplicationDTO)
async def submit_tenant_application(
    session: SessionDep,
    current_user: CurrentUser,
    creator: TenantApplicationCreator,
):
    try:
        application = create_tenant_application(
            session,
            applicant_user_id=int(current_user.id),
            application_type=creator.application_type,
            tenant_id=creator.tenant_id,
            tenant_name=creator.tenant_name,
            plan=creator.plan,
            reason=creator.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    detail = "提交工作空间创建申请" if application.application_type == TENANT_APPLICATION_TYPE_CREATE else "提交加入工作空间申请"
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.CREATE,
        detail=detail,
        module=OperationModules.TENANT_APPLICATION,
        tenant_id=_application_audit_tenant_id(current_user, application),
        resource_id=application.id,
        resource_name=application.tenant_name,
        remark=_application_audit_remark(application),
    )
    return _application_dto(application)


@router.get("/application/my", response_model=list[TenantApplicationDTO])
async def my_tenant_applications(
    session: SessionDep,
    current_user: CurrentUser,
    status: str | None = None,
):
    applications = list_tenant_applications(
        session,
        applicant_user_id=int(current_user.id),
        status=status,
    )
    return _application_dto_list(session, applications)


@router.delete("/application/{application_id}", response_model=TenantApplicationDTO)
async def cancel_my_tenant_application(
    session: SessionDep,
    current_user: CurrentUser,
    application_id: int,
):
    application = session.get(TenantApplicationModel, application_id)
    if (
        not application
        or int(application.applicant_user_id) != int(current_user.id)
        or application.application_type not in {TENANT_APPLICATION_TYPE_CREATE, TENANT_APPLICATION_TYPE_JOIN}
    ):
        raise HTTPException(status_code=404, detail="Tenant application not found")
    try:
        application = cancel_tenant_application(
            session,
            application_id=application_id,
            reviewer_user_id=int(current_user.id),
            review_comment="cancelled by applicant",
            allowed_types={TENANT_APPLICATION_TYPE_CREATE, TENANT_APPLICATION_TYPE_JOIN},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    detail = "取消工作空间创建申请" if application.application_type == TENANT_APPLICATION_TYPE_CREATE else "取消加入工作空间申请"
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE_STATUS,
        detail=detail,
        module=OperationModules.TENANT_APPLICATION,
        tenant_id=_application_audit_tenant_id(current_user, application),
        resource_id=application.id,
        resource_name=application.tenant_name,
        remark=_application_audit_remark(application),
    )
    return _application_dto_list(session, [application])[0]


@router.get("/application/admin/list", response_model=list[TenantApplicationDTO])
async def admin_tenant_applications(
    session: SessionDep,
    current_user: CurrentUser,
    status: str | None = None,
):
    _require_platform_admin(current_user)
    applications = list_tenant_applications(
        session,
        application_type=TENANT_APPLICATION_TYPE_CREATE,
        status=status,
    )
    return _application_dto_list(session, applications)


@router.post("/application/{application_id}/review", response_model=TenantApplicationDTO)
async def review_tenant_application(
    session: SessionDep,
    current_user: CurrentUser,
    application_id: int,
    dto: TenantApplicationReview,
):
    _require_platform_admin(current_user)
    try:
        if dto.approved:
            application, _tenant = approve_tenant_application(
                session,
                application_id=application_id,
                reviewer_user_id=int(current_user.id),
                review_comment=dto.review_comment,
                allowed_types={TENANT_APPLICATION_TYPE_CREATE},
            )
        else:
            application = reject_tenant_application(
                session,
                application_id=application_id,
                reviewer_user_id=int(current_user.id),
                review_comment=dto.review_comment,
                allowed_types={TENANT_APPLICATION_TYPE_CREATE},
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE_STATUS,
        detail="审核工作空间创建申请通过" if dto.approved else "审核工作空间创建申请拒绝",
        module=OperationModules.TENANT_APPLICATION,
        tenant_id=_application_audit_tenant_id(current_user, application),
        resource_id=application.id,
        resource_name=application.tenant_name,
        remark=_application_audit_remark(application),
    )
    return _application_dto_list(session, [application])[0]


@router.get("/application/tenant/list", response_model=list[TenantApplicationDTO])
async def tenant_join_applications(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    status: str | None = None,
):
    _require_current_tenant_admin(current_user)
    applications = list_tenant_applications(
        session,
        tenant_id=int(current_tenant.id),
        application_type=TENANT_APPLICATION_TYPE_JOIN,
        status=status,
    )
    return _application_dto_list(session, applications, include_user_email=False)


@router.post("/application/tenant/{application_id}/review", response_model=TenantApplicationDTO)
async def review_tenant_join_application(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    application_id: int,
    dto: TenantApplicationReview,
):
    _require_current_tenant_admin(current_user)
    application = session.get(TenantApplicationModel, application_id)
    if (
        not application
        or application.application_type != TENANT_APPLICATION_TYPE_JOIN
        or int(application.tenant_id or 0) != int(current_tenant.id)
    ):
        raise HTTPException(status_code=404, detail="Tenant join application not found")
    try:
        if dto.approved:
            application, _tenant = approve_tenant_application(
                session,
                application_id=application_id,
                reviewer_user_id=int(current_user.id),
                review_comment=dto.review_comment,
                allowed_types={TENANT_APPLICATION_TYPE_JOIN},
            )
        else:
            application = reject_tenant_application(
                session,
                application_id=application_id,
                reviewer_user_id=int(current_user.id),
                review_comment=dto.review_comment,
                allowed_types={TENANT_APPLICATION_TYPE_JOIN},
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE_STATUS,
        detail="审核加入工作空间申请通过" if dto.approved else "审核加入工作空间申请拒绝",
        module=OperationModules.TENANT_APPLICATION,
        tenant_id=int(current_tenant.id),
        resource_id=application.id,
        resource_name=application.tenant_name,
        remark=_application_audit_remark(application),
    )
    return _application_dto_list(session, [application], include_user_email=False)[0]


@router.post("/invitation", response_model=TenantApplicationDTO)
async def invite_tenant_member(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    creator: TenantInvitationCreator,
):
    _require_current_tenant_admin(current_user)
    user = session.exec(select(UserModel).where(UserModel.account == creator.account.strip())).first()
    if not user:
        raise HTTPException(status_code=404, detail="User does not exist")
    if is_high_privilege_user(user):
        raise HTTPException(status_code=400, detail="SaaS administrator cannot be invited to tenant")
    try:
        invitation = create_tenant_invitation(
            session,
            tenant_id=int(current_tenant.id),
            invitee_user_id=int(user.id),
            invited_by_user_id=int(current_user.id),
            requested_role=creator.requested_role,
            reason=creator.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.CREATE,
        detail="邀请工作空间成员",
        module=OperationModules.TENANT_APPLICATION,
        tenant_id=int(current_tenant.id),
        resource_id=invitation.id,
        resource_name=invitation.tenant_name,
        remark=_application_audit_remark(invitation),
    )
    return _application_dto_list(session, [invitation], include_user_email=False)[0]


@router.post("/invitation/bulk", response_model=list[TenantBulkInviteResult])
async def bulk_invite_tenant_members(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    creator: TenantBulkInviteCreator,
):
    _require_current_tenant_admin(current_user)
    results: list[TenantBulkInviteResult] = []
    seen = set()
    for raw_account in creator.accounts:
        account = (raw_account or "").strip()
        if not account or account in seen:
            continue
        seen.add(account)
        user = session.exec(select(UserModel).where(UserModel.account == account)).first()
        if not user:
            results.append(TenantBulkInviteResult(account=account, status="failed", message="User does not exist"))
            continue
        if is_high_privilege_user(user):
            results.append(
                TenantBulkInviteResult(
                    account=account,
                    status="failed",
                    message="SaaS administrator cannot be invited to tenant",
                )
            )
            continue
        try:
            invitation = create_tenant_invitation(
                session,
                tenant_id=int(current_tenant.id),
                invitee_user_id=int(user.id),
                invited_by_user_id=int(current_user.id),
                requested_role=creator.requested_role,
                reason=creator.reason,
            )
            results.append(
                TenantBulkInviteResult(
                    account=account,
                    status="created",
                    application_id=int(invitation.id),
                )
            )
        except ValueError as exc:
            results.append(TenantBulkInviteResult(account=account, status="failed", message=str(exc)))
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.IMPORT,
        detail="批量邀请工作空间成员",
        module=OperationModules.TENANT_APPLICATION,
        tenant_id=int(current_tenant.id),
        resource_name=current_tenant.name,
        remark=f"total={len(seen)}; created={sum(1 for item in results if item.status == 'created')}",
    )
    return results


@router.get("/invitation/list", response_model=list[TenantApplicationDTO])
async def tenant_invitations(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    status: str | None = None,
):
    _require_current_tenant_admin(current_user)
    applications = list_tenant_applications(
        session,
        tenant_id=int(current_tenant.id),
        application_type=TENANT_APPLICATION_TYPE_INVITE,
        status=status,
    )
    return _application_dto_list(session, applications, include_user_email=False)


@router.get("/invitation/my", response_model=list[TenantApplicationDTO])
async def my_tenant_invitations(
    session: SessionDep,
    current_user: CurrentUser,
    status: str | None = None,
):
    applications = list_tenant_applications(
        session,
        applicant_user_id=int(current_user.id),
        application_type=TENANT_APPLICATION_TYPE_INVITE,
        status=status,
    )
    return _application_dto_list(session, applications)


@router.post("/owner/transfer", response_model=TenantDTO)
async def transfer_current_tenant_owner(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    dto: TenantOwnerTransfer,
):
    _require_current_tenant_owner(current_user)
    target_user = session.get(UserModel, int(dto.target_user_id))
    if not target_user or int(target_user.status) != 1:
        raise HTTPException(status_code=404, detail="Target user does not exist")
    if is_high_privilege_user(target_user):
        raise HTTPException(status_code=400, detail="SaaS administrator cannot be tenant owner")
    try:
        transfer_tenant_owner(
            session,
            tenant_id=int(current_tenant.id),
            target_user_id=int(target_user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE,
        detail="转移工作空间所有者",
        module=OperationModules.TENANT,
        tenant_id=int(current_tenant.id),
        resource_id=target_user.id,
        resource_name=target_user.name,
        remark=f"tenant_id={current_tenant.id}; target_user_id={target_user.id}",
    )
    tenant = session.get(TenantModel, int(current_tenant.id))
    return _tenant_dto(tenant, owner={
        "owner_user_id": int(target_user.id),
        "owner_account": target_user.account,
        "owner_name": target_user.name,
        "owner_email": target_user.email,
    })


@router.post("/invitation/{application_id}/respond", response_model=TenantApplicationDTO)
async def respond_tenant_invitation(
    session: SessionDep,
    current_user: CurrentUser,
    application_id: int,
    dto: TenantApplicationReview,
):
    application = session.get(TenantApplicationModel, application_id)
    if (
        not application
        or application.application_type != TENANT_APPLICATION_TYPE_INVITE
        or int(application.applicant_user_id) != int(current_user.id)
    ):
        raise HTTPException(status_code=404, detail="Tenant invitation not found")
    try:
        if dto.approved:
            application, _tenant = approve_tenant_application(
                session,
                application_id=application_id,
                reviewer_user_id=int(current_user.id),
                review_comment=dto.review_comment,
                allowed_types={TENANT_APPLICATION_TYPE_INVITE},
            )
        else:
            application = reject_tenant_application(
                session,
                application_id=application_id,
                reviewer_user_id=int(current_user.id),
                review_comment=dto.review_comment,
                allowed_types={TENANT_APPLICATION_TYPE_INVITE},
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE_STATUS,
        detail="接受工作空间邀请" if dto.approved else "拒绝工作空间邀请",
        module=OperationModules.TENANT_APPLICATION,
        tenant_id=_application_audit_tenant_id(current_user, application),
        resource_id=application.id,
        resource_name=application.tenant_name,
        remark=_application_audit_remark(application),
    )
    return _application_dto_list(session, [application], include_user_email=False)[0]


@router.delete("/invitation/{application_id}", response_model=TenantApplicationDTO)
async def cancel_tenant_invitation(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    application_id: int,
):
    _require_current_tenant_admin(current_user)
    application = session.get(TenantApplicationModel, application_id)
    if (
        not application
        or application.application_type != TENANT_APPLICATION_TYPE_INVITE
        or int(application.tenant_id or 0) != int(current_tenant.id)
    ):
        raise HTTPException(status_code=404, detail="Tenant invitation not found")
    try:
        application = cancel_tenant_application(
            session,
            application_id=application_id,
            reviewer_user_id=int(current_user.id),
            review_comment="cancelled by tenant admin",
            allowed_types={TENANT_APPLICATION_TYPE_INVITE},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE_STATUS,
        detail="取消工作空间邀请",
        module=OperationModules.TENANT_APPLICATION,
        tenant_id=int(current_tenant.id),
        resource_id=application.id,
        resource_name=application.tenant_name,
        remark=_application_audit_remark(application),
    )
    return _application_dto_list(session, [application])[0]


@router.post("/domain", response_model=TenantDomainDTO)
async def bind_tenant_domain(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    creator: TenantDomainCreator,
):
    _require_current_tenant_admin(current_user)
    try:
        row = create_tenant_domain(
            session,
            tenant_id=int(current_tenant.id),
            domain=creator.domain,
            requested_by_user_id=int(current_user.id),
            auto_join_role=creator.auto_join_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.CREATE,
        detail="提交工作空间邮箱域绑定",
        module=OperationModules.TENANT,
        tenant_id=int(current_tenant.id),
        resource_id=row.id,
        resource_name=row.domain,
        remark=f"status={row.status}; auto_join_role={row.auto_join_role}",
    )
    return _domain_dto(row)


@router.get("/domain/list", response_model=list[TenantDomainDTO])
async def tenant_domain_list(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
):
    _require_current_tenant_admin(current_user)
    return [_domain_dto(row) for row in list_tenant_domains(session, tenant_id=int(current_tenant.id))]


@router.get("/domain/admin/list", response_model=list[TenantDomainDTO])
async def admin_tenant_domain_list(
    session: SessionDep,
    current_user: CurrentUser,
    tenant_id: int | None = None,
):
    _require_platform_admin(current_user)
    return [_domain_dto(row) for row in list_tenant_domains(session, tenant_id=tenant_id)]


@router.post("/domain/{domain_id}/review", response_model=TenantDomainDTO)
async def review_domain_binding(
    session: SessionDep,
    current_user: CurrentUser,
    domain_id: int,
    dto: TenantDomainReview,
):
    _require_platform_admin(current_user)
    try:
        row = review_tenant_domain(
            session,
            domain_id=domain_id,
            status=dto.status,
            reviewed_by_user_id=int(current_user.id),
            auto_join_role=dto.auto_join_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE_STATUS,
        detail="审核工作空间邮箱域绑定",
        module=OperationModules.TENANT,
        tenant_id=int(row.tenant_id),
        resource_id=row.id,
        resource_name=row.domain,
        remark=f"status={row.status}; auto_join_role={row.auto_join_role}",
    )
    return _domain_dto(row)


@router.get("/security", response_model=TenantSecurityPolicyDTO)
async def tenant_security_policy(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
):
    _require_current_tenant_admin(current_user)
    return _security_policy_dto(
        get_tenant_security_policy(session, tenant_id=int(current_tenant.id)),
        int(current_tenant.id),
    )


@router.put("/security", response_model=TenantSecurityPolicyDTO)
async def update_tenant_security_policy(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    editor: TenantSecurityPolicyEditor,
):
    _require_current_tenant_admin(current_user)
    try:
        row = upsert_tenant_security_policy(
            session,
            tenant_id=int(current_tenant.id),
            sso_required=editor.sso_required,
            session_timeout_minutes=editor.session_timeout_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE,
        detail="更新工作空间安全策略",
        module=OperationModules.TENANT,
        tenant_id=int(current_tenant.id),
        resource_id=row.id,
        resource_name=current_tenant.name,
        remark=f"sso_required={row.sso_required}; session_timeout_minutes={row.session_timeout_minutes}",
    )
    return _security_policy_dto(row, int(current_tenant.id))


@router.post("/data-request", response_model=TenantDataRequestDTO)
async def submit_tenant_data_request(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    creator: TenantDataRequestCreator,
):
    if creator.request_type in {TENANT_DATA_REQUEST_TYPE_CANCEL, TENANT_DATA_REQUEST_TYPE_DELETE}:
        _require_current_tenant_owner(current_user)
    else:
        _require_current_tenant_admin(current_user)
    try:
        row = create_tenant_data_request(
            session,
            tenant_id=int(current_tenant.id),
            requested_by_user_id=int(current_user.id),
            request_type=creator.request_type,
            reason=creator.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.CREATE,
        detail="提交工作空间数据请求",
        module=OperationModules.TENANT,
        tenant_id=int(current_tenant.id),
        resource_id=row.id,
        resource_name=current_tenant.name,
        remark=f"type={row.request_type}; status={row.status}",
    )
    return _data_request_dto(row)


@router.get("/data-request/list", response_model=list[TenantDataRequestDTO])
async def tenant_data_request_list(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    status: str | None = None,
    tenant_id: int | None = None,
):
    if is_platform_workspace_delegate(current_user):
        scoped_tenant_id = int(current_tenant.id)
        if tenant_id is not None and int(tenant_id) != scoped_tenant_id:
            raise HTTPException(status_code=403, detail="Tenant data request access denied")
    elif is_platform_admin(current_user):
        scoped_tenant_id = tenant_id
    else:
        _require_current_tenant_admin(current_user)
        scoped_tenant_id = int(current_tenant.id)
        if tenant_id is not None and int(tenant_id) != scoped_tenant_id:
            raise HTTPException(status_code=403, detail="Tenant data request access denied")
    return [
        _data_request_dto(row)
        for row in list_tenant_data_requests(session, tenant_id=scoped_tenant_id, status=status)
    ]


@router.post("/data-request/{request_id}/review", response_model=TenantDataRequestDTO)
async def review_data_request(
    session: SessionDep,
    current_user: CurrentUser,
    request_id: int,
    dto: TenantDataRequestReview,
):
    _require_platform_admin(current_user)
    try:
        row = review_tenant_data_request(
            session,
            request_id=request_id,
            reviewer_user_id=int(current_user.id),
            approved=dto.approved,
            review_comment=dto.review_comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE_STATUS,
        detail="审核工作空间数据请求",
        module=OperationModules.TENANT,
        tenant_id=int(row.tenant_id),
        resource_id=row.id,
        resource_name=str(row.tenant_id),
        remark=f"type={row.request_type}; status={row.status}",
    )
    return _data_request_dto(row)


@router.post("/data-request/{request_id}/complete", response_model=TenantDataRequestDTO)
async def complete_data_request(
    session: SessionDep,
    current_user: CurrentUser,
    request_id: int,
    dto: TenantDataRequestComplete,
):
    _require_platform_admin(current_user)
    try:
        row = complete_tenant_data_request(
            session,
            request_id=request_id,
            completed_by_user_id=int(current_user.id),
            complete_comment=dto.complete_comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE_STATUS,
        detail="完成工作空间数据请求",
        module=OperationModules.TENANT,
        tenant_id=int(row.tenant_id),
        resource_id=row.id,
        resource_name=str(row.tenant_id),
        remark=f"type={row.request_type}; status={row.status}",
    )
    return _data_request_dto(row)


@router.post("/{tenant_id}/leave", response_model=list[TenantDTO])
async def leave_joined_tenant(
    session: SessionDep,
    current_user: CurrentUser,
    tenant_id: int,
):
    if is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="SaaS administrator cannot leave tenant from this endpoint")
    tenant = session.get(TenantModel, int(tenant_id))
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant does not exist")
    try:
        leave_tenant(session, int(current_user.id), tenant_id=int(tenant_id))
        _remove_tenant_project_permissions(
            session,
            tenant_id=int(tenant_id),
            user_id=int(current_user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.DELETE,
        detail="退出工作空间",
        module=OperationModules.TENANT,
        tenant_id=int(tenant_id),
        resource_id=current_user.id,
        resource_name=_audit_user_name(current_user),
        remark=f"tenant_id={tenant.id}; user_id={current_user.id}",
    )
    rows = list_user_tenant_memberships(session, int(current_user.id))
    return _tenant_dto_list(session, [(tenant, membership.role, membership.create_time) for tenant, membership in rows])


async def _update_tenant_datasource_binding(
    session: SessionDep,
    current_user: CurrentUser,
    tenant_id: int,
    editor: TenantDatasourceBindingEditor,
) -> TenantDTO:
    _require_platform_admin(current_user)
    tenant = session.get(TenantModel, int(tenant_id))
    if tenant is None or int(getattr(tenant, "status", 1)) < 0:
        raise HTTPException(status_code=404, detail="Tenant does not exist")
    bind_tenant_to_datasource(session, current_user, int(tenant_id), editor.datasource_id)
    tenant = session.get(TenantModel, int(tenant_id))
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE,
        detail="更新工作空间绑定数据源",
        module=OperationModules.TENANT,
        tenant_id=int(tenant_id),
        resource_id=tenant_id,
        resource_name=tenant.name if tenant else str(tenant_id),
        remark=f"datasource_id={editor.datasource_id or 'none'}",
    )
    return _tenant_admin_dto(session, tenant)


@router.put("/{tenant_id}/datasource-binding", response_model=TenantDTO, include_in_schema=False)
async def update_tenant_datasource_binding(
    session: SessionDep,
    current_user: CurrentUser,
    tenant_id: int,
    editor: TenantDatasourceBindingEditor,
):
    return await _update_tenant_datasource_binding(session, current_user, tenant_id, editor)


@router.put("/{tenant_id}/project-binding", response_model=TenantDTO, include_in_schema=False)
async def update_tenant_legacy_project_binding(
    session: SessionDep,
    current_user: CurrentUser,
    tenant_id: int,
    editor: TenantDatasourceBindingEditor,
):
    return await _update_tenant_datasource_binding(session, current_user, tenant_id, editor)


@router.post("", response_model=TenantDTO)
async def add_tenant(session: SessionDep, current_user: CurrentUser, creator: TenantCreator):
    _require_platform_admin(current_user)
    try:
        owner_user = _resolve_owner_user(session, creator)
        tenant = create_tenant(
            session,
            name=creator.name,
            plan=creator.plan,
            subscription_status=creator.subscription_status,
            billing_mode=creator.billing_mode,
            trial_end_time=creator.trial_end_time,
            current_period_end_time=creator.current_period_end_time,
            contract_no=creator.contract_no,
            billing_contact=creator.billing_contact,
            billing_email=creator.billing_email,
            subscription_note=creator.subscription_note,
        )
        if owner_user:
            assign_user_to_tenant(
                session,
                int(owner_user.id),
                tenant_id=int(tenant.id),
                role=TENANT_ROLE_OWNER,
                is_primary=True,
            )
        if creator.datasource_id:
            bind_tenant_to_datasource(session, current_user, int(tenant.id), creator.datasource_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    tenant = session.get(TenantModel, int(tenant.id))
    owner = None
    if owner_user:
        owner = {
            "owner_user_id": int(owner_user.id),
            "owner_account": owner_user.account,
            "owner_name": owner_user.name,
            "owner_email": owner_user.email,
        }
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.CREATE,
        detail="创建工作空间",
        module=OperationModules.TENANT,
        tenant_id=int(tenant.id),
        resource_id=tenant.id,
        resource_name=tenant.name,
        remark=f"tenant_id={tenant.id}; plan={tenant.plan}",
    )
    datasource = _tenant_bound_datasource_map(session, [int(tenant.id)]).get(int(tenant.id))
    return _tenant_dto(tenant, owner=owner, datasource=datasource)


@router.put("/{tenant_id}", response_model=TenantDTO)
async def edit_tenant(session: SessionDep, current_user: CurrentUser, tenant_id: int, editor: TenantEditor):
    _require_platform_admin(current_user)
    editor_fields = _model_fields_set(editor)
    try:
        tenant = update_tenant(
            session,
            tenant_id=tenant_id,
            name=editor.name,
            plan=editor.plan,
            subscription_status=editor.subscription_status,
            billing_mode=editor.billing_mode,
            trial_end_time=editor.trial_end_time,
            current_period_end_time=editor.current_period_end_time,
            contract_no=editor.contract_no,
            billing_contact=editor.billing_contact,
            billing_email=editor.billing_email,
            subscription_note=editor.subscription_note,
        )
        if "datasource_id" in editor_fields:
            bind_tenant_to_datasource(session, current_user, int(tenant.id), editor.datasource_id)
            tenant = session.get(TenantModel, int(tenant.id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE,
        detail="更新工作空间",
        module=OperationModules.TENANT,
        tenant_id=int(tenant.id),
        resource_id=tenant.id,
        resource_name=tenant.name,
        remark=(
            f"tenant_id={tenant.id}; plan={tenant.plan}; "
            f"datasource_id={editor.datasource_id if 'datasource_id' in editor_fields else 'unchanged'}"
        ),
    )
    return _tenant_admin_dto(session, tenant)


@router.patch("/{tenant_id}/status", response_model=TenantDTO)
async def update_tenant_status(session: SessionDep, current_user: CurrentUser, tenant_id: int, dto: TenantStatus):
    _require_platform_admin(current_user)
    try:
        tenant = set_tenant_status(session, tenant_id=tenant_id, status=dto.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE_STATUS,
        detail="更新工作空间状态",
        module=OperationModules.TENANT,
        tenant_id=int(tenant.id),
        resource_id=tenant.id,
        resource_name=tenant.name,
        remark=f"tenant_id={tenant.id}; status={tenant.status}",
    )
    return _tenant_dto(tenant)


@router.delete("/{tenant_id}", response_model=TenantDTO)
async def remove_tenant(session: SessionDep, current_user: CurrentUser, tenant_id: int):
    _require_platform_admin(current_user)
    try:
        tenant = delete_tenant(session, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.DELETE,
        detail="删除工作空间",
        module=OperationModules.TENANT,
        tenant_id=int(tenant.id),
        resource_id=tenant.id,
        resource_name=tenant.name,
        remark=f"tenant_id={tenant.id}; soft_deleted=true",
    )
    return _tenant_dto(tenant)
