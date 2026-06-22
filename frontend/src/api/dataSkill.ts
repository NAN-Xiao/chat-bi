import { request } from '@/utils/request'

const DATA_SKILL_TYPE = 'DATA_SKILL'

export const dataSkillApi = {
  getList: (pageNum: any, pageSize: any, params = '') =>
    request.get(`/system/custom_prompt/${DATA_SKILL_TYPE}/page/${pageNum}/${pageSize}${params}`),
  options: (params: any) =>
    request.get('/system/custom_prompt/options', {
      params: { ...params, custom_prompt_type: DATA_SKILL_TYPE },
    }),
  save: (data: any) => request.put('/system/custom_prompt', { ...data, type: DATA_SKILL_TYPE }),
  delete: (params: any) => request.delete('/system/custom_prompt', { data: params }),
  getOne: (id: any) => request.get(`/system/custom_prompt/${id}`),
  setActivation: (id: any, enabled: boolean, scope: 'user' | 'global' = 'user') =>
    request.put(`/system/custom_prompt/${id}/activation`, null, {
      params: { enabled, scope },
    }),
}
