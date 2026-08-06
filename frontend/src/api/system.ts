import { request } from '@/utils/request'

export const modelApi = {
  queryAll: (keyword?: string) =>
    request.get('/system/aimodel', { params: keyword ? { keyword } : {} }),
  add: (data: any) => {
    const param = { ...data }
    return request.post('/system/aimodel', param)
  },
  edit: (data: any) => {
    const param = { ...data }
    return request.put('/system/aimodel', param)
  },
  delete: (id: number) => request.delete(`/system/aimodel/${id}`),
  query: (id: number) => request.get(`/system/aimodel/${id}`),
  setDefault: (id: number) => request.put(`/system/aimodel/default/${id}`),
  check: (data: any) => request.fetchStream('/system/aimodel/status', data),
  fetchModels: (data: { api_domain: string; api_key: string }) =>
    request.post('/system/aimodel/models', data),
  listAvailable: () => request.get('/system/aimodel/list/available'),
}

export const trackingConfigApi = {
  get: () => request.get('/system/tracking-config'),
  eventCatalog: (datasourceId?: number | string) =>
    request.get('/system/tracking-config/event-catalog', {
      params: datasourceId ? { datasource_id: datasourceId } : undefined,
    }),
  update: (data: any) => request.put('/system/tracking-config', data),
  downloadTemplate: () => request.download('/system/tracking-config/template'),
  exportExcel: () => request.download('/system/tracking-config/export'),
  importExcel: (file: File) => request.upload('/system/tracking-config/importExcel', file),
}
