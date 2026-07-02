import { request } from '@/utils/request'

export const assistantApi = {
  queryAll: (keyword?: string) =>
    request.get('/system/assistant', { params: keyword ? { keyword } : {} }),
  add: (data: any) => request.post('/system/assistant', data),
  edit: (data: any) => request.put('/system/assistant', data),
  delete: (id: number) => request.delete(`/system/assistant/${id}`),
  query: (id: number) => request.get(`/system/assistant/${id}`),
  validate: (data: any, credential?: string, hostOrigin?: string) =>
    request.get('/system/assistant/validator', {
      params: data,
      headers:
        credential || hostOrigin
          ? {
              ...(credential ? { 'X-SHUZHI-ASSISTANT-VALIDATOR': `Embedded ${credential}` } : {}),
              ...(hostOrigin ? { 'X-SHUZHI-HOST-ORIGIN': hostOrigin } : {}),
            }
          : undefined,
    }),
}
