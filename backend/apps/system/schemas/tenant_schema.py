from typing import Literal, Optional

from pydantic import BaseModel, Field


class TenantDTO(BaseModel):
    id: int
    code: str
    name: str
    role: str = "member"
    plan: str = "default"
    status: int = 1
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
    already_joined: bool = False


class TenantCreator(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    plan: str = Field(default="default", max_length=64)
    owner_user_id: Optional[int] = None
    owner_account: Optional[str] = Field(default=None, max_length=100)
    owner_name: Optional[str] = Field(default=None, max_length=100)
    owner_email: Optional[str] = Field(default=None, max_length=100)


class TenantEditor(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    plan: str = Field(default="default", max_length=64)


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
