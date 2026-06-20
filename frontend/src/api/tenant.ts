import { request } from '@/utils/request'

export interface TenantInfo {
  id: number | string
  code: string
  name: string
  role: string
  plan?: string
  status?: number
  subscription_status?: string
  billing_mode?: string
  trial_end_time?: number
  current_period_end_time?: number
  contract_no?: string
  billing_contact?: string
  billing_email?: string
  subscription_note?: string
  create_time?: number
  update_time?: number
  owner_user_id?: number | string
  owner_account?: string
  owner_name?: string
  owner_email?: string
  bound_project_id?: number | string | null
  bound_project_name?: string | null
  admin_count?: number
  member_count?: number
  join_time?: number
}

export interface TenantSearchInfo {
  id: number | string
  code: string
  name: string
  plan?: string
  status?: number
  subscription_status?: string
  already_joined?: boolean
}

export interface TenantApplicationInfo {
  id: number | string
  application_type?: string
  applicant_user_id: number | string
  applicant_account?: string
  applicant_name?: string
  applicant_email?: string
  invited_by_user_id?: number | string
  inviter_account?: string
  inviter_name?: string
  inviter_email?: string
  tenant_id?: number | string
  tenant_code: string
  tenant_name: string
  plan: string
  requested_role: string
  reason?: string
  status: string
  reviewer_user_id?: number | string
  review_comment?: string
  create_time?: number
  update_time?: number
  review_time?: number
}

export interface TenantApplicationPayload {
  application_type?: 'create' | 'join'
  tenant_id?: number | string
  tenant_code?: string
  tenant_name?: string
  plan?: string
  requested_role?: string
  reason?: string
}

export interface TenantUsageDailyInfo {
  tenant_id: number | string
  usage_date: string
  metric: string
  request_count: number
  success_count: number
  failure_count: number
  total_tokens: number
  task_count: number
  update_time?: number
}

export interface TenantDomainInfo {
  id: number | string
  tenant_id: number | string
  domain: string
  auto_join_role: string
  status: string
  requested_by_user_id?: number | string
  verified_by_user_id?: number | string
  create_time?: number
  update_time?: number
  verify_time?: number
}

export interface TenantSecurityPolicyInfo {
  id?: number | string
  tenant_id: number | string
  sso_required: boolean
  session_timeout_minutes?: number | null
  create_time?: number
  update_time?: number
}

export interface TenantDataRequestInfo {
  id: number | string
  tenant_id: number | string
  request_type: 'cancel' | 'export' | 'delete' | string
  status: string
  requested_by_user_id: number | string
  reviewer_user_id?: number | string
  completed_by_user_id?: number | string
  reason?: string
  review_comment?: string
  export_manifest?: string
  create_time?: number
  update_time?: number
  review_time?: number
  complete_time?: number
}

export interface TenantBulkInviteResult {
  account: string
  status: string
  message?: string
  application_id?: number | string
}

export interface TenantMemberInfo {
  user_id: number | string
  account: string
  name?: string
  member_remark?: string
  tenant_role: string
  is_primary?: boolean
  create_time?: number
  project_ids?: Array<number | string>
  project_role_map?: Record<string, string>
}

export interface TenantBulkMemberResult {
  account: string
  status: string
  message?: string
  user_id?: number | string
}

export interface TenantOverviewSummaryInfo {
  member_total: number
  active_member_count: number
  datasource_total: number
  dashboard_total: number
  pending_member_application_count: number
}

export interface TenantOverviewTrendPointInfo {
  date: string
  active_member_count: number
  activity_count: number
  login_count: number
}

export interface TenantOverviewAssetItemInfo {
  key: string
  count: number
}

export interface TenantOverviewRoleItemInfo {
  role: string
  count: number
}

export interface TenantOverviewTodoInfo {
  key: string
  level: string
  count?: number | null
  route?: string | null
}

export interface TenantOverviewEventInfo {
  id: string
  title: string
  description?: string | null
  create_time: number
  operator_name?: string | null
  module?: string | null
  resource_name?: string | null
}

export interface TenantOverviewMemberActivityInfo {
  user_id: number | string
  account?: string | null
  name?: string | null
  tenant_role: string
  last_active_time: number
}

export interface TenantOverviewInfo {
  tenant_id: number | string
  tenant_name: string
  days: number
  summary: TenantOverviewSummaryInfo
  activity_trend: TenantOverviewTrendPointInfo[]
  assets: TenantOverviewAssetItemInfo[]
  role_distribution: TenantOverviewRoleItemInfo[]
  todos: TenantOverviewTodoInfo[]
  recent_events: TenantOverviewEventInfo[]
  member_last_activities?: TenantOverviewMemberActivityInfo[]
}

export interface TenantUsageQuery {
  tenant_id?: number | string
  start_date?: string
  end_date?: string
  metric?: string
  limit?: number
}

export interface TenantUsageUserInfo {
  tenant_id: number | string
  user_id: number | string
  user_account?: string | null
  user_name?: string | null
  request_count: number
  success_count: number
  failure_count: number
  total_tokens: number
  last_used_time: number
}

const buildTenantUsageQuery = (params: TenantUsageQuery = {}) => {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    searchParams.append(key, String(value))
  })
  const query = searchParams.toString()
  return query ? `?${query}` : ''
}

const buildOptionalTenantQuery = (
  params: { tenant_id?: number | string; status?: string } = {}
) => {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    searchParams.append(key, String(value))
  })
  const query = searchParams.toString()
  return query ? `?${query}` : ''
}

export const tenantApi = {
  current: () => request.get<TenantInfo>('/system/tenant/current'),
  list: () => request.get<TenantInfo[]>('/system/tenant/list'),
  search: (keyword: string) =>
    request.get<TenantSearchInfo[]>(`/system/tenant/search?keyword=${encodeURIComponent(keyword)}`),
  adminList: () => request.get<TenantInfo[]>('/system/tenant/admin/list'),
  myApplications: () => request.get<TenantApplicationInfo[]>('/system/tenant/application/my'),
  adminApplications: (status?: string) =>
    request.get<TenantApplicationInfo[]>(
      `/system/tenant/application/admin/list${status ? `?status=${status}` : ''}`
    ),
  submitApplication: (data: TenantApplicationPayload) =>
    request.post<TenantApplicationInfo>('/system/tenant/application', data),
  cancelApplication: (id: number | string) =>
    request.delete<TenantApplicationInfo>(`/system/tenant/application/${id}`),
  reviewApplication: (
    id: number | string,
    data: { approved: boolean; tenant_code?: string; review_comment?: string }
  ) =>
    request.post<TenantApplicationInfo>(`/system/tenant/application/${id}/review`, data),
  tenantApplications: (status?: string) =>
    request.get<TenantApplicationInfo[]>(
      `/system/tenant/application/tenant/list${status ? `?status=${status}` : ''}`
    ),
  reviewTenantApplication: (
    id: number | string,
    data: { approved: boolean; review_comment?: string }
  ) => request.post<TenantApplicationInfo>(`/system/tenant/application/tenant/${id}/review`, data),
  invite: (data: { account: string; requested_role: 'admin' | 'member'; reason?: string }) =>
    request.post<TenantApplicationInfo>('/system/tenant/invitation', data),
  bulkInvite: (data: { accounts: string[]; requested_role: 'admin' | 'member'; reason?: string }) =>
    request.post<TenantBulkInviteResult[]>('/system/tenant/invitation/bulk', data),
  invitations: (status?: string) =>
    request.get<TenantApplicationInfo[]>(
      `/system/tenant/invitation/list${status ? `?status=${status}` : ''}`
    ),
  myInvitations: () => request.get<TenantApplicationInfo[]>('/system/tenant/invitation/my'),
  respondInvitation: (id: number | string, data: { approved: boolean; review_comment?: string }) =>
    request.post<TenantApplicationInfo>(`/system/tenant/invitation/${id}/respond`, data),
  cancelInvitation: (id: number | string) =>
    request.delete<TenantApplicationInfo>(`/system/tenant/invitation/${id}`),
  transferOwner: (targetUserId: number | string) =>
    request.post<TenantInfo>('/system/tenant/owner/transfer', { target_user_id: targetUserId }),
  leave: (id: number | string) => request.post<TenantInfo[]>(`/system/tenant/${id}/leave`),
  members: (keyword?: string) =>
    request.get<TenantMemberInfo[]>(
      `/system/tenant/member/list${keyword ? `?keyword=${encodeURIComponent(keyword)}` : ''}`
    ),
  addMember: (data: {
    account: string
    member_remark?: string
    tenant_role: 'admin' | 'member'
    project_ids?: Array<number | string>
    project_role_map?: Record<string, string>
  }) => request.post<TenantMemberInfo>('/system/tenant/member', data),
  bulkAddMembers: (data: { accounts: string[]; tenant_role: 'admin' | 'member' }) =>
    request.post<TenantBulkMemberResult[]>('/system/tenant/member/bulk', data),
  updateMember: (
    userId: number | string,
    data: {
      member_remark?: string
      tenant_role: 'admin' | 'member'
      project_ids?: Array<number | string>
      project_role_map?: Record<string, string>
    }
  ) => request.put<TenantMemberInfo>(`/system/tenant/member/${userId}`, data),
  removeMember: (userId: number | string) =>
    request.delete<TenantMemberInfo>(`/system/tenant/member/${userId}`),
  add: (data: {
    code: string
    name: string
    plan?: string
    subscription_status?: string
    billing_mode?: string
    trial_end_time?: number | null
    current_period_end_time?: number | null
    contract_no?: string
    billing_contact?: string
    billing_email?: string
    subscription_note?: string
  }) => request.post<TenantInfo>('/system/tenant', data),
  edit: (
    id: number | string,
    data: {
      name: string
      plan?: string
      subscription_status?: string
      billing_mode?: string
      trial_end_time?: number | null
      current_period_end_time?: number | null
      contract_no?: string
      billing_contact?: string
      billing_email?: string
      subscription_note?: string
    }
  ) => request.put<TenantInfo>(`/system/tenant/${id}`, data),
  status: (id: number | string, status: number) =>
    request.patch<TenantInfo>(`/system/tenant/${id}/status`, { status }),
  updateProjectBinding: (
    id: number | string,
    data: { datasource_id?: number | string | null }
  ) => request.put<TenantInfo>(`/system/tenant/${id}/project-binding`, data),
  delete: (id: number | string) => request.delete<TenantInfo>(`/system/tenant/${id}`),
  overview: (days = 7) => request.get<TenantOverviewInfo>(`/system/tenant/overview?days=${days}`),
  usage: (params?: TenantUsageQuery) =>
    request.get<TenantUsageDailyInfo[]>(`/system/tenant/usage${buildTenantUsageQuery(params)}`),
  usageByUser: (params?: TenantUsageQuery) =>
    request.get<TenantUsageUserInfo[]>(`/system/tenant/usage/user${buildTenantUsageQuery(params)}`),
  bindDomain: (data: { domain: string; auto_join_role: 'admin' | 'member' }) =>
    request.post<TenantDomainInfo>('/system/tenant/domain', data),
  domains: () => request.get<TenantDomainInfo[]>('/system/tenant/domain/list'),
  adminDomains: (tenantId?: number | string) =>
    request.get<TenantDomainInfo[]>(
      `/system/tenant/domain/admin/list${buildOptionalTenantQuery({ tenant_id: tenantId })}`
    ),
  reviewDomain: (
    id: number | string,
    data: { status: 'verified' | 'disabled'; auto_join_role: 'admin' | 'member' }
  ) => request.post<TenantDomainInfo>(`/system/tenant/domain/${id}/review`, data),
  security: () => request.get<TenantSecurityPolicyInfo>('/system/tenant/security'),
  updateSecurity: (data: {
    sso_required: boolean
    session_timeout_minutes?: number | null
  }) => request.put<TenantSecurityPolicyInfo>('/system/tenant/security', data),
  dataRequests: (params?: { tenant_id?: number | string; status?: string }) =>
    request.get<TenantDataRequestInfo[]>(
      `/system/tenant/data-request/list${buildOptionalTenantQuery(params)}`
    ),
  submitDataRequest: (data: { request_type: 'cancel' | 'export' | 'delete'; reason?: string }) =>
    request.post<TenantDataRequestInfo>('/system/tenant/data-request', data),
  reviewDataRequest: (id: number | string, data: { approved: boolean; review_comment?: string }) =>
    request.post<TenantDataRequestInfo>(`/system/tenant/data-request/${id}/review`, data),
  completeDataRequest: (id: number | string, data: { complete_comment?: string }) =>
    request.post<TenantDataRequestInfo>(`/system/tenant/data-request/${id}/complete`, data),
}
