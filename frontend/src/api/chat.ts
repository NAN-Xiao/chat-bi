import { request } from '@/utils/request'

export const questionApi = {
  pager: (pageNumber: number, pageSize: number) => request.get(`/chat/question/pager/${pageNumber}/${pageSize}`),
  /* add: (data: any) => new Promise((resolve, reject) => {
    request.post('/chat/question', data, { responseType: 'stream', timeout: 0, onDownloadProgress: p => {
      resolve(p)
    }}).catch(e => reject(e))
  }), */
  // add: (data: any) => request.post('/chat/question', data),
  add: (data: any) => request.fetchStream('/chat/question', data),
  edit: (data: any) => request.put('/chat/question', data),
  delete: (id: number) => request.delete(`/chat/question/${id}`),
  query: (id: number) => request.get(`/chat/question/${id}`)
}