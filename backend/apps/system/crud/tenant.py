from pydantic import BaseModel
from sqlmodel import Session, select

from apps.system.models.tenant import TenantApplicationModel, TenantModel, TenantUserModel
from common.utils.time import get_timestamp

DEFAULT_TENANT_ID = 1
DEFAULT_TENANT_CODE = "default"
DEFAULT_TENANT_NAME = "默认租户"
TENANT_ROLE_OWNER = "owner"
TENANT_ROLE_ADMIN = "admin"
TENANT_ROLE_MEMBER = "member"
TENANT_ADMIN_ROLES = {TENANT_ROLE_OWNER, TENANT_ROLE_ADMIN}
SYSTEM_ROLE_SYSTEM_ADMIN = "system_admin"
TENANT_APPLICATION_STATUS_PENDING = "pending"
TENANT_APPLICATION_STATUS_APPROVED = "approved"
TENANT_APPLICATION_STATUS_REJECTED = "rejected"
TENANT_APPLICATION_STATUS_CANCELLED = "cancelled"
TENANT_APPLICATION_STATUSES = {
    TENANT_APPLICATION_STATUS_PENDING,
    TENANT_APPLICATION_STATUS_APPROVED,
    TENANT_APPLICATION_STATUS_REJECTED,
    TENANT_APPLICATION_STATUS_CANCELLED,
}
TENANT_APPLICATION_TYPE_CREATE = "create"
TENANT_APPLICATION_TYPE_JOIN = "join"
TENANT_APPLICATION_TYPE_INVITE = "invite"
TENANT_APPLICATION_TYPES = {
    TENANT_APPLICATION_TYPE_CREATE,
    TENANT_APPLICATION_TYPE_JOIN,
    TENANT_APPLICATION_TYPE_INVITE,
}
TENANT_CREATE_APPLICATION_ROLES = {TENANT_ROLE_OWNER, TENANT_ROLE_ADMIN}
TENANT_MEMBERSHIP_APPLICATION_ROLES = {TENANT_ROLE_ADMIN, TENANT_ROLE_MEMBER}


class TenantContext(BaseModel):
    id: int
    code: str
    name: str
    role: str = TENANT_ROLE_MEMBER


def normalize_tenant_role(role: str | None) -> str:
    value = (role or "").strip().lower()
    if value in {TENANT_ROLE_OWNER, TENANT_ROLE_ADMIN, TENANT_ROLE_MEMBER}:
        return value
    return TENANT_ROLE_MEMBER


def normalize_application_type(application_type: str | None) -> str:
    normalized = (application_type or "").strip().lower()
    return normalized if normalized in TENANT_APPLICATION_TYPES else TENANT_APPLICATION_TYPE_CREATE


def normalize_application_role(role: str | None, application_type: str | None = None) -> str:
    normalized = normalize_tenant_role(role)
    normalized_type = normalize_application_type(application_type)
    if normalized_type == TENANT_APPLICATION_TYPE_CREATE:
        return normalized if normalized in TENANT_CREATE_APPLICATION_ROLES else TENANT_ROLE_OWNER
    return normalized if normalized in TENANT_MEMBERSHIP_APPLICATION_ROLES else TENANT_ROLE_MEMBER


def normalize_application_status(status: str | None) -> str:
    normalized = (status or "").strip().lower()
    return normalized if normalized in TENANT_APPLICATION_STATUSES else TENANT_APPLICATION_STATUS_PENDING


def _user_is_system_admin(user) -> bool:
    return (getattr(user, "system_role", "") or "").strip().lower() == SYSTEM_ROLE_SYSTEM_ADMIN


def ensure_default_tenant(session: Session) -> TenantModel:
    tenant = session.exec(select(TenantModel).where(TenantModel.code == DEFAULT_TENANT_CODE)).first()
    if tenant:
        return tenant

    tenant = TenantModel(
        id=DEFAULT_TENANT_ID,
        code=DEFAULT_TENANT_CODE,
        name=DEFAULT_TENANT_NAME,
        status=1,
        plan="default",
    )
    session.add(tenant)
    session.flush()
    return tenant


def create_tenant(session: Session, *, code: str, name: str, plan: str = "default") -> TenantModel:
    normalized_code = code.strip().lower()
    if not normalized_code:
        raise ValueError("Tenant code is required")
    existing = session.exec(select(TenantModel).where(TenantModel.code == normalized_code)).first()
    if existing:
        raise ValueError("Tenant code already exists")
    tenant = TenantModel(code=normalized_code, name=name.strip(), plan=plan.strip() or "default", status=1)
    session.add(tenant)
    session.flush()
    return tenant


def tenant_code_exists(session: Session, code: str) -> bool:
    normalized_code = code.strip().lower()
    if not normalized_code:
        return False
    return session.exec(select(TenantModel.id).where(TenantModel.code == normalized_code)).first() is not None


def list_tenants(session: Session, *, include_disabled: bool = False) -> list[TenantModel]:
    statement = select(TenantModel).order_by(TenantModel.name, TenantModel.code)
    if not include_disabled:
        statement = statement.where(TenantModel.status == 1)
    return list(session.exec(statement).all())


def get_active_tenant(session: Session, tenant_id: int | None = None, code: str | None = None) -> TenantModel | None:
    if tenant_id:
        tenant = session.get(TenantModel, int(tenant_id))
        return tenant if tenant and int(tenant.status) == 1 else None
    normalized_code = (code or "").strip().lower()
    if not normalized_code:
        return None
    return session.exec(
        select(TenantModel).where(
            TenantModel.code == normalized_code,
            TenantModel.status == 1,
        )
    ).first()


def search_active_tenants(session: Session, *, keyword: str, limit: int = 20) -> list[TenantModel]:
    normalized = (keyword or "").strip().lower()
    if not normalized:
        return []
    filters = [TenantModel.code == normalized]
    if normalized.isdigit():
        filters.append(TenantModel.id == int(normalized))
    statement = (
        select(TenantModel)
        .where(TenantModel.status == 1)
        .order_by(TenantModel.name, TenantModel.code)
        .limit(limit)
    )
    if len(filters) == 1:
        statement = statement.where(filters[0])
    else:
        statement = statement.where(filters[0] | filters[1])
    return list(session.exec(statement).all())


def update_tenant(session: Session, *, tenant_id: int, name: str, plan: str = "default") -> TenantModel:
    tenant = session.get(TenantModel, tenant_id)
    if not tenant:
        raise ValueError("Tenant does not exist")
    tenant.name = name.strip()
    tenant.plan = plan.strip() or "default"
    tenant.update_time = get_timestamp()
    session.add(tenant)
    session.flush()
    return tenant


def set_tenant_status(session: Session, *, tenant_id: int, status: int) -> TenantModel:
    if status not in {0, 1}:
        raise ValueError("Tenant status must be 0 or 1")
    tenant = session.get(TenantModel, tenant_id)
    if not tenant:
        raise ValueError("Tenant does not exist")
    if int(tenant.id) == DEFAULT_TENANT_ID and status == 0:
        raise ValueError("Default tenant cannot be disabled")
    tenant.status = status
    tenant.update_time = get_timestamp()
    session.add(tenant)
    session.flush()
    return tenant


def create_tenant_application(
    session: Session,
    *,
    applicant_user_id: int,
    application_type: str = TENANT_APPLICATION_TYPE_CREATE,
    tenant_id: int | None = None,
    tenant_code: str | None = None,
    tenant_name: str | None = None,
    plan: str = "default",
    requested_role: str = TENANT_ROLE_OWNER,
    reason: str | None = None,
) -> TenantApplicationModel:
    normalized_type = normalize_application_type(application_type)
    if normalized_type == TENANT_APPLICATION_TYPE_INVITE:
        raise ValueError("Tenant invitation must be created with invitation API")

    if normalized_type == TENANT_APPLICATION_TYPE_CREATE:
        normalized_code = (tenant_code or "").strip().lower()
        normalized_name = (tenant_name or "").strip()
        if not normalized_code:
            raise ValueError("Tenant code is required")
        if not normalized_name:
            raise ValueError("Tenant name is required")
        if tenant_code_exists(session, normalized_code):
            raise ValueError("Tenant code already exists")
        existing_pending = session.exec(
            select(TenantApplicationModel.id).where(
                TenantApplicationModel.application_type == TENANT_APPLICATION_TYPE_CREATE,
                TenantApplicationModel.tenant_code == normalized_code,
                TenantApplicationModel.status == TENANT_APPLICATION_STATUS_PENDING,
            )
        ).first()
        if existing_pending:
            raise ValueError("Tenant application for this code is already pending")
        target_tenant_id = None
        target_code = normalized_code
        target_name = normalized_name
        target_plan = plan.strip() or "default"
    else:
        tenant = get_active_tenant(session, tenant_id=tenant_id, code=tenant_code)
        if not tenant:
            raise ValueError("Tenant does not exist or is disabled")
        if user_belongs_to_tenant(session, int(applicant_user_id), int(tenant.id)):
            raise ValueError("User already belongs to tenant")
        existing_pending = session.exec(
            select(TenantApplicationModel.id).where(
                TenantApplicationModel.application_type == TENANT_APPLICATION_TYPE_JOIN,
                TenantApplicationModel.applicant_user_id == int(applicant_user_id),
                TenantApplicationModel.tenant_id == int(tenant.id),
                TenantApplicationModel.status == TENANT_APPLICATION_STATUS_PENDING,
            )
        ).first()
        if existing_pending:
            raise ValueError("Tenant join application is already pending")
        target_tenant_id = int(tenant.id)
        target_code = tenant.code
        target_name = tenant.name
        target_plan = tenant.plan

    application = TenantApplicationModel(
        application_type=normalized_type,
        applicant_user_id=applicant_user_id,
        tenant_id=target_tenant_id,
        tenant_code=target_code,
        tenant_name=target_name,
        plan=target_plan,
        requested_role=normalize_application_role(requested_role, normalized_type),
        reason=(reason or "").strip() or None,
        status=TENANT_APPLICATION_STATUS_PENDING,
    )
    session.add(application)
    session.flush()
    return application


def create_tenant_invitation(
    session: Session,
    *,
    tenant_id: int,
    invitee_user_id: int,
    invited_by_user_id: int,
    requested_role: str = TENANT_ROLE_MEMBER,
    reason: str | None = None,
) -> TenantApplicationModel:
    tenant = get_active_tenant(session, tenant_id=tenant_id)
    if not tenant:
        raise ValueError("Tenant does not exist or is disabled")
    if user_belongs_to_tenant(session, int(invitee_user_id), int(tenant.id)):
        raise ValueError("User already belongs to tenant")
    existing_pending = session.exec(
        select(TenantApplicationModel.id).where(
            TenantApplicationModel.application_type == TENANT_APPLICATION_TYPE_INVITE,
            TenantApplicationModel.applicant_user_id == int(invitee_user_id),
            TenantApplicationModel.tenant_id == int(tenant.id),
            TenantApplicationModel.status == TENANT_APPLICATION_STATUS_PENDING,
        )
    ).first()
    if existing_pending:
        raise ValueError("Tenant invitation is already pending")

    invitation = TenantApplicationModel(
        application_type=TENANT_APPLICATION_TYPE_INVITE,
        applicant_user_id=int(invitee_user_id),
        invited_by_user_id=int(invited_by_user_id),
        tenant_id=int(tenant.id),
        tenant_code=tenant.code,
        tenant_name=tenant.name,
        plan=tenant.plan,
        requested_role=normalize_application_role(requested_role, TENANT_APPLICATION_TYPE_INVITE),
        reason=(reason or "").strip() or None,
        status=TENANT_APPLICATION_STATUS_PENDING,
    )
    session.add(invitation)
    session.flush()
    return invitation


def list_tenant_applications(
    session: Session,
    *,
    applicant_user_id: int | None = None,
    invited_by_user_id: int | None = None,
    tenant_id: int | None = None,
    application_type: str | None = None,
    status: str | None = None,
) -> list[TenantApplicationModel]:
    statement = select(TenantApplicationModel).order_by(TenantApplicationModel.create_time.desc())
    if applicant_user_id is not None:
        statement = statement.where(TenantApplicationModel.applicant_user_id == int(applicant_user_id))
    if invited_by_user_id is not None:
        statement = statement.where(TenantApplicationModel.invited_by_user_id == int(invited_by_user_id))
    if tenant_id is not None:
        statement = statement.where(TenantApplicationModel.tenant_id == int(tenant_id))
    if application_type:
        statement = statement.where(TenantApplicationModel.application_type == normalize_application_type(application_type))
    if status:
        statement = statement.where(TenantApplicationModel.status == normalize_application_status(status))
    return list(session.exec(statement).all())


def approve_tenant_application(
    session: Session,
    *,
    application_id: int,
    reviewer_user_id: int,
    review_comment: str | None = None,
    allowed_types: set[str] | None = None,
) -> tuple[TenantApplicationModel, TenantModel]:
    application = session.get(TenantApplicationModel, application_id)
    if not application:
        raise ValueError("Tenant application does not exist")
    if application.status != TENANT_APPLICATION_STATUS_PENDING:
        raise ValueError("Tenant application has already been reviewed")
    application_type = normalize_application_type(getattr(application, "application_type", None))
    allowed_normalized = {normalize_application_type(item) for item in allowed_types} if allowed_types else None
    if allowed_normalized and application_type not in allowed_normalized:
        raise ValueError("Tenant application type cannot be reviewed from this endpoint")

    if application_type == TENANT_APPLICATION_TYPE_CREATE:
        if tenant_code_exists(session, application.tenant_code):
            raise ValueError("Tenant code already exists")
        tenant = create_tenant(
            session,
            code=application.tenant_code,
            name=application.tenant_name,
            plan=application.plan,
        )
        assign_user_to_tenant(
            session,
            int(application.applicant_user_id),
            tenant_id=int(tenant.id),
            role=normalize_application_role(application.requested_role, application_type),
            is_primary=True,
        )
        application.tenant_id = int(tenant.id)
    else:
        tenant = get_active_tenant(session, tenant_id=application.tenant_id)
        if not tenant:
            raise ValueError("Tenant does not exist or is disabled")
        if user_belongs_to_tenant(session, int(application.applicant_user_id), int(tenant.id)):
            raise ValueError("User already belongs to tenant")
        assign_user_to_tenant(
            session,
            int(application.applicant_user_id),
            tenant_id=int(tenant.id),
            role=normalize_application_role(application.requested_role, application_type),
            is_primary=False,
        )
    now = get_timestamp()
    application.status = TENANT_APPLICATION_STATUS_APPROVED
    application.reviewer_user_id = int(reviewer_user_id)
    application.review_comment = (review_comment or "").strip() or None
    application.review_time = now
    application.update_time = now
    session.add(application)
    session.flush()
    return application, tenant


def reject_tenant_application(
    session: Session,
    *,
    application_id: int,
    reviewer_user_id: int,
    review_comment: str | None = None,
    allowed_types: set[str] | None = None,
) -> TenantApplicationModel:
    application = session.get(TenantApplicationModel, application_id)
    if not application:
        raise ValueError("Tenant application does not exist")
    if application.status != TENANT_APPLICATION_STATUS_PENDING:
        raise ValueError("Tenant application has already been reviewed")
    application_type = normalize_application_type(getattr(application, "application_type", None))
    allowed_normalized = {normalize_application_type(item) for item in allowed_types} if allowed_types else None
    if allowed_normalized and application_type not in allowed_normalized:
        raise ValueError("Tenant application type cannot be reviewed from this endpoint")
    now = get_timestamp()
    application.status = TENANT_APPLICATION_STATUS_REJECTED
    application.reviewer_user_id = int(reviewer_user_id)
    application.review_comment = (review_comment or "").strip() or None
    application.review_time = now
    application.update_time = now
    session.add(application)
    session.flush()
    return application


def cancel_tenant_application(
    session: Session,
    *,
    application_id: int,
    reviewer_user_id: int,
    review_comment: str | None = None,
    allowed_types: set[str] | None = None,
) -> TenantApplicationModel:
    application = session.get(TenantApplicationModel, application_id)
    if not application:
        raise ValueError("Tenant application does not exist")
    if application.status != TENANT_APPLICATION_STATUS_PENDING:
        raise ValueError("Tenant application has already been reviewed")
    application_type = normalize_application_type(getattr(application, "application_type", None))
    allowed_normalized = {normalize_application_type(item) for item in allowed_types} if allowed_types else None
    if allowed_normalized and application_type not in allowed_normalized:
        raise ValueError("Tenant application type cannot be cancelled from this endpoint")
    now = get_timestamp()
    application.status = TENANT_APPLICATION_STATUS_CANCELLED
    application.reviewer_user_id = int(reviewer_user_id)
    application.review_comment = (review_comment or "").strip() or None
    application.review_time = now
    application.update_time = now
    session.add(application)
    session.flush()
    return application


def list_user_tenant_memberships(session: Session, user_id: int) -> list[tuple[TenantModel, TenantUserModel]]:
    statement = (
        select(TenantModel, TenantUserModel)
        .join(TenantUserModel, TenantUserModel.tenant_id == TenantModel.id)
        .where(
            TenantUserModel.user_id == user_id,
            TenantUserModel.status == 1,
            TenantModel.status == 1,
        )
        .order_by(TenantUserModel.is_primary.desc(), TenantModel.name)
    )
    return list(session.exec(statement).all())


def user_belongs_to_tenant(session: Session, user_id: int, tenant_id: int | None) -> bool:
    if not tenant_id:
        return False
    return session.exec(
        select(TenantUserModel.id).where(
            TenantUserModel.user_id == user_id,
            TenantUserModel.tenant_id == tenant_id,
            TenantUserModel.status == 1,
        )
    ).first() is not None


def get_tenant_membership(session: Session, user_id: int, *, tenant_id: int) -> TenantUserModel | None:
    return session.exec(
        select(TenantUserModel).where(
            TenantUserModel.user_id == int(user_id),
            TenantUserModel.tenant_id == int(tenant_id),
            TenantUserModel.status == 1,
        )
    ).first()


def count_active_tenant_owners(session: Session, *, tenant_id: int) -> int:
    owners = session.exec(
        select(TenantUserModel.id).where(
            TenantUserModel.tenant_id == int(tenant_id),
            TenantUserModel.role == TENANT_ROLE_OWNER,
            TenantUserModel.status == 1,
        )
    ).all()
    return len(owners)


def remove_user_from_tenant(session: Session, user_id: int, *, tenant_id: int) -> TenantUserModel:
    membership = get_tenant_membership(session, user_id, tenant_id=tenant_id)
    if not membership:
        raise ValueError("User does not belong to tenant")
    if normalize_tenant_role(membership.role) == TENANT_ROLE_OWNER:
        raise ValueError("Tenant owner cannot be removed from tenant")
    membership.status = 0
    membership.is_primary = False
    session.add(membership)
    session.flush()
    return membership


def leave_tenant(session: Session, user_id: int, *, tenant_id: int) -> TenantUserModel:
    if int(tenant_id) == DEFAULT_TENANT_ID:
        raise ValueError("Default tenant cannot be left")
    membership = get_tenant_membership(session, user_id, tenant_id=tenant_id)
    if not membership:
        raise ValueError("User does not belong to tenant")
    if normalize_tenant_role(membership.role) == TENANT_ROLE_OWNER and count_active_tenant_owners(
        session,
        tenant_id=tenant_id,
    ) <= 1:
        raise ValueError("Transfer tenant ownership before leaving")
    membership.status = 0
    membership.is_primary = False
    session.add(membership)
    session.flush()
    return membership


def transfer_tenant_owner(session: Session, *, tenant_id: int, target_user_id: int) -> TenantUserModel:
    target_membership = get_tenant_membership(session, target_user_id, tenant_id=tenant_id)
    if not target_membership:
        raise ValueError("Target user does not belong to tenant")
    if normalize_tenant_role(target_membership.role) == TENANT_ROLE_OWNER:
        raise ValueError("Target user is already tenant owner")

    active_memberships = session.exec(
        select(TenantUserModel).where(
            TenantUserModel.tenant_id == int(tenant_id),
            TenantUserModel.status == 1,
        )
    ).all()
    for membership in active_memberships:
        if int(membership.user_id) == int(target_user_id):
            membership.role = TENANT_ROLE_OWNER
            membership.is_primary = True
        elif normalize_tenant_role(membership.role) == TENANT_ROLE_OWNER:
            membership.role = TENANT_ROLE_ADMIN
        session.add(membership)
    session.flush()
    return target_membership


def assign_user_to_tenant(
    session: Session,
    user_id: int,
    *,
    tenant_id: int | None = None,
    role: str = TENANT_ROLE_MEMBER,
    is_primary: bool = False,
) -> TenantUserModel:
    tenant = session.get(TenantModel, tenant_id) if tenant_id else ensure_default_tenant(session)
    if not tenant:
        raise ValueError("Tenant does not exist")

    membership = session.exec(
        select(TenantUserModel).where(
            TenantUserModel.tenant_id == tenant.id,
            TenantUserModel.user_id == user_id,
        )
    ).first()
    if membership:
        membership.role = normalize_tenant_role(role or membership.role)
        membership.status = 1
        membership.is_primary = bool(is_primary or membership.is_primary)
    else:
        membership = TenantUserModel(
            tenant_id=tenant.id,
            user_id=user_id,
            role=normalize_tenant_role(role),
            is_primary=is_primary,
            status=1,
        )
    session.add(membership)
    session.flush()
    return membership


def ensure_user_default_membership(session: Session, user) -> TenantContext:
    role = TENANT_ROLE_OWNER if _user_is_system_admin(user) else TENANT_ROLE_MEMBER
    membership = assign_user_to_tenant(
        session,
        int(user.id),
        tenant_id=DEFAULT_TENANT_ID,
        role=role,
        is_primary=True,
    )
    tenant = session.get(TenantModel, membership.tenant_id) or ensure_default_tenant(session)
    return TenantContext(id=int(tenant.id), code=tenant.code, name=tenant.name, role=membership.role)


def resolve_current_tenant(
    session: Session,
    user,
    *,
    requested_tenant_id: int | None = None,
) -> TenantContext:
    if not user or not getattr(user, "id", None):
        raise PermissionError("Authenticated user is required to resolve tenant")

    ensure_default_tenant(session)
    if requested_tenant_id:
        tenant = session.get(TenantModel, requested_tenant_id)
        if not tenant or tenant.status != 1:
            raise PermissionError("Tenant is disabled or does not exist")
        if _user_is_system_admin(user) or user_belongs_to_tenant(session, int(user.id), requested_tenant_id):
            membership = session.exec(
                select(TenantUserModel).where(
                    TenantUserModel.tenant_id == requested_tenant_id,
                    TenantUserModel.user_id == int(user.id),
                    TenantUserModel.status == 1,
                )
            ).first()
            return TenantContext(
                id=int(tenant.id),
                code=tenant.code,
                name=tenant.name,
                role=normalize_tenant_role(membership.role if membership else TENANT_ROLE_OWNER),
            )
        raise PermissionError("User does not belong to tenant")

    memberships = list_user_tenant_memberships(session, int(user.id))
    if not memberships:
        return ensure_user_default_membership(session, user)

    tenant, membership = memberships[0]
    return TenantContext(
        id=int(tenant.id),
        code=tenant.code,
        name=tenant.name,
        role=normalize_tenant_role(membership.role),
    )


def attach_tenant_context(user, tenant: TenantContext):
    user_copy = user.model_copy(deep=True) if hasattr(user, "model_copy") else user
    user_copy.tenant_id = tenant.id
    user_copy.tenant_code = tenant.code
    user_copy.tenant_name = tenant.name
    user_copy.tenant_role = tenant.role
    return user_copy
