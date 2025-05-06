import { request } from '@/utils/request'

export const datasourceApi = {
  check: (data: any) => request.post('/datasource/check', data),
  add: (data: any) => request.post('/datasource/add', data),
  list: () => request.get('/datasource/list')
}