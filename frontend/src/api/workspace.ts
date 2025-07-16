import { request } from '@/utils/request'

export const workspaceUserList = (params: any, pageNum: number, pageSize: number) =>
  request.get(`/system/workspace/uws/pager/${pageNum}/${pageSize}`, { params })

export const workspaceCreate = (data: any) => request.post('/system/workspace/uws', data)
export const workspaceDelete = (data: any) => request.delete('/system/workspace/uws', data)
export const workspaceList = () => request.get('/system/workspace')
export const workspaceDetail = (id: any) => request.get(`/system/workspace/${id}`)
