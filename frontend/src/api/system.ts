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
  remoteModels: (data: any) => request.post('/system/aimodel/remote-models', data),
  listAvailable: () => request.get('/system/aimodel/list/available'),
}
