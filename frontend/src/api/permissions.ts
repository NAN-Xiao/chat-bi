import { request } from '@/utils/request'

export type PermissionType = 'row' | 'column' | 'table' | 'schema' | 'event' | 'event_property'

export type PermissionDatasourceOption = {
  id: number | string
  name: string
  type?: string
  type_name?: string
  permission_source: 'ordinary' | 'roi'
}

export const getList = () => request.post('/ds_permission/list')
export const savePermissions = (data: any) => request.post('/ds_permission/save', data)
export const delPermissions = (id: any) => request.post(`/ds_permission/delete/${id}`)
export const getPermissionDatasources = (permissionType: PermissionType) =>
  request.get<PermissionDatasourceOption[]>('/ds_permission/datasources', {
    params: { permission_type: permissionType },
  })
export const getPermissionDatasourceTables = (
  datasourceId: number | string,
  permissionType: PermissionType
) =>
  request.get(`/ds_permission/datasources/${datasourceId}/tables`, {
    params: { permission_type: permissionType },
  })
