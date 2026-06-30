import json

from pydantic import BaseModel
from sqlalchemy import column as sa_column, func, inspect, or_, table as sa_table
from sqlmodel import Session, select

from apps.system.models.tenant import (
    TenantApplicationModel,
    TenantDataRequestModel,
    TenantDomainModel,
    TenantModel,
    TenantSecurityPolicyModel,
    TenantUserModel,
    generate_tenant_public_id,
)
from common.utils.time import get_timestamp

DEFAULT_TENANT_ID = 1
DEFAULT_TENANT_NAME = "默认租户"
SAMPLE_TENANT_NAME = "示例工作空间"
TENANT_ROLE_OWNER = "owner"
TENANT_ROLE_ADMIN = "admin"
TENANT_ROLE_MEMBER = "member"
TENANT_ADMIN_ROLES = {TENANT_ROLE_OWNER, TENANT_ROLE_ADMIN}
SYSTEM_ROLE_SYSTEM_ADMIN = "system_admin"
SYSTEM_ROLE_COLLAB_ADMIN = "collab_admin"
TENANT_SUBSCRIPTION_TRIALING = "trialing"
TENANT_SUBSCRIPTION_ACTIVE = "active"
TENANT_SUBSCRIPTION_PAST_DUE = "past_due"
TENANT_SUBSCRIPTION_SUSPENDED = "suspended"
TENANT_SUBSCRIPTION_CANCELLED = "cancelled"
TENANT_SUBSCRIPTION_STATUSES = {
    TENANT_SUBSCRIPTION_TRIALING,
    TENANT_SUBSCRIPTION_ACTIVE,
    TENANT_SUBSCRIPTION_PAST_DUE,
    TENANT_SUBSCRIPTION_SUSPENDED,
    TENANT_SUBSCRIPTION_CANCELLED,
}
TENANT_SUBSCRIPTION_BLOCKING_STATUSES = {
    TENANT_SUBSCRIPTION_SUSPENDED,
    TENANT_SUBSCRIPTION_CANCELLED,
}
BILLING_MODE_MANUAL = "manual"
BILLING_MODE_CONTRACT = "contract"
BILLING_MODE_OFFLINE = "offline"
BILLING_MODES = {BILLING_MODE_MANUAL, BILLING_MODE_CONTRACT, BILLING_MODE_OFFLINE}
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
TENANT_MEMBERSHIP_APPLICATION_ROLES = {TENANT_ROLE_ADMIN, TENANT_ROLE_MEMBER}
TENANT_DOMAIN_STATUS_PENDING = "pending"
TENANT_DOMAIN_STATUS_VERIFIED = "verified"
TENANT_DOMAIN_STATUS_DISABLED = "disabled"
TENANT_DOMAIN_STATUSES = {TENANT_DOMAIN_STATUS_PENDING, TENANT_DOMAIN_STATUS_VERIFIED, TENANT_DOMAIN_STATUS_DISABLED}
TENANT_DATA_REQUEST_TYPE_EXPORT = "export"
TENANT_DATA_REQUEST_TYPE_DELETE = "delete"
TENANT_DATA_REQUEST_TYPE_CANCEL = "cancel"
TENANT_DATA_REQUEST_TYPES = {
    TENANT_DATA_REQUEST_TYPE_EXPORT,
    TENANT_DATA_REQUEST_TYPE_DELETE,
    TENANT_DATA_REQUEST_TYPE_CANCEL,
}
TENANT_DATA_REQUEST_STATUS_PENDING = "pending"
TENANT_DATA_REQUEST_STATUS_APPROVED = "approved"
TENANT_DATA_REQUEST_STATUS_REJECTED = "rejected"
TENANT_DATA_REQUEST_STATUS_COMPLETED = "completed"
TENANT_DATA_REQUEST_STATUSES = {
    TENANT_DATA_REQUEST_STATUS_PENDING,
    TENANT_DATA_REQUEST_STATUS_APPROVED,
    TENANT_DATA_REQUEST_STATUS_REJECTED,
    TENANT_DATA_REQUEST_STATUS_COMPLETED,
}
TENANT_STATUS_DELETED = -1


class TenantContext(BaseModel):
    id: int
    public_id: str | None = None
    name: str
    role: str = TENANT_ROLE_MEMBER


def normalize_tenant_role(role: str | None) -> str:
    """
    是什么：normalize_tenant_role 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化系统管理相关数据，生成后续流程可使用的结构。
    """
    value = (role or "").strip().lower()
    if value in {TENANT_ROLE_OWNER, TENANT_ROLE_ADMIN, TENANT_ROLE_MEMBER}:
        return value
    return TENANT_ROLE_MEMBER


def normalize_application_type(application_type: str | None) -> str:
    """
    是什么：normalize_application_type 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化系统管理相关数据，生成后续流程可使用的结构。
    """
    normalized = (application_type or "").strip().lower()
    return normalized if normalized in TENANT_APPLICATION_TYPES else TENANT_APPLICATION_TYPE_CREATE


def normalize_application_role(role: str | None, application_type: str | None = None) -> str:
    """
    是什么：normalize_application_role 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化系统管理相关数据，生成后续流程可使用的结构。
    """
    normalized = normalize_tenant_role(role)
    normalized_type = normalize_application_type(application_type)
    if normalized_type == TENANT_APPLICATION_TYPE_CREATE:
        return TENANT_ROLE_OWNER
    return normalized if normalized in TENANT_MEMBERSHIP_APPLICATION_ROLES else TENANT_ROLE_MEMBER


def normalize_application_status(status: str | None) -> str:
    """
    是什么：normalize_application_status 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化系统管理相关数据，生成后续流程可使用的结构。
    """
    normalized = (status or "").strip().lower()
    return normalized if normalized in TENANT_APPLICATION_STATUSES else TENANT_APPLICATION_STATUS_PENDING


def normalize_domain_status(status: str | None) -> str:
    """
    是什么：normalize_domain_status 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化系统管理相关数据，生成后续流程可使用的结构。
    """
    normalized = (status or "").strip().lower()
    return normalized if normalized in TENANT_DOMAIN_STATUSES else TENANT_DOMAIN_STATUS_PENDING


def normalize_domain(domain: str | None) -> str:
    """
    是什么：normalize_domain 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化系统管理相关数据，生成后续流程可使用的结构。
    """
    normalized = (domain or "").strip().lower().lstrip("@")
    if not normalized or "." not in normalized or any(part == "" for part in normalized.split(".")):
        raise ValueError("Tenant domain is invalid")
    return normalized


def normalize_data_request_type(request_type: str | None) -> str:
    """
    是什么：normalize_data_request_type 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化系统管理相关数据，生成后续流程可使用的结构。
    """
    normalized = (request_type or "").strip().lower()
    if normalized not in TENANT_DATA_REQUEST_TYPES:
        raise ValueError("Tenant data request type is invalid")
    return normalized


def normalize_subscription_status(status: str | None) -> str:
    """
    是什么：normalize_subscription_status 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化系统管理相关数据，生成后续流程可使用的结构。
    """
    normalized = (status or "").strip().lower()
    return normalized if normalized in TENANT_SUBSCRIPTION_STATUSES else TENANT_SUBSCRIPTION_ACTIVE


def normalize_billing_mode(mode: str | None) -> str:
    """
    是什么：normalize_billing_mode 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化系统管理相关数据，生成后续流程可使用的结构。
    """
    normalized = (mode or "").strip().lower()
    return normalized if normalized in BILLING_MODES else BILLING_MODE_MANUAL


def subscription_blocks_high_cost_features(status: str | None) -> bool:
    """
    是什么：subscription_blocks_high_cost_features 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 subscription_blocks_high_cost_features 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return normalize_subscription_status(status) in TENANT_SUBSCRIPTION_BLOCKING_STATUSES


def _user_is_system_admin(user) -> bool:
    """
    是什么：_user_is_system_admin 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _user_is_system_admin 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return (getattr(user, "system_role", "") or "").strip().lower() == SYSTEM_ROLE_SYSTEM_ADMIN


def _user_is_platform_admin(user) -> bool:
    """
    是什么：_user_is_platform_admin 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _user_is_platform_admin 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return (getattr(user, "system_role", "") or "").strip().lower() in {
        SYSTEM_ROLE_SYSTEM_ADMIN,
        SYSTEM_ROLE_COLLAB_ADMIN,
    }


def ensure_default_tenant(session: Session) -> TenantModel:
    """
    是什么：ensure_default_tenant 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    tenant = session.get(TenantModel, DEFAULT_TENANT_ID)
    if tenant:
        ensure_tenant_public_id(session, tenant)
        return tenant

    tenant = TenantModel(
        id=DEFAULT_TENANT_ID,
        public_id=generate_unique_tenant_public_id(session),
        name=DEFAULT_TENANT_NAME,
        status=1,
        plan="default",
    )
    session.add(tenant)
    session.flush()
    return tenant


def sample_workspace_role_for_user(user) -> str:
    """
    是什么：sample_workspace_role_for_user 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 sample_workspace_role_for_user 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    system_role = (getattr(user, "system_role", "") or "").strip().lower()
    if system_role == SYSTEM_ROLE_SYSTEM_ADMIN:
        return TENANT_ROLE_OWNER
    if system_role == SYSTEM_ROLE_COLLAB_ADMIN:
        return TENANT_ROLE_ADMIN
    return TENANT_ROLE_MEMBER


def _ensure_sample_workspace_state(session: Session) -> tuple[TenantModel, bool]:
    """
    是什么：_ensure_sample_workspace_state 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    tenant = session.exec(select(TenantModel).where(TenantModel.name == SAMPLE_TENANT_NAME)).first()
    changed = False
    if tenant is None:
        tenant = TenantModel(
            public_id=generate_unique_tenant_public_id(session),
            name=SAMPLE_TENANT_NAME,
            status=1,
            plan="default",
            subscription_status=TENANT_SUBSCRIPTION_ACTIVE,
            billing_mode=BILLING_MODE_MANUAL,
        )
        session.add(tenant)
        session.flush()
        return tenant, True

    if not getattr(tenant, "public_id", None):
        tenant.public_id = generate_unique_tenant_public_id(session)
        changed = True
    if tenant.name != SAMPLE_TENANT_NAME:
        tenant.name = SAMPLE_TENANT_NAME
        changed = True
    if int(tenant.status or 0) != 1:
        tenant.status = 1
        changed = True
    if (tenant.plan or "").strip() != "default":
        tenant.plan = "default"
        changed = True
    if normalize_subscription_status(getattr(tenant, "subscription_status", None)) != TENANT_SUBSCRIPTION_ACTIVE:
        tenant.subscription_status = TENANT_SUBSCRIPTION_ACTIVE
        changed = True
    if normalize_billing_mode(getattr(tenant, "billing_mode", None)) != BILLING_MODE_MANUAL:
        tenant.billing_mode = BILLING_MODE_MANUAL
        changed = True
    if changed:
        tenant.update_time = get_timestamp()
        session.add(tenant)
        session.flush()
    return tenant, changed


def ensure_sample_workspace(session: Session) -> TenantModel:
    """
    是什么：ensure_sample_workspace 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    tenant, _changed = _ensure_sample_workspace_state(session)
    return tenant


def _user_has_active_primary_tenant(session: Session, user_id: int) -> bool:
    """
    是什么：_user_has_active_primary_tenant 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _user_has_active_primary_tenant 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return session.exec(
        select(TenantUserModel.id).where(
            TenantUserModel.user_id == int(user_id),
            TenantUserModel.status == 1,
            TenantUserModel.is_primary == True,  # noqa: E712
        )
    ).first() is not None


def ensure_user_sample_workspace_membership(session: Session, user) -> TenantUserModel | None:
    """
    是什么：ensure_user_sample_workspace_membership 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    user_id = getattr(user, "id", None)
    if not user_id:
        return None
    tenant, tenant_changed = _ensure_sample_workspace_state(session)
    role = sample_workspace_role_for_user(user)
    should_be_primary = not _user_has_active_primary_tenant(session, int(user_id))
    membership = session.exec(
        select(TenantUserModel).where(
            TenantUserModel.tenant_id == int(tenant.id),
            TenantUserModel.user_id == int(user_id),
        )
    ).first()
    changed = tenant_changed
    if membership is None:
        membership = TenantUserModel(
            tenant_id=int(tenant.id),
            user_id=int(user_id),
            role=role,
            is_primary=should_be_primary,
            status=1,
        )
        changed = True
    else:
        if normalize_tenant_role(membership.role) != role:
            membership.role = role
            changed = True
        if int(membership.status or 0) != 1:
            membership.status = 1
            changed = True
        if should_be_primary and not bool(membership.is_primary):
            membership.is_primary = True
            changed = True
    if not changed:
        return None
    session.add(membership)
    session.flush()
    return membership


def _clean_optional_text(value: str | None) -> str | None:
    """
    是什么：_clean_optional_text 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：删除或清理系统管理相关数据、缓存或临时状态。
    """
    return (value or "").strip() or None


def _email_domain(email: str | None) -> str | None:
    """
    是什么：_email_domain 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _email_domain 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    value = (email or "").strip().lower()
    if "@" not in value:
        return None
    return value.rsplit("@", 1)[1] or None


def _table_exists(session: Session, table_name: str) -> bool:
    """
    是什么：_table_exists 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _table_exists 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    try:
        return inspect(session.connection()).has_table(table_name)
    except Exception:
        return False


def generate_unique_tenant_public_id(session: Session) -> str:
    """
    是什么：generate_unique_tenant_public_id 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：基于输入上下文生成系统管理相关结果，并保存或返回给调用方。
    """
    for _attempt in range(20):
        public_id = generate_tenant_public_id()
        exists = session.exec(select(TenantModel.id).where(TenantModel.public_id == public_id)).first()
        if not exists:
            return public_id
    raise RuntimeError("Unable to generate a unique tenant public id")


def ensure_tenant_public_id(session: Session, tenant: TenantModel | None) -> TenantModel | None:
    """
    是什么：ensure_tenant_public_id 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    if tenant is None or getattr(tenant, "public_id", None):
        return tenant
    tenant.public_id = generate_unique_tenant_public_id(session)
    session.add(tenant)
    session.flush()
    return tenant


def create_tenant(
    session: Session,
    *,
    name: str,
    plan: str = "default",
    subscription_status: str = TENANT_SUBSCRIPTION_ACTIVE,
    billing_mode: str = BILLING_MODE_MANUAL,
    trial_end_time: int | None = None,
    current_period_end_time: int | None = None,
    contract_no: str | None = None,
    billing_contact: str | None = None,
    billing_email: str | None = None,
    subscription_note: str | None = None,
) -> TenantModel:
    """
    是什么：create_tenant 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装系统管理相关对象和数据，并返回或写入对应状态。
    """
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Tenant name is required")
    tenant = TenantModel(
        public_id=generate_unique_tenant_public_id(session),
        name=normalized_name,
        plan=plan.strip() or "default",
        status=1,
        subscription_status=normalize_subscription_status(subscription_status),
        billing_mode=normalize_billing_mode(billing_mode),
        trial_end_time=trial_end_time,
        current_period_end_time=current_period_end_time,
        contract_no=_clean_optional_text(contract_no),
        billing_contact=_clean_optional_text(billing_contact),
        billing_email=_clean_optional_text(billing_email),
        subscription_note=_clean_optional_text(subscription_note),
    )
    session.add(tenant)
    session.flush()
    return tenant


def tenant_name_exists(session: Session, name: str) -> bool:
    """
    是什么：tenant_name_exists 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 tenant_name_exists 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    normalized_name = name.strip()
    if not normalized_name:
        return False
    return session.exec(select(TenantModel.id).where(TenantModel.name == normalized_name)).first() is not None


def create_tenant_domain(
    session: Session,
    *,
    tenant_id: int,
    domain: str,
    requested_by_user_id: int | None = None,
    auto_join_role: str = TENANT_ROLE_MEMBER,
) -> TenantDomainModel:
    """
    是什么：create_tenant_domain 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装系统管理相关对象和数据，并返回或写入对应状态。
    """
    tenant = session.get(TenantModel, int(tenant_id))
    if not tenant:
        raise ValueError("Tenant does not exist")
    normalized_domain = normalize_domain(domain)
    existing = session.exec(select(TenantDomainModel).where(TenantDomainModel.domain == normalized_domain)).first()
    if existing:
        if int(existing.tenant_id) != int(tenant_id):
            raise ValueError("Tenant domain is already bound to another tenant")
        existing.auto_join_role = normalize_application_role(auto_join_role, TENANT_APPLICATION_TYPE_JOIN)
        existing.status = TENANT_DOMAIN_STATUS_PENDING if existing.status == TENANT_DOMAIN_STATUS_DISABLED else existing.status
        existing.update_time = get_timestamp()
        session.add(existing)
        session.flush()
        return existing
    row = TenantDomainModel(
        tenant_id=int(tenant_id),
        domain=normalized_domain,
        auto_join_role=normalize_application_role(auto_join_role, TENANT_APPLICATION_TYPE_JOIN),
        status=TENANT_DOMAIN_STATUS_PENDING,
        requested_by_user_id=requested_by_user_id,
    )
    session.add(row)
    session.flush()
    return row


def list_tenant_domains(session: Session, *, tenant_id: int | None = None, include_disabled: bool = True) -> list[TenantDomainModel]:
    """
    是什么：list_tenant_domains 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    statement = select(TenantDomainModel).order_by(TenantDomainModel.domain)
    if tenant_id is not None:
        statement = statement.where(TenantDomainModel.tenant_id == int(tenant_id))
    if not include_disabled:
        statement = statement.where(TenantDomainModel.status != TENANT_DOMAIN_STATUS_DISABLED)
    return list(session.exec(statement).all())


def review_tenant_domain(
    session: Session,
    *,
    domain_id: int,
    status: str,
    reviewed_by_user_id: int,
    auto_join_role: str = TENANT_ROLE_MEMBER,
) -> TenantDomainModel:
    """
    是什么：review_tenant_domain 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 review_tenant_domain 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    row = session.get(TenantDomainModel, int(domain_id))
    if not row:
        raise ValueError("Tenant domain does not exist")
    normalized_status = normalize_domain_status(status)
    if normalized_status == TENANT_DOMAIN_STATUS_PENDING:
        raise ValueError("Tenant domain review status must be verified or disabled")
    row.status = normalized_status
    row.auto_join_role = normalize_application_role(auto_join_role, TENANT_APPLICATION_TYPE_JOIN)
    row.verified_by_user_id = int(reviewed_by_user_id)
    row.verify_time = get_timestamp()
    row.update_time = row.verify_time
    session.add(row)
    session.flush()
    return row


def auto_assign_tenants_by_email_domain(session: Session, user) -> list[TenantUserModel]:
    """
    是什么：auto_assign_tenants_by_email_domain 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 auto_assign_tenants_by_email_domain 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    email_domain = _email_domain(getattr(user, "email", None))
    user_id = getattr(user, "id", None)
    if not email_domain or not user_id:
        return []
    domain_rows = session.exec(
        select(TenantDomainModel).where(
            TenantDomainModel.domain == email_domain,
            TenantDomainModel.status == TENANT_DOMAIN_STATUS_VERIFIED,
        )
    ).all()
    assigned = []
    for row in domain_rows:
        if not user_belongs_to_tenant(session, int(user_id), int(row.tenant_id)):
            assigned.append(
                assign_user_to_tenant(
                    session,
                    int(user_id),
                    tenant_id=int(row.tenant_id),
                    role=normalize_application_role(row.auto_join_role, TENANT_APPLICATION_TYPE_JOIN),
                    is_primary=False,
                )
            )
    return assigned


def list_tenants(session: Session, *, include_disabled: bool = False) -> list[TenantModel]:
    """
    是什么：list_tenants 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    statement = select(TenantModel).order_by(TenantModel.name, TenantModel.id)
    if not include_disabled:
        statement = statement.where(TenantModel.status == 1)
    else:
        statement = statement.where(TenantModel.status != TENANT_STATUS_DELETED)
    return list(session.exec(statement).all())


def get_active_tenant(session: Session, tenant_id: int | None = None) -> TenantModel | None:
    """
    是什么：get_active_tenant 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    if tenant_id:
        tenant = session.get(TenantModel, int(tenant_id))
        ensure_tenant_public_id(session, tenant)
        return tenant if tenant and int(tenant.status) == 1 else None
    return None


def search_active_tenants(session: Session, *, keyword: str, limit: int = 20) -> list[TenantModel]:
    """
    是什么：search_active_tenants 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    normalized = (keyword or "").strip().lower()
    if not normalized:
        return []
    keyword_pattern = f"%{normalized}%"
    filters = [
        func.lower(TenantModel.name).like(keyword_pattern),
        func.lower(TenantModel.public_id).like(keyword_pattern),
    ]
    statement = (
        select(TenantModel)
        .where(TenantModel.status == 1)
        .where(or_(*filters))
        .order_by(TenantModel.name, TenantModel.id)
        .limit(limit)
    )
    return list(session.exec(statement).all())


def update_tenant(
    session: Session,
    *,
    tenant_id: int,
    name: str,
    plan: str = "default",
    subscription_status: str = TENANT_SUBSCRIPTION_ACTIVE,
    billing_mode: str = BILLING_MODE_MANUAL,
    trial_end_time: int | None = None,
    current_period_end_time: int | None = None,
    contract_no: str | None = None,
    billing_contact: str | None = None,
    billing_email: str | None = None,
    subscription_note: str | None = None,
) -> TenantModel:
    """
    是什么：update_tenant 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新系统管理相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    tenant = session.get(TenantModel, tenant_id)
    if not tenant:
        raise ValueError("Tenant does not exist")
    tenant.name = name.strip()
    tenant.plan = plan.strip() or "default"
    tenant.subscription_status = normalize_subscription_status(subscription_status)
    tenant.billing_mode = normalize_billing_mode(billing_mode)
    tenant.trial_end_time = trial_end_time
    tenant.current_period_end_time = current_period_end_time
    tenant.contract_no = _clean_optional_text(contract_no)
    tenant.billing_contact = _clean_optional_text(billing_contact)
    tenant.billing_email = _clean_optional_text(billing_email)
    tenant.subscription_note = _clean_optional_text(subscription_note)
    tenant.update_time = get_timestamp()
    session.add(tenant)
    session.flush()
    return tenant


def set_tenant_status(session: Session, *, tenant_id: int, status: int) -> TenantModel:
    """
    是什么：set_tenant_status 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新系统管理相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    if status not in {0, 1}:
        raise ValueError("Tenant status must be 0 or 1")
    tenant = session.get(TenantModel, tenant_id)
    if not tenant:
        raise ValueError("Tenant does not exist")
    if int(tenant.status) == TENANT_STATUS_DELETED:
        raise ValueError("Deleted tenant cannot be updated")
    if int(tenant.id) == DEFAULT_TENANT_ID and status == 0:
        raise ValueError("Default tenant cannot be disabled")
    tenant.status = status
    tenant.update_time = get_timestamp()
    session.add(tenant)
    session.flush()
    return tenant


def delete_tenant(session: Session, *, tenant_id: int) -> TenantModel:
    """
    是什么：delete_tenant 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：删除或清理系统管理相关数据、缓存或临时状态。
    """
    tenant = session.get(TenantModel, tenant_id)
    if not tenant or int(tenant.status) == TENANT_STATUS_DELETED:
        raise ValueError("Tenant does not exist")
    if int(tenant.id) == DEFAULT_TENANT_ID:
        raise ValueError("Default tenant cannot be deleted")
    if int(tenant.status) != 0:
        raise ValueError("Tenant must be disabled before deletion")
    tenant.status = TENANT_STATUS_DELETED
    tenant.update_time = get_timestamp()
    session.add(tenant)
    session.flush()
    return tenant


def get_tenant_security_policy(session: Session, *, tenant_id: int) -> TenantSecurityPolicyModel | None:
    """
    是什么：get_tenant_security_policy 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    if not _table_exists(session, TenantSecurityPolicyModel.__tablename__):
        return None
    return session.exec(
        select(TenantSecurityPolicyModel).where(TenantSecurityPolicyModel.tenant_id == int(tenant_id))
    ).first()


def upsert_tenant_security_policy(
    session: Session,
    *,
    tenant_id: int,
    sso_required: bool = False,
    session_timeout_minutes: int | None = None,
) -> TenantSecurityPolicyModel:
    """
    是什么：upsert_tenant_security_policy 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 upsert_tenant_security_policy 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    tenant = session.get(TenantModel, int(tenant_id))
    if not tenant:
        raise ValueError("Tenant does not exist")
    if session_timeout_minutes is not None and int(session_timeout_minutes) < 5:
        raise ValueError("Session timeout must be at least 5 minutes")
    now = get_timestamp()
    row = get_tenant_security_policy(session, tenant_id=int(tenant_id))
    if row is None:
        row = TenantSecurityPolicyModel(
            tenant_id=int(tenant_id),
            sso_required=bool(sso_required),
            session_timeout_minutes=session_timeout_minutes,
            create_time=now,
            update_time=now,
        )
    else:
        row.sso_required = bool(sso_required)
        row.session_timeout_minutes = session_timeout_minutes
        row.update_time = now
    session.add(row)
    session.flush()
    return row


def validate_tenant_security_policy(session: Session, *, tenant_id: int, user) -> None:
    """
    是什么：validate_tenant_security_policy 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    policy = get_tenant_security_policy(session, tenant_id=int(tenant_id))
    if not policy:
        return
    if _user_is_system_admin(user):
        return
    if bool(policy.sso_required) and int(getattr(user, "origin", 0) or 0) == 0:
        raise PermissionError("Tenant requires SSO login")


def create_tenant_data_request(
    session: Session,
    *,
    tenant_id: int,
    requested_by_user_id: int,
    request_type: str,
    reason: str | None = None,
) -> TenantDataRequestModel:
    """
    是什么：create_tenant_data_request 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装系统管理相关对象和数据，并返回或写入对应状态。
    """
    tenant = session.get(TenantModel, int(tenant_id))
    if not tenant:
        raise ValueError("Tenant does not exist")
    row = TenantDataRequestModel(
        tenant_id=int(tenant_id),
        request_type=normalize_data_request_type(request_type),
        status=TENANT_DATA_REQUEST_STATUS_PENDING,
        requested_by_user_id=int(requested_by_user_id),
        reason=_clean_optional_text(reason),
    )
    session.add(row)
    session.flush()
    return row


def list_tenant_data_requests(
    session: Session,
    *,
    tenant_id: int | None = None,
    status: str | None = None,
) -> list[TenantDataRequestModel]:
    """
    是什么：list_tenant_data_requests 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    statement = select(TenantDataRequestModel).order_by(TenantDataRequestModel.create_time.desc())
    if tenant_id is not None:
        statement = statement.where(TenantDataRequestModel.tenant_id == int(tenant_id))
    if status:
        statement = statement.where(TenantDataRequestModel.status == status.strip().lower())
    return list(session.exec(statement).all())


def build_tenant_export_manifest(session: Session, *, tenant_id: int) -> dict:
    """
    是什么：build_tenant_export_manifest 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装系统管理相关对象和数据，并返回或写入对应状态。
    """
    inspector = inspect(session.connection())
    tables = []
    for table_name in inspector.get_table_names():
        try:
            columns = {column["name"] for column in inspector.get_columns(table_name)}
        except Exception:
            continue
        if "tenant_id" not in columns:
            continue
        try:
            dynamic_table = sa_table(table_name, sa_column("tenant_id"))
            count_value = session.exec(
                select(func.count()).select_from(dynamic_table).where(dynamic_table.c.tenant_id == int(tenant_id))
            ).one()
        except Exception:
            continue
        tables.append({"table": table_name, "rows": int(count_value or 0)})
    return {
        "tenant_id": int(tenant_id),
        "scope": "tenant_id",
        "tables": sorted(tables, key=lambda item: item["table"]),
        "warning": "This manifest records export scope and row counts; actual file generation is a separate controlled operation.",
    }


def review_tenant_data_request(
    session: Session,
    *,
    request_id: int,
    reviewer_user_id: int,
    approved: bool,
    review_comment: str | None = None,
) -> TenantDataRequestModel:
    """
    是什么：review_tenant_data_request 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 review_tenant_data_request 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    row = session.get(TenantDataRequestModel, int(request_id))
    if not row:
        raise ValueError("Tenant data request does not exist")
    if row.status != TENANT_DATA_REQUEST_STATUS_PENDING:
        raise ValueError("Tenant data request has already been reviewed")
    now = get_timestamp()
    row.status = TENANT_DATA_REQUEST_STATUS_APPROVED if approved else TENANT_DATA_REQUEST_STATUS_REJECTED
    row.reviewer_user_id = int(reviewer_user_id)
    row.review_comment = _clean_optional_text(review_comment)
    row.review_time = now
    row.update_time = now
    if approved and row.request_type == TENANT_DATA_REQUEST_TYPE_EXPORT:
        row.export_manifest = json.dumps(
            build_tenant_export_manifest(session, tenant_id=int(row.tenant_id)),
            ensure_ascii=False,
        )
    session.add(row)
    session.flush()
    return row


def complete_tenant_data_request(
    session: Session,
    *,
    request_id: int,
    completed_by_user_id: int,
    complete_comment: str | None = None,
) -> TenantDataRequestModel:
    """
    是什么：complete_tenant_data_request 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 complete_tenant_data_request 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    row = session.get(TenantDataRequestModel, int(request_id))
    if not row:
        raise ValueError("Tenant data request does not exist")
    if row.status != TENANT_DATA_REQUEST_STATUS_APPROVED:
        raise ValueError("Tenant data request must be approved before completion")
    now = get_timestamp()
    row.status = TENANT_DATA_REQUEST_STATUS_COMPLETED
    row.completed_by_user_id = int(completed_by_user_id)
    note = _clean_optional_text(complete_comment)
    if note:
        row.review_comment = f"{row.review_comment or ''}\ncomplete: {note}".strip()
    row.complete_time = now
    row.update_time = now
    session.add(row)
    session.flush()
    return row


def create_tenant_application(
    session: Session,
    *,
    applicant_user_id: int,
    application_type: str = TENANT_APPLICATION_TYPE_CREATE,
    tenant_id: int | None = None,
    tenant_name: str | None = None,
    plan: str = "default",
    requested_role: str = TENANT_ROLE_OWNER,
    reason: str | None = None,
) -> TenantApplicationModel:
    """
    是什么：create_tenant_application 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装系统管理相关对象和数据，并返回或写入对应状态。
    """
    normalized_type = normalize_application_type(application_type)
    if normalized_type == TENANT_APPLICATION_TYPE_INVITE:
        raise ValueError("Tenant invitation must be created with invitation API")

    if normalized_type == TENANT_APPLICATION_TYPE_CREATE:
        normalized_name = (tenant_name or "").strip()
        if not normalized_name:
            raise ValueError("Tenant name is required")
        if tenant_name_exists(session, normalized_name):
            raise ValueError("Tenant name already exists")
        existing_pending = session.exec(
            select(TenantApplicationModel.id).where(
                TenantApplicationModel.application_type == TENANT_APPLICATION_TYPE_CREATE,
                TenantApplicationModel.tenant_name == normalized_name,
                TenantApplicationModel.status == TENANT_APPLICATION_STATUS_PENDING,
            )
        ).first()
        if existing_pending:
            raise ValueError("Tenant application for this name is already pending")
        target_tenant_id = None
        target_name = normalized_name
        target_plan = plan.strip() or "default"
    else:
        tenant = get_active_tenant(session, tenant_id=tenant_id)
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
        target_name = tenant.name
        target_plan = tenant.plan

    application_role = (
        TENANT_ROLE_MEMBER
        if normalized_type == TENANT_APPLICATION_TYPE_JOIN
        else normalize_application_role(requested_role, normalized_type)
    )

    application = TenantApplicationModel(
        application_type=normalized_type,
        applicant_user_id=applicant_user_id,
        tenant_id=target_tenant_id,
        tenant_name=target_name,
        plan=target_plan,
        requested_role=application_role,
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
    """
    是什么：create_tenant_invitation 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装系统管理相关对象和数据，并返回或写入对应状态。
    """
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
    """
    是什么：list_tenant_applications 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
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
    """
    是什么：approve_tenant_application 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 approve_tenant_application 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
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
        if tenant_name_exists(session, application.tenant_name):
            raise ValueError("Tenant name already exists")
        tenant = create_tenant(
            session,
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
        membership_role = (
            TENANT_ROLE_MEMBER
            if application_type == TENANT_APPLICATION_TYPE_JOIN
            else normalize_application_role(application.requested_role, application_type)
        )
        assign_user_to_tenant(
            session,
            int(application.applicant_user_id),
            tenant_id=int(tenant.id),
            role=membership_role,
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
    """
    是什么：reject_tenant_application 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 reject_tenant_application 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
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
    """
    是什么：cancel_tenant_application 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 cancel_tenant_application 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
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


def list_user_tenant_memberships(
    session: Session,
    user_id: int,
    *,
    include_default: bool = False,
) -> list[tuple[TenantModel, TenantUserModel]]:
    """
    是什么：list_user_tenant_memberships 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
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
    if not include_default:
        statement = statement.where(TenantModel.id != DEFAULT_TENANT_ID)
    return list(session.exec(statement).all())


def user_belongs_to_tenant(session: Session, user_id: int, tenant_id: int | None) -> bool:
    """
    是什么：user_belongs_to_tenant 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 user_belongs_to_tenant 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
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
    """
    是什么：get_tenant_membership 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    return session.exec(
        select(TenantUserModel).where(
            TenantUserModel.user_id == int(user_id),
            TenantUserModel.tenant_id == int(tenant_id),
            TenantUserModel.status == 1,
        )
    ).first()


def count_active_tenant_owners(session: Session, *, tenant_id: int) -> int:
    """
    是什么：count_active_tenant_owners 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 count_active_tenant_owners 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    owners = session.exec(
        select(TenantUserModel.id).where(
            TenantUserModel.tenant_id == int(tenant_id),
            TenantUserModel.role == TENANT_ROLE_OWNER,
            TenantUserModel.status == 1,
        )
    ).all()
    return len(owners)


def remove_user_from_tenant(session: Session, user_id: int, *, tenant_id: int) -> TenantUserModel:
    """
    是什么：remove_user_from_tenant 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：删除或清理系统管理相关数据、缓存或临时状态。
    """
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
    """
    是什么：leave_tenant 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 leave_tenant 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
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
    """
    是什么：transfer_tenant_owner 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 transfer_tenant_owner 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
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
    """
    是什么：assign_user_to_tenant 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 assign_user_to_tenant 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
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
    """
    是什么：ensure_user_default_membership 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    role = TENANT_ROLE_OWNER if _user_is_system_admin(user) else TENANT_ROLE_MEMBER
    membership = assign_user_to_tenant(
        session,
        int(user.id),
        tenant_id=DEFAULT_TENANT_ID,
        role=role,
        is_primary=True,
    )
    tenant = session.get(TenantModel, membership.tenant_id) or ensure_default_tenant(session)
    ensure_tenant_public_id(session, tenant)
    return TenantContext(
        id=int(tenant.id),
        public_id=getattr(tenant, "public_id", None),
        name=tenant.name,
        role=membership.role,
    )


def _tenant_context_from_membership(
    session: Session,
    tenant: TenantModel,
    membership: TenantUserModel,
) -> TenantContext:
    """
    是什么：_tenant_context_from_membership 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _tenant_context_from_membership 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    ensure_tenant_public_id(session, tenant)
    return TenantContext(
        id=int(tenant.id),
        public_id=getattr(tenant, "public_id", None),
        name=tenant.name,
        role=normalize_tenant_role(membership.role),
    )


def _fallback_user_tenant_context(session: Session, user) -> TenantContext | None:
    """
    是什么：_fallback_user_tenant_context 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _fallback_user_tenant_context 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    memberships = list_user_tenant_memberships(session, int(user.id))
    if not memberships:
        return None

    non_sample_memberships = [
        (tenant, membership)
        for tenant, membership in memberships
        if tenant.name != SAMPLE_TENANT_NAME
    ]
    tenant, membership = (non_sample_memberships or memberships)[0]
    return _tenant_context_from_membership(session, tenant, membership)


def resolve_current_tenant(
    session: Session,
    user,
    *,
    requested_tenant_id: int | None = None,
    platform_workspace_delegate: bool = False,
) -> TenantContext | None:
    """
    是什么：resolve_current_tenant 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 resolve_current_tenant 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    if not user or not getattr(user, "id", None):
        raise PermissionError("Authenticated user is required to resolve tenant")

    ensure_default_tenant(session)
    user_is_platform_admin = _user_is_platform_admin(user)
    if requested_tenant_id == DEFAULT_TENANT_ID and not user_is_platform_admin:
        requested_tenant_id = None
    if requested_tenant_id:
        tenant = session.get(TenantModel, requested_tenant_id)
        if not tenant or getattr(tenant, "status", 1) == TENANT_STATUS_DELETED:
            if not user_is_platform_admin:
                fallback = _fallback_user_tenant_context(session, user)
                if fallback is not None:
                    return fallback
            raise PermissionError("Tenant is disabled or does not exist")
        if user_is_platform_admin and platform_workspace_delegate:
            ensure_tenant_public_id(session, tenant)
            return TenantContext(
                id=int(tenant.id),
                public_id=getattr(tenant, "public_id", None),
                name=tenant.name,
                role=TENANT_ROLE_OWNER,
            )
        if not user_is_platform_admin and int(getattr(tenant, "status", 0) or 0) != 1:
            fallback = _fallback_user_tenant_context(session, user)
            if fallback is not None:
                return fallback
            raise PermissionError("Tenant is disabled or does not exist")
        if user_is_platform_admin or user_belongs_to_tenant(session, int(user.id), requested_tenant_id):
            membership = session.exec(
                select(TenantUserModel).where(
                    TenantUserModel.tenant_id == requested_tenant_id,
                    TenantUserModel.user_id == int(user.id),
                    TenantUserModel.status == 1,
                )
            ).first()
            ensure_tenant_public_id(session, tenant)
            return TenantContext(
                id=int(tenant.id),
                public_id=getattr(tenant, "public_id", None),
                name=tenant.name,
                role=normalize_tenant_role(membership.role if membership else TENANT_ROLE_OWNER),
            )
        fallback = _fallback_user_tenant_context(session, user)
        if fallback is not None:
            return fallback
        raise PermissionError("User does not belong to tenant")

    if user_is_platform_admin and not platform_workspace_delegate:
        tenant = ensure_default_tenant(session)
        return TenantContext(
            id=int(tenant.id),
            public_id=getattr(tenant, "public_id", None),
            name=tenant.name,
            role=TENANT_ROLE_OWNER,
        )

    fallback = _fallback_user_tenant_context(session, user)
    if fallback is None:
        if user_is_platform_admin:
            tenant = ensure_default_tenant(session)
            return TenantContext(
                id=int(tenant.id),
                public_id=getattr(tenant, "public_id", None),
                name=tenant.name,
                role=TENANT_ROLE_OWNER,
            )
        return None

    return fallback


def attach_tenant_context(user, tenant: TenantContext | None, *, platform_workspace_delegate: bool = False):
    """
    是什么：attach_tenant_context 是 backend/apps/system/crud/tenant.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 attach_tenant_context 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    user_copy = user.model_copy(deep=True) if hasattr(user, "model_copy") else user
    is_platform_admin = _user_is_platform_admin(user_copy)
    user_copy.global_role = "platform_admin" if is_platform_admin else "normal_user"
    if tenant is None:
        user_copy.tenant_id = None
        user_copy.tenant_public_id = None
        user_copy.tenant_name = None
        user_copy.tenant_role = None
        user_copy.workspace_role = None
        user_copy.has_workspace = False
        user_copy.workspace_status = "platform_admin" if is_platform_admin else "workspace_required"
        return user_copy
    user_copy.tenant_id = tenant.id
    user_copy.tenant_public_id = getattr(tenant, "public_id", None)
    user_copy.tenant_name = tenant.name
    user_copy.tenant_role = tenant.role
    user_copy.workspace_role = tenant.role
    delegated = bool(is_platform_admin and platform_workspace_delegate)
    user_copy.has_workspace = delegated or not is_platform_admin
    user_copy.workspace_status = (
        "platform_workspace_delegate"
        if delegated
        else "platform_admin"
        if is_platform_admin
        else "active"
    )
    return user_copy
