import { request } from '@/utils/request'

export const promptApi = {
  getList: (pageNum: any, pageSize: any, type: any, params: any) =>
    request.get(`/system/custom_prompt/${type}/page/${pageNum}/${pageSize}${params}`),
  options: (params: any) => request.get('/system/custom_prompt/options', { params }),
  updateEmbedded: (data: any) => request.put(`/system/custom_prompt`, data),
  deleteEmbedded: (params: any) => request.delete('/system/custom_prompt', { data: params }),
  getOne: (id: any) => request.get(`/system/custom_prompt/${id}`),
  setActivation: (id: any, enabled: boolean, scope: 'user' | 'global' = 'user') =>
    request.put(`/system/custom_prompt/${id}/activation`, null, {
      params: { enabled, scope },
    }),
  setVisibility: (id: any, visible: boolean) =>
    request.put(`/system/custom_prompt/${id}/visibility`, null, {
      params: { visible },
    }),
  export2Excel: (type: any, params: any) =>
    request.get(`/system/custom_prompt/${type}/export`, {
      params,
      responseType: 'blob',
      requestOptions: { customError: true },
    }),
}
