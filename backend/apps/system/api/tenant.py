from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import inspect
from sqlmodel import delete as sqlmodel_delete, select

from apps.datasource.models.datasource import CoreDatasource, CoreDatasourceUser
from apps.system.crud.tenant import (
    DEFAULT_TENANT_ID,
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
    leave_tenant,
    list_tenant_data_requests,
    list_tenants,
    list_tenant_applications,
    list_tenant_domains,
    list_user_tenant_memberships,
    normalize_application_role,
    normalize_tenant_role,
    reject_tenant_application,
    review_tenant_data_request,
    review_tenant_domain,
    search_active_tenants,
    set_tenant_status,
    transfer_tenant_owner,
    update_tenant,
    upsert_tenant_security_policy,
    get_tenant_security_policy,
    user_belongs_to_tenant,
)
from apps.system.crud.tenant_usage import list_tenant_usage_daily
from apps.system.crud.user import (
    SYSTEM_ROLE_VIEWER,
    check_email_format,
    is_high_privilege_user,
    is_super_admin,
)
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
    TenantDataRequestComplete,
    TenantDataRequestCreator,
    TenantDataRequestDTO,
    TenantDataRequestReview,
    TenantDomainCreator,
    TenantDomainDTO,
    TenantDomainReview,
    TenantInvitationCreator,
    TenantCreator,
    TenantDTO,
    TenantEditor,
    TenantOwnerTransfer,
    TenantSecurityPolicyDTO,
    TenantSecurityPolicyEditor,
    TenantSearchDTO,
    TenantStatus,
)
from apps.system.schemas.tenant_usage_schema import TenantUsageDailyDTO
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


def _audit_tenant_id(current_user: CurrentUser, tenant_id: int | None = None) -> int:
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
        f"tenant_code={application.tenant_code}",
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
    if not is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="Only system admin can manage tenants")


def _require_current_tenant_admin(current_user: CurrentUser) -> None:
    tenant_role = normalize_tenant_role(getattr(current_user, "tenant_role", None))
    if not is_super_admin(current_user) and tenant_role not in TENANT_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Only tenant admin can manage tenant members")


def _require_current_tenant_owner(current_user: CurrentUser) -> None:
    tenant_role = normalize_tenant_role(getattr(current_user, "tenant_role", None))
    if not is_super_admin(current_user) and tenant_role != TENANT_ROLE_OWNER:
        raise HTTPException(status_code=403, detail="Only tenant owner can perform this operation")


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


def _tenant_dto(tenant: TenantModel, *, role: str = TENANT_ROLE_OWNER, owner: dict | None = None) -> TenantDTO:
    owner = owner or {}
    return TenantDTO(
        id=int(tenant.id),
        code=tenant.code,
        name=tenant.name,
        role=role,
        plan=tenant.plan,
        status=int(tenant.status),
        subscription_status=getattr(tenant, "subscription_status", None) or "active",
        billing_mode=getattr(tenant, "billing_mode", None) or "manual",
        trial_end_time=getattr(tenant, "trial_end_time", None),
        current_period_end_time=getattr(tenant, "current_period_end_time", None),
        contract_no=getattr(tenant, "contract_no", None),
        billing_contact=getattr(tenant, "billing_contact", None),
        billing_email=getattr(tenant, "billing_email", None),
        subscription_note=getattr(tenant, "subscription_note", None),
        create_time=int(tenant.create_time or 0),
        update_time=int(tenant.update_time or 0),
        owner_user_id=owner.get("owner_user_id"),
        owner_account=owner.get("owner_account"),
        owner_name=owner.get("owner_name"),
        owner_email=owner.get("owner_email"),
    )


def _tenant_dto_list(session: SessionDep, rows: list[tuple[TenantModel, str]]) -> list[TenantDTO]:
    owner_map = _tenant_owner_map(session, [int(tenant.id) for tenant, _role in rows])
    return [
        _tenant_dto(tenant, role=role, owner=owner_map.get(int(tenant.id)))
        for tenant, role in rows
    ]


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
) -> TenantApplicationDTO:
    applicant = applicant or {}
    inviter = inviter or {}
    return TenantApplicationDTO(
        id=int(application.id),
        application_type=getattr(application, "application_type", None) or TENANT_APPLICATION_TYPE_CREATE,
        applicant_user_id=int(application.applicant_user_id),
        applicant_account=applicant.get("account"),
        applicant_name=applicant.get("name"),
        applicant_email=applicant.get("email"),
        invited_by_user_id=application.invited_by_user_id,
        inviter_account=inviter.get("account"),
        inviter_name=inviter.get("name"),
        inviter_email=inviter.get("email"),
        tenant_id=application.tenant_id,
        tenant_code=application.tenant_code,
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


def _application_dto_list(session: SessionDep, applications) -> list[TenantApplicationDTO]:
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
    return [
        _application_dto(
            application,
            applicant=user_map.get(int(application.applicant_user_id)),
            inviter=user_map.get(int(application.invited_by_user_id)) if application.invited_by_user_id else None,
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
            ip_whitelist=None,
            sso_required=False,
            session_timeout_minutes=None,
        )
    return TenantSecurityPolicyDTO(
        id=int(row.id),
        tenant_id=int(row.tenant_id),
        ip_whitelist=row.ip_whitelist,
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


def _resolve_owner_user(session: SessionDep, creator: TenantCreator) -> UserModel | None:
    if creator.owner_user_id:
        user = session.get(UserModel, int(creator.owner_user_id))
        if not user:
            raise ValueError("Tenant owner user does not exist")
        if is_high_privilege_user(user):
            raise ValueError("Platform administrator cannot be tenant owner")
        return user

    owner_account = (creator.owner_account or "").strip()
    if not owner_account:
        return None

    existing = session.exec(select(UserModel).where(UserModel.account == owner_account)).first()
    if existing:
        if is_high_privilege_user(existing):
            raise ValueError("Platform administrator cannot be tenant owner")
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
    return user


@router.get("/current", response_model=TenantDTO)
async def current_tenant(current_tenant: CurrentTenant):
    return TenantDTO(
        id=current_tenant.id,
        code=current_tenant.code,
        name=current_tenant.name,
        role=current_tenant.role,
    )


@router.get("/list", response_model=list[TenantDTO])
async def tenant_list(session: SessionDep, current_user: CurrentUser):
    if is_super_admin(current_user):
        tenants = list_tenants(session)
        return _tenant_dto_list(session, [(tenant, TENANT_ROLE_OWNER) for tenant in tenants])
    rows = list_user_tenant_memberships(session, int(current_user.id))
    return _tenant_dto_list(session, [(tenant, membership.role) for tenant, membership in rows])


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
            code=tenant.code,
            name=tenant.name,
            plan=tenant.plan,
            status=int(tenant.status),
            subscription_status=getattr(tenant, "subscription_status", None) or "active",
            already_joined=user_belongs_to_tenant(session, int(current_user.id), int(tenant.id)),
        )
        for tenant in tenants
    ]


@router.get("/admin/list", response_model=list[TenantDTO])
async def admin_tenant_list(session: SessionDep, current_user: CurrentUser):
    _require_platform_admin(current_user)
    tenants = list_tenants(session, include_disabled=True)
    return _tenant_dto_list(session, [(tenant, TENANT_ROLE_OWNER) for tenant in tenants])


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
    if is_super_admin(current_user):
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
            tenant_code=creator.tenant_code,
            tenant_name=creator.tenant_name,
            plan=creator.plan,
            requested_role=normalize_application_role(creator.requested_role, creator.application_type),
            reason=creator.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    detail = "提交企业创建申请" if application.application_type == TENANT_APPLICATION_TYPE_CREATE else "提交加入企业申请"
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
    detail = "取消企业创建申请" if application.application_type == TENANT_APPLICATION_TYPE_CREATE else "取消加入企业申请"
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
        detail="审核企业创建申请通过" if dto.approved else "审核企业创建申请拒绝",
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
    return _application_dto_list(session, applications)


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
        detail="审核加入企业申请通过" if dto.approved else "审核加入企业申请拒绝",
        module=OperationModules.TENANT_APPLICATION,
        tenant_id=int(current_tenant.id),
        resource_id=application.id,
        resource_name=application.tenant_name,
        remark=_application_audit_remark(application),
    )
    return _application_dto_list(session, [application])[0]


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
        raise HTTPException(status_code=400, detail="Platform administrator cannot be invited to tenant")
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
        detail="邀请企业成员",
        module=OperationModules.TENANT_APPLICATION,
        tenant_id=int(current_tenant.id),
        resource_id=invitation.id,
        resource_name=invitation.tenant_name,
        remark=_application_audit_remark(invitation),
    )
    return _application_dto_list(session, [invitation])[0]


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
                    message="Platform administrator cannot be invited to tenant",
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
        detail="批量邀请企业成员",
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
    return _application_dto_list(session, applications)


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
        raise HTTPException(status_code=400, detail="Platform administrator cannot be tenant owner")
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
        detail="转移企业所有者",
        module=OperationModules.TENANT,
        tenant_id=int(current_tenant.id),
        resource_id=target_user.id,
        resource_name=target_user.name,
        remark=f"tenant_code={current_tenant.code}; target_user_id={target_user.id}",
    )
    tenant = session.get(TenantModel, int(current_tenant.id))
    return _tenant_dto(tenant, owner={
        "owner_user_id": int(target_user.id),
        "owner_account": target_user.account,
        "owner_name": target_user.name,
        "owner_email": target_user.email,
    })


@router.post("/{tenant_id}/leave", response_model=list[TenantDTO])
async def leave_joined_tenant(
    session: SessionDep,
    current_user: CurrentUser,
    tenant_id: int,
):
    if is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="Platform administrator cannot leave tenant from this endpoint")
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
        detail="退出企业",
        module=OperationModules.TENANT,
        tenant_id=int(tenant_id),
        resource_id=current_user.id,
        resource_name=_audit_user_name(current_user),
        remark=f"tenant_code={tenant.code}; user_id={current_user.id}",
    )
    rows = list_user_tenant_memberships(session, int(current_user.id))
    return _tenant_dto_list(session, [(tenant, membership.role) for tenant, membership in rows])


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
        detail="接受企业邀请" if dto.approved else "拒绝企业邀请",
        module=OperationModules.TENANT_APPLICATION,
        tenant_id=_application_audit_tenant_id(current_user, application),
        resource_id=application.id,
        resource_name=application.tenant_name,
        remark=_application_audit_remark(application),
    )
    return _application_dto_list(session, [application])[0]


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
        detail="取消企业邀请",
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
        detail="提交企业邮箱域绑定",
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
        detail="审核企业邮箱域绑定",
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
            ip_whitelist=editor.ip_whitelist,
            sso_required=editor.sso_required,
            session_timeout_minutes=editor.session_timeout_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE,
        detail="更新企业安全策略",
        module=OperationModules.TENANT,
        tenant_id=int(current_tenant.id),
        resource_id=row.id,
        resource_name=current_tenant.name,
        remark=f"sso_required={row.sso_required}; has_ip_whitelist={bool(row.ip_whitelist)}",
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
        detail="提交企业数据请求",
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
    if is_super_admin(current_user):
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
        detail="审核企业数据请求",
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
        detail="完成企业数据请求",
        module=OperationModules.TENANT,
        tenant_id=int(row.tenant_id),
        resource_id=row.id,
        resource_name=str(row.tenant_id),
        remark=f"type={row.request_type}; status={row.status}",
    )
    return _data_request_dto(row)


@router.post("", response_model=TenantDTO)
async def add_tenant(session: SessionDep, current_user: CurrentUser, creator: TenantCreator):
    _require_platform_admin(current_user)
    try:
        owner_user = _resolve_owner_user(session, creator)
        tenant = create_tenant(
            session,
            code=creator.code,
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        detail="创建企业",
        module=OperationModules.TENANT,
        tenant_id=int(tenant.id),
        resource_id=tenant.id,
        resource_name=tenant.name,
        remark=f"tenant_code={tenant.code}; plan={tenant.plan}",
    )
    return _tenant_dto(tenant, owner=owner)


@router.put("/{tenant_id}", response_model=TenantDTO)
async def edit_tenant(session: SessionDep, current_user: CurrentUser, tenant_id: int, editor: TenantEditor):
    _require_platform_admin(current_user)
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_tenant_audit(
        session,
        current_user,
        operation_type=OperationType.UPDATE,
        detail="更新企业",
        module=OperationModules.TENANT,
        tenant_id=int(tenant.id),
        resource_id=tenant.id,
        resource_name=tenant.name,
        remark=f"tenant_code={tenant.code}; plan={tenant.plan}",
    )
    return _tenant_dto(tenant)


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
        detail="更新企业状态",
        module=OperationModules.TENANT,
        tenant_id=int(tenant.id),
        resource_id=tenant.id,
        resource_name=tenant.name,
        remark=f"tenant_code={tenant.code}; status={tenant.status}",
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
        detail="删除企业",
        module=OperationModules.TENANT,
        tenant_id=int(tenant.id),
        resource_id=tenant.id,
        resource_name=tenant.name,
        remark=f"tenant_code={tenant.code}; soft_deleted=true",
    )
    return _tenant_dto(tenant)
