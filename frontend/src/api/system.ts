import { request } from '@/utils/request'

export const modelApi = {
  queryAll: (keyword?: string) =>
    request.get('/system/aimodel', { params: keyword ? { keyword } : {} }),
  add: (data: any) => request.post('/system/aimodel', data),
  edit: (data: any) => request.put('/system/aimodel', data),
  delete: (id: number) => request.delete(`/system/aimodel/${id}`),
  query: (id: number) => request.get(`/system/aimodel/${id}`),
  status: (data: any) => request.patch('/system/aimodel/status', data),
}
