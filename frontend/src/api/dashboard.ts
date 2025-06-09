import { request } from '@/utils/request'

export const dashboardApi = {
  list: (params: any) => request.post('/dashboard/list',params),
  getDashboardInfo: (params:any) => request.post(`/dashboard/get_dashboard/${params.id}`,params),
  sqNameCheck: (data: any) => request.post('/dashboard/name_check',data),
  moveResource: (data: any) => request.post('/dashboard/move',data),
  addResource: (data: any) => request.post('/dashboard/add',data),
  updateResource: (data: any) => request.post('/dashboard/update',data),
  saveCanvas: (data: any) => request.post('/dashboard/add_canvas',data),
  updateCanvas: (data: any) => request.post('/dashboard/update_',data),
  check_name: (data: any) => request.post('/dashboard/check_name',data)
}