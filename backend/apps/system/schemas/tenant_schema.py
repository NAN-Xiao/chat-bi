from typing import Literal, Optional

from pydantic import BaseModel, Field


class TenantDTO(BaseModel):
    id: int
    code: str
    name: str
    role: str = "member"
    plan: str = "default"
    status: int = 1
    subscription_status: str = "active"
    billing_mode: str = "manual"
    trial_end_time: Optional[int] = None
    current_period_end_time: Optional[int] = None
    contract_no: Optional[str] = None
    billing_contact: Optional[str] = None
    billing_email: Optional[str] = None
    subscription_note: Optional[str] = None
    create_time: int = 0
    update_time: int = 0
    owner_user_id: Optional[int] = None
    owner_account: Optional[str] = None
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None


class TenantSearchDTO(BaseModel):
    id: int
    code: str
    name: str
    plan: str = "default"
    status: int = 1
    subscription_status: str = "active"
    already_joined: bool = False


class TenantCreator(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    plan: str = Field(default="default", max_length=64)
    subscription_status: str = Field(default="active", max_length=32)
    billing_mode: str = Field(default="manual", max_length=32)
    trial_end_time: Optional[int] = None
    current_period_end_time: Optional[int] = None
    contract_no: Optional[str] = Field(default=None, max_length=128)
    billing_contact: Optional[str] = Field(default=None, max_length=128)
    billing_email: Optional[str] = Field(default=None, max_length=128)
    subscription_note: Optional[str] = Field(default=None, max_length=2000)
    owner_user_id: Optional[int] = None
    owner_account: Optional[str] = Field(default=None, max_length=100)
    owner_name: Optional[str] = Field(default=None, max_length=100)
    owner_email: Optional[str] = Field(default=None, max_length=100)


class TenantEditor(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    plan: str = Field(default="default", max_length=64)
    subscription_status: str = Field(default="active", max_length=32)
    billing_mode: str = Field(default="manual", max_length=32)
    trial_end_time: Optional[int] = None
    current_period_end_time: Optional[int] = None
    contract_no: Optional[str] = Field(default=None, max_length=128)
    billing_contact: Optional[str] = Field(default=None, max_length=128)
    billing_email: Optional[str] = Field(default=None, max_length=128)
    subscription_note: Optional[str] = Field(default=None, max_length=2000)


class TenantStatus(BaseModel):
    status: int = Field(ge=0, le=1)


class TenantOwnerTransfer(BaseModel):
    target_user_id: int = Field(gt=0)


class TenantApplicationCreator(BaseModel):
    application_type: Literal["create", "join"] = "create"
    tenant_id: Optional[int] = None
    tenant_code: Optional[str] = Field(default=None, max_length=64)
    tenant_name: Optional[str] = Field(default=None, max_length=255)
    plan: str = Field(default="default", max_length=64)
    requested_role: str = Field(default="owner", max_length=32)
    reason: Optional[str] = Field(default=None, max_length=2000)


class TenantInvitationCreator(BaseModel):
    account: str = Field(min_length=1, max_length=100)
    requested_role: Literal["admin", "member"] = "member"
    reason: Optional[str] = Field(default=None, max_length=2000)


class TenantApplicationReview(BaseModel):
    approved: bool
    review_comment: Optional[str] = Field(default=None, max_length=2000)


class TenantApplicationDTO(BaseModel):
    id: int
    application_type: str = "create"
    applicant_user_id: int
    applicant_account: Optional[str] = None
    applicant_name: Optional[str] = None
    applicant_email: Optional[str] = None
    invited_by_user_id: Optional[int] = None
    inviter_account: Optional[str] = None
    inviter_name: Optional[str] = None
    inviter_email: Optional[str] = None
    tenant_id: Optional[int] = None
    tenant_code: str
    tenant_name: str
    plan: str = "default"
    requested_role: str = "owner"
    reason: Optional[str] = None
    status: str = "pending"
    reviewer_user_id: Optional[int] = None
    review_comment: Optional[str] = None
    create_time: int = 0
    update_time: int = 0
    review_time: Optional[int] = None


class TenantDomainCreator(BaseModel):
    domain: str = Field(min_length=3, max_length=255)
    auto_join_role: Literal["admin", "member"] = "member"


class TenantDomainReview(BaseModel):
    status: Literal["verified", "disabled"]
    auto_join_role: Literal["admin", "member"] = "member"


class TenantDomainDTO(BaseModel):
    id: int
    tenant_id: int
    domain: str
    auto_join_role: str = "member"
    status: str = "pending"
    requested_by_user_id: Optional[int] = None
    verified_by_user_id: Optional[int] = None
    create_time: int = 0
    update_time: int = 0
    verify_time: Optional[int] = None


class TenantSecurityPolicyEditor(BaseModel):
    ip_whitelist: Optional[str] = Field(default=None, max_length=4000)
    sso_required: bool = False
    session_timeout_minutes: Optional[int] = Field(default=None, ge=5, le=10080)


class TenantSecurityPolicyDTO(TenantSecurityPolicyEditor):
    id: Optional[int] = None
    tenant_id: int
    create_time: int = 0
    update_time: int = 0


class TenantDataRequestCreator(BaseModel):
    request_type: Literal["cancel", "export", "delete"]
    reason: Optional[str] = Field(default=None, max_length=2000)


class TenantDataRequestReview(BaseModel):
    approved: bool
    review_comment: Optional[str] = Field(default=None, max_length=2000)


class TenantDataRequestComplete(BaseModel):
    complete_comment: Optional[str] = Field(default=None, max_length=2000)


class TenantDataRequestDTO(BaseModel):
    id: int
    tenant_id: int
    request_type: str
    status: str
    requested_by_user_id: int
    reviewer_user_id: Optional[int] = None
    completed_by_user_id: Optional[int] = None
    reason: Optional[str] = None
    review_comment: Optional[str] = None
    export_manifest: Optional[str] = None
    create_time: int = 0
    update_time: int = 0
    review_time: Optional[int] = None
    complete_time: Optional[int] = None


class TenantBulkInviteCreator(BaseModel):
    accounts: list[str] = Field(min_length=1, max_length=200)
    requested_role: Literal["admin", "member"] = "member"
    reason: Optional[str] = Field(default=None, max_length=2000)


class TenantBulkInviteResult(BaseModel):
    account: str
    status: str
    message: Optional[str] = None
    application_id: Optional[int] = None
