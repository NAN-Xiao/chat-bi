from sqlalchemy import BigInteger, Boolean, Column, Index, String, Text, UniqueConstraint
from sqlmodel import Field

from common.core.models import SnowflakeBase
from common.utils.time import get_timestamp


class TenantModel(SnowflakeBase, table=True):
    __tablename__ = "sys_tenant"
    __table_args__ = (
        UniqueConstraint("code", name="uq_sys_tenant_code"),
        Index("idx_sys_tenant_status", "status"),
        Index("idx_sys_tenant_subscription_status", "subscription_status"),
    )

    code: str = Field(sa_column=Column(String(64), nullable=False))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    status: int = Field(default=1, sa_column=Column(BigInteger(), nullable=False, server_default="1"))
    plan: str = Field(default="default", sa_column=Column(String(64), nullable=False, server_default="default"))
    subscription_status: str = Field(
        default="active",
        sa_column=Column(String(32), nullable=False, server_default="active"),
    )
    billing_mode: str = Field(
        default="manual",
        sa_column=Column(String(32), nullable=False, server_default="manual"),
    )
    trial_end_time: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    current_period_end_time: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    contract_no: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    billing_contact: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    billing_email: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    subscription_note: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)


class TenantUserModel(SnowflakeBase, table=True):
    __tablename__ = "sys_tenant_user"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_sys_tenant_user_tenant_user"),
        Index("idx_sys_tenant_user_tenant_id", "tenant_id"),
        Index("idx_sys_tenant_user_user_id", "user_id"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    user_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    role: str = Field(default="member", sa_column=Column(String(32), nullable=False, server_default="member"))
    member_remark: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    is_primary: bool = Field(default=False, sa_column=Column(Boolean(), nullable=False, server_default="false"))
    status: int = Field(default=1, sa_column=Column(BigInteger(), nullable=False, server_default="1"))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)


class TenantApplicationModel(SnowflakeBase, table=True):
    __tablename__ = "sys_tenant_application"
    __table_args__ = (
        Index("idx_sys_tenant_application_applicant", "applicant_user_id"),
        Index("idx_sys_tenant_application_inviter", "invited_by_user_id"),
        Index("idx_sys_tenant_application_status", "status"),
        Index("idx_sys_tenant_application_tenant_id", "tenant_id"),
        Index("idx_sys_tenant_application_type_status", "application_type", "status"),
        Index("idx_sys_tenant_application_tenant_code", "tenant_code"),
    )

    applicant_user_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    invited_by_user_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    application_type: str = Field(default="create", sa_column=Column(String(32), nullable=False, server_default="create"))
    tenant_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    tenant_code: str = Field(sa_column=Column(String(64), nullable=False))
    tenant_name: str = Field(sa_column=Column(String(255), nullable=False))
    plan: str = Field(default="default", sa_column=Column(String(64), nullable=False, server_default="default"))
    requested_role: str = Field(default="owner", sa_column=Column(String(32), nullable=False, server_default="owner"))
    reason: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    status: str = Field(default="pending", sa_column=Column(String(32), nullable=False, server_default="pending"))
    reviewer_user_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    review_comment: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    review_time: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))


class TenantDomainModel(SnowflakeBase, table=True):
    __tablename__ = "sys_tenant_domain"
    __table_args__ = (
        UniqueConstraint("domain", name="uq_sys_tenant_domain_domain"),
        Index("idx_sys_tenant_domain_tenant_id", "tenant_id"),
        Index("idx_sys_tenant_domain_status", "status"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    domain: str = Field(sa_column=Column(String(255), nullable=False))
    auto_join_role: str = Field(default="member", sa_column=Column(String(32), nullable=False, server_default="member"))
    status: str = Field(default="pending", sa_column=Column(String(32), nullable=False, server_default="pending"))
    requested_by_user_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    verified_by_user_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    verify_time: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))


class TenantSecurityPolicyModel(SnowflakeBase, table=True):
    __tablename__ = "sys_tenant_security_policy"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_sys_tenant_security_policy_tenant_id"),
        Index("idx_sys_tenant_security_policy_tenant_id", "tenant_id"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    sso_required: bool = Field(default=False, sa_column=Column(Boolean(), nullable=False, server_default="false"))
    session_timeout_minutes: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)


class TenantDataRequestModel(SnowflakeBase, table=True):
    __tablename__ = "sys_tenant_data_request"
    __table_args__ = (
        Index("idx_sys_tenant_data_request_tenant_id", "tenant_id"),
        Index("idx_sys_tenant_data_request_status", "status"),
        Index("idx_sys_tenant_data_request_type", "request_type"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    request_type: str = Field(sa_column=Column(String(32), nullable=False))
    status: str = Field(default="pending", sa_column=Column(String(32), nullable=False, server_default="pending"))
    requested_by_user_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    reviewer_user_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    completed_by_user_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    reason: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    review_comment: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    export_manifest: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    review_time: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    complete_time: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
