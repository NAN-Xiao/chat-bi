import { request } from '@/utils/request'

export const questionApi = {
  pager: (pageNumber: number, pageSize: number) => request.get(`/chat/question/pager/${pageNumber}/${pageSize}`),
  // add: (data: any, progress: any) => request.post('/chat/question', data, { responseType: 'stream', onDownloadProgress: progress }),
  add: (data: any) => request.post('/chat/question', data),
  edit: (data: any) => request.put('/chat/question', data),
  delete: (id: number) => request.delete(`/chat/question/${id}`),
  query: (id: number) => request.get(`/chat/question/${id}`)
}