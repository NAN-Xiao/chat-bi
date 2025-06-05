import { request } from '@/utils/request'

export const dashboardApi = {
  list: (params: any) => request.post('/dashboard/list',params),
  getDashboardInfo: (params:any) => request.post(`/dashboard/get_dashboard/${params.id}`,params),
  sqNameCheck: (data: any) => request.post('/dashboard/name_check',data),
  moveResource: (data: any) => request.post('/dashboard/move',data),
  addResource: (data: any) => request.post('/dashboard/add',data)
}