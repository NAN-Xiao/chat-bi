import { request } from '@/utils/request'

export const modelApi = {
  pager: (pageNumber: number, pageSize: number) => request.get(`/system/aimodel/pager/${pageNumber}/${pageSize}`),
  add: (data: any) => request.post('/system/aimodel', data),
  edit: (data: any) => request.put('/system/aimodel', data),
  delete: (id: number) => request.delete(`/system/aimodel/${id}`),
  query: (id: number) => request.get(`/system/aimodel/${id}`),
  status: (data: any) => request.patch('/system/aimodel/status', data),
}