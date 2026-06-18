import { request } from '@/utils/request'

export interface TenantInfo {
  id: number | string
  code: string
  name: string
  role: string
  plan?: string
  status?: number
  create_time?: number
  update_time?: number
}

export interface TenantSearchInfo {
  id: number | string
  code: string
  name: string
  plan?: string
  status?: number
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
  requested_role: string
  reason?: string
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
  reviewApplication: (id: number | string, data: { approved: boolean; review_comment?: string }) =>
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
  add: (data: { code: string; name: string; plan?: string }) =>
    request.post<TenantInfo>('/system/tenant', data),
  edit: (id: number | string, data: { name: string; plan?: string }) =>
    request.put<TenantInfo>(`/system/tenant/${id}`, data),
  status: (id: number | string, status: number) =>
    request.patch<TenantInfo>(`/system/tenant/${id}/status`, { status }),
}
