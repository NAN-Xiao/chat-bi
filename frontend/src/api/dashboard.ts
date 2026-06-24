import { request } from '@/utils/request'

export const dashboardApi = {
  list_resource: (params: any, config?: any) => request.post('/dashboard/list_resource', params, config),
  load_resource: (params: any, config?: any) => request.post('/dashboard/load_resource', params, config),
  create_resource: (params: any) => request.post('/dashboard/create_resource', params),
  update_resource: (params: any) => request.post('/dashboard/update_resource', params),
  create_canvas: (params: any) => request.post('/dashboard/create_canvas', params),
  update_canvas: (params: any) => request.post('/dashboard/update_canvas', params),
  check_name: (params: any) => request.post('/dashboard/check_name', params),
  preview_sql: (params: any, config?: any) => request.post('/dashboard/sql_preview', params, config),
  default_list: (config?: any) => request.get('/dashboard/default/list', config),
  default_load: (params: any, config?: any) => request.post('/dashboard/default/load', params, config),
  default_copy: (params: any, config?: any) => request.post('/dashboard/default/copy', params, config),
  default_set: (params: any, config?: any) => request.post('/dashboard/default/set', params, config),
  default_sort: (params: any, config?: any) => request.post('/dashboard/default/sort', params, config),
  delegate_draft_list: (config?: any) => request.get('/dashboard/platform-delegate/draft/list', config),
  delegate_draft_load: (params: any, config?: any) =>
    request.post('/dashboard/platform-delegate/draft/load', params, config),
  delegate_draft_update: (params: any, config?: any) =>
    request.post('/dashboard/platform-delegate/draft/update', params, config),
  delegate_draft_maintain: (params: any, config?: any) =>
    request.post('/dashboard/platform-delegate/draft/maintain', params, config),
  delegate_draft_publish: (params: any, config?: any) =>
    request.post('/dashboard/platform-delegate/draft/publish', params, config),
  delegate_draft_delete: (params: any, config?: any) =>
    request.post('/dashboard/platform-delegate/draft/delete', params, config),
  platform_template_list: (config?: any) =>
    request.get('/dashboard/platform-delegate/template/list', config),
  platform_template_copy_from_dashboard: (params: any, config?: any) =>
    request.post('/dashboard/platform-delegate/template/copy-from-dashboard', params, config),
  platform_template_copy_to_draft: (params: any, config?: any) =>
    request.post('/dashboard/platform-delegate/template/copy-to-draft', params, config),
  share: (params: any, config?: any) => request.post('/dashboard/share', params, config),
  share_list: (params: any, config?: any) => request.post('/dashboard/share/list', params, config),
  share_load: (params: any, config?: any) => request.post('/dashboard/share/load', params, config),
  share_delete: (params: any, config?: any) => request.post('/dashboard/share/delete', params, config),
  share_use: (params: any, config?: any) => request.post('/dashboard/share/use', params, config),
  delete_resource: (params: any) =>
    request.delete(`/dashboard/delete_resource/${params.id}/${params.name}`, params),
  move_resource: (params: any) =>
    request.delete(`/dashboard/move_resource/${params.id}`, { data: params }),
}
