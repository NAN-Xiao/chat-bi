"""
脚本说明：这个脚本定义系统管理的输入输出结构，帮接口和业务代码统一数据格式。
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class TenantDTO(BaseModel):
    """
    类说明：TenantDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    id: int
    public_id: str
    name: str
    role: str = "member"
    plan: Optional[str] = None
    status: int = 1
    subscription_status: Optional[str] = None
    billing_mode: Optional[str] = None
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
    bound_datasource_id: Optional[int] = None
    bound_datasource_name: Optional[str] = None
    bound_project_id: Optional[int] = None
    bound_project_name: Optional[str] = None
    admin_count: int = 0
    member_count: int = 0
    join_time: int = 0
    is_system_default: bool = False


class TenantSearchDTO(BaseModel):
    """
    类说明：TenantSearchDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    id: int
    public_id: str
    name: str
    plan: str = "default"
    status: int = 1
    subscription_status: str = "active"
    already_joined: bool = False


class TenantCreator(BaseModel):
    """
    类说明：TenantCreator 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
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
    datasource_id: Optional[int] = None


class TenantEditor(BaseModel):
    """
    类说明：TenantEditor 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
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
    datasource_id: Optional[int] = None


class TenantStatus(BaseModel):
    """
    类说明：TenantStatus 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    status: int = Field(ge=0, le=1)


class TenantDatasourceBindingEditor(BaseModel):
    """
    类说明：TenantDatasourceBindingEditor 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    datasource_id: Optional[int] = None


class TenantOwnerTransfer(BaseModel):
    """
    类说明：TenantOwnerTransfer 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    target_user_id: int = Field(gt=0)
    reason: Optional[str] = Field(default=None, max_length=2000)


class TenantOwnerCandidateDTO(BaseModel):
    """
    类说明：TenantOwnerCandidateDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    user_id: int
    account: str
    name: Optional[str] = None
    email: Optional[str] = None
    tenant_role: Optional[str] = None
    is_workspace_member: bool = False


class TenantApplicationCreator(BaseModel):
    """
    类说明：TenantApplicationCreator 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    model_config = ConfigDict(extra="forbid")

    application_type: Literal["create", "join"] = "create"
    tenant_id: Optional[int] = None
    tenant_name: Optional[str] = Field(default=None, max_length=255)
    plan: str = Field(default="default", max_length=64)
    reason: Optional[str] = Field(default=None, max_length=2000)


class TenantInvitationCreator(BaseModel):
    """
    类说明：TenantInvitationCreator 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    account: str = Field(min_length=1, max_length=100)
    requested_role: Literal["admin", "member"] = "member"
    reason: Optional[str] = Field(default=None, max_length=2000)


class TenantApplicationReview(BaseModel):
    """
    类说明：TenantApplicationReview 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    approved: bool
    review_comment: Optional[str] = Field(default=None, max_length=2000)


class TenantApplicationDTO(BaseModel):
    """
    类说明：TenantApplicationDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
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
    tenant_public_id: Optional[str] = None
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
    """
    类说明：TenantDomainCreator 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    domain: str = Field(min_length=3, max_length=255)
    auto_join_role: Literal["admin", "member"] = "member"


class TenantDomainReview(BaseModel):
    """
    类说明：TenantDomainReview 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    status: Literal["verified", "disabled"]
    auto_join_role: Literal["admin", "member"] = "member"


class TenantDomainDTO(BaseModel):
    """
    类说明：TenantDomainDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
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
    """
    类说明：TenantSecurityPolicyEditor 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    sso_required: bool = False
    session_timeout_minutes: Optional[int] = Field(default=None, ge=5, le=10080)


class TenantSecurityPolicyDTO(TenantSecurityPolicyEditor):
    """
    类说明：TenantSecurityPolicyDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    id: Optional[int] = None
    tenant_id: int
    create_time: int = 0
    update_time: int = 0


class TenantTrackingTableBase(BaseModel):
    """
    类说明：TenantTrackingTableBase 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    table_name: str = Field(min_length=1, max_length=255)
    table_comment: Optional[str] = Field(default=None, max_length=4000)
    table_role: Optional[str] = Field(default=None, max_length=64)
    aliases: list[str] = Field(default_factory=list)
    ai_notes: Optional[str] = Field(default=None, max_length=4000)


class TenantTrackingTableDTO(TenantTrackingTableBase):
    """
    类说明：TenantTrackingTableDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    id: Optional[int] = None
    tenant_id: int = 0
    create_by: Optional[int] = None
    update_by: Optional[int] = None
    create_time: int = 0
    update_time: int = 0


class TenantTrackingFieldBase(BaseModel):
    """
    类说明：TenantTrackingFieldBase 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    table_name: str = Field(min_length=1, max_length=255)
    field_name: str = Field(min_length=1, max_length=255)
    field_comment: Optional[str] = Field(default=None, max_length=4000)
    field_role: Optional[str] = Field(default=None, max_length=64)
    semantic_type: Optional[str] = Field(default=None, max_length=64)
    aliases: list[str] = Field(default_factory=list)
    value_mappings: Optional[Any] = None
    expression: Optional[str] = Field(default=None, max_length=4000)
    required: bool = False
    example_values: list[Any] = Field(default_factory=list)
    ai_notes: Optional[str] = Field(default=None, max_length=4000)


class TenantTrackingFieldDTO(TenantTrackingFieldBase):
    """
    类说明：TenantTrackingFieldDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    id: Optional[int] = None
    tenant_id: int = 0
    create_by: Optional[int] = None
    update_by: Optional[int] = None
    create_time: int = 0
    update_time: int = 0


class TenantTrackingConfigBase(BaseModel):
    """
    类说明：TenantTrackingConfigBase 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    enabled: bool = True
    default_event_table: Optional[str] = Field(default=None, max_length=255)
    default_subject_field: Optional[str] = Field(default=None, max_length=255)
    default_event_name_field: Optional[str] = Field(default=None, max_length=255)
    default_event_time_field: Optional[str] = Field(default=None, max_length=255)
    field_role_mappings: list[Any] = Field(default_factory=list)
    event_name_mappings: list[Any] = Field(default_factory=list)
    sql_rules: Optional[str] = Field(default=None, max_length=8000)
    notes: Optional[str] = Field(default=None, max_length=8000)
    tables: list[TenantTrackingTableBase] = Field(default_factory=list)
    fields: list[TenantTrackingFieldBase] = Field(default_factory=list)


class TenantTrackingConfigEditor(TenantTrackingConfigBase):
    """
    类说明：TenantTrackingConfigEditor 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    pass


class TenantTrackingConfigDTO(TenantTrackingConfigBase):
    """
    类说明：TenantTrackingConfigDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    id: Optional[int] = None
    tenant_id: int
    tables: list[TenantTrackingTableDTO] = Field(default_factory=list)
    fields: list[TenantTrackingFieldDTO] = Field(default_factory=list)
    create_by: Optional[int] = None
    update_by: Optional[int] = None
    create_time: int = 0
    update_time: int = 0


class TenantDataRequestCreator(BaseModel):
    """
    类说明：TenantDataRequestCreator 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    request_type: Literal["cancel", "export", "delete"]
    reason: Optional[str] = Field(default=None, max_length=2000)


class TenantDataRequestReview(BaseModel):
    """
    类说明：TenantDataRequestReview 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    approved: bool
    review_comment: Optional[str] = Field(default=None, max_length=2000)


class TenantDataRequestComplete(BaseModel):
    """
    类说明：TenantDataRequestComplete 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    complete_comment: Optional[str] = Field(default=None, max_length=2000)


class TenantDataRequestDTO(BaseModel):
    """
    类说明：TenantDataRequestDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
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
    """
    类说明：TenantBulkInviteCreator 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    accounts: list[str] = Field(min_length=1, max_length=200)
    requested_role: Literal["admin", "member"] = "member"
    reason: Optional[str] = Field(default=None, max_length=2000)


class TenantBulkInviteResult(BaseModel):
    """
    类说明：TenantBulkInviteResult 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    account: str
    status: str
    message: Optional[str] = None
    application_id: Optional[int] = None


class TenantMemberDTO(BaseModel):
    """
    类说明：TenantMemberDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    user_id: int
    account: str
    name: Optional[str] = None
    member_remark: Optional[str] = None
    tenant_role: str = "member"
    is_primary: bool = False
    create_time: int = 0
    project_ids: list[int] = Field(default_factory=list)
    project_role_map: dict[int, str] = Field(default_factory=dict)


class TenantMemberCreator(BaseModel):
    """
    类说明：TenantMemberCreator 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    account: str = Field(min_length=1, max_length=100)
    member_remark: Optional[str] = Field(default=None, max_length=255)
    tenant_role: Literal["admin", "member"] = "member"
    project_ids: Optional[list[int]] = None
    project_role_map: Optional[dict[int, str]] = None


class TenantMemberEditor(BaseModel):
    """
    类说明：TenantMemberEditor 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    member_remark: Optional[str] = Field(default=None, max_length=255)
    tenant_role: Literal["admin", "member"] = "member"
    project_ids: Optional[list[int]] = None
    project_role_map: Optional[dict[int, str]] = None


class TenantBulkMemberCreator(BaseModel):
    """
    类说明：TenantBulkMemberCreator 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    accounts: list[str] = Field(min_length=1, max_length=200)
    tenant_role: Literal["admin", "member"] = "member"


class TenantBulkMemberResult(BaseModel):
    """
    类说明：TenantBulkMemberResult 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    account: str
    status: str
    message: Optional[str] = None
    user_id: Optional[int] = None


class TenantOverviewSummaryDTO(BaseModel):
    """
    类说明：TenantOverviewSummaryDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    member_total: int = 0
    active_member_count: int = 0
    datasource_total: int = 0
    dashboard_total: int = 0
    pending_member_application_count: int = 0


class TenantOverviewTrendPointDTO(BaseModel):
    """
    类说明：TenantOverviewTrendPointDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    date: str
    active_member_count: int = 0
    activity_count: int = 0
    login_count: int = 0


class TenantOverviewAssetItemDTO(BaseModel):
    """
    类说明：TenantOverviewAssetItemDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    key: str
    count: int = 0


class TenantOverviewRoleItemDTO(BaseModel):
    """
    类说明：TenantOverviewRoleItemDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    role: str
    count: int = 0


class TenantOverviewTodoDTO(BaseModel):
    """
    类说明：TenantOverviewTodoDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    key: str
    level: str = "normal"
    count: Optional[int] = None
    route: Optional[str] = None


class TenantOverviewEventDTO(BaseModel):
    """
    类说明：TenantOverviewEventDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    id: str
    title: str
    description: Optional[str] = None
    create_time: int = 0
    operator_name: Optional[str] = None
    module: Optional[str] = None
    resource_name: Optional[str] = None


class TenantOverviewMemberActivityDTO(BaseModel):
    """
    类说明：TenantOverviewMemberActivityDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    user_id: int
    account: Optional[str] = None
    name: Optional[str] = None
    tenant_role: str = "member"
    last_active_time: int = 0


class TenantOverviewDTO(BaseModel):
    """
    类说明：TenantOverviewDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    tenant_id: int
    tenant_public_id: Optional[str] = None
    tenant_name: str
    days: int = 7
    summary: TenantOverviewSummaryDTO
    activity_trend: list[TenantOverviewTrendPointDTO] = []
    assets: list[TenantOverviewAssetItemDTO] = []
    role_distribution: list[TenantOverviewRoleItemDTO] = []
    todos: list[TenantOverviewTodoDTO] = []
    recent_events: list[TenantOverviewEventDTO] = []
    member_last_activities: list[TenantOverviewMemberActivityDTO] = []


class PlatformOverviewSummaryDTO(BaseModel):
    """
    类说明：PlatformOverviewSummaryDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    tenant_total: int = 0
    active_tenant_count: int = 0
    disabled_tenant_count: int = 0
    user_total: int = 0
    active_user_count: int = 0
    platform_admin_count: int = 0
    new_tenant_count: int = 0
    new_user_count: int = 0
    paying_tenant_count: int = 0
    trial_tenant_count: int = 0
    past_due_tenant_count: int = 0
    suspended_tenant_count: int = 0
    cancelled_tenant_count: int = 0
    contract_tenant_count: int = 0
    active_usage_tenant_count: int = 0
    revenue_data_ready: bool = False
    revenue_amount: Optional[float] = None
    datasource_total: int = 0
    bound_datasource_count: int = 0
    dashboard_total: int = 0
    pending_workspace_application_count: int = 0
    pending_data_request_count: int = 0
    request_count: int = 0
    total_tokens: int = 0
    failure_count: int = 0


class PlatformOverviewTrendPointDTO(BaseModel):
    """
    类说明：PlatformOverviewTrendPointDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    date: str
    tenant_created_count: int = 0
    user_created_count: int = 0
    active_tenant_count: int = 0
    request_count: int = 0
    failure_count: int = 0
    total_tokens: int = 0


class PlatformOverviewDistributionItemDTO(BaseModel):
    """
    类说明：PlatformOverviewDistributionItemDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    key: str
    label: Optional[str] = None
    count: int = 0


class PlatformOverviewTenantUsageDTO(BaseModel):
    """
    类说明：PlatformOverviewTenantUsageDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    tenant_id: int
    tenant_public_id: Optional[str] = None
    tenant_name: Optional[str] = None
    request_count: int = 0
    total_tokens: int = 0
    failure_count: int = 0


class PlatformOverviewModelUsageDTO(BaseModel):
    """
    类说明：PlatformOverviewModelUsageDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    model_id: Optional[int] = None
    model_name: str
    request_count: int = 0
    total_tokens: int = 0


class PlatformOverviewRecentTenantDTO(BaseModel):
    """
    类说明：PlatformOverviewRecentTenantDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    id: int
    public_id: str
    name: str
    plan: str = "default"
    status: int = 1
    subscription_status: str = "active"
    create_time: int = 0
    bound_datasource_name: Optional[str] = None
    owner_account: Optional[str] = None


class PlatformOverviewDTO(BaseModel):
    """
    类说明：PlatformOverviewDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    days: int = 7
    summary: PlatformOverviewSummaryDTO
    tenant_trend: list[PlatformOverviewTrendPointDTO] = []
    subscription_distribution: list[PlatformOverviewDistributionItemDTO] = []
    plan_distribution: list[PlatformOverviewDistributionItemDTO] = []
    datasource_distribution: list[PlatformOverviewDistributionItemDTO] = []
    top_tenant_usage: list[PlatformOverviewTenantUsageDTO] = []
    model_usage: list[PlatformOverviewModelUsageDTO] = []
    recent_tenants: list[PlatformOverviewRecentTenantDTO] = []
