import { request } from '@/utils/request'

export const getList = () => request.post('/ds_permission/list')
export const savePermissions = (data: any) => request.post('/ds_permission/save', data)
