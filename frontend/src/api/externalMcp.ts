import { request } from '@/utils/request'

export interface ExternalMcpServerInfo {
  id: number | string
  name: string
  endpoint: string
  description?: string | null
  auth_type?: string
  auth_header_name?: string
  server_name?: string | null
  server_version?: string | null
  status?: number
  credential_configured?: boolean
  create_time?: number
  update_time?: number
}

export interface ExternalMcpToolInfo {
  name: string
  title?: string | null
  description?: string | null
  input_schema?: Record<string, any>
  output_schema?: Record<string, any>
}

export const externalMcpApi = {
  list: (params?: { keyword?: string; include_disabled?: boolean }) =>
    request.get<ExternalMcpServerInfo[]>('/external-mcp/list', { params }),
  available: (params?: { tenant_id?: number | string | null; dashboard_id?: number | string | null }) =>
    request.get<ExternalMcpServerInfo[]>('/external-mcp/available', {
      params: {
        ...(params?.tenant_id ? { tenant_id: String(params.tenant_id) } : {}),
        ...(params?.dashboard_id ? { dashboard_id: String(params.dashboard_id) } : {}),
      },
    }),
  tools: (externalMcpServerId: number | string, params?: { tenant_id?: number | string | null; dashboard_id?: number | string | null }) =>
    request.get<ExternalMcpToolInfo[]>(`/external-mcp/${externalMcpServerId}/tools`, {
      params: {
        ...(params?.tenant_id ? { tenant_id: String(params.tenant_id) } : {}),
        ...(params?.dashboard_id ? { dashboard_id: String(params.dashboard_id) } : {}),
      },
    }),
  preview: (data: any, config?: any) => request.post('/external-mcp/preview', data, config),
  add: (data: any) => request.post<ExternalMcpServerInfo>('/external-mcp', data),
  edit: (data: any) => request.put<ExternalMcpServerInfo>('/external-mcp', data),
}
