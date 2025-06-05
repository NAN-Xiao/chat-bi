import { request } from '@/utils/request'

export const datasourceApi = {
  check: (data: any) => request.post('/datasource/check', data),
  add: (data: any) => request.post('/datasource/add', data),
  list: () => request.get('/datasource/list'),
  update: (data: any) => request.post('/datasource/update', data),
  delete: (id: Number) => request.post(`/datasource/delete/${id}`),
  getTables: (id: Number) => request.post(`/datasource/getTables/${id}`),
  getTablesByConf: (data: any) => request.post('/datasource/getTablesByConf', data),
  getFields: (id: Number, table_name: string) => request.post(`/datasource/getFields/${id}/${table_name}`),
  execSql: (id: Number, sql: string) => request.post(`/datasource/execSql/${id}/${sql}`),
  chooseTables: (id: Number, data: any) => request.post(`/datasource/chooseTables/${id}`, data),
  tableList: (id: Number) => request.post(`/datasource/tableList/${id}`),
  fieldList: (id: Number) => request.post(`/datasource/fieldList/${id}`),
  edit: (data: any) => request.post('/datasource/editLocalComment', data),
  previewData: (id: Number, data: any) => request.post(`/datasource/previewData/${id}`, data),
  saveTable: (data: any) => request.post('/datasource/editTable', data),
  saveField: (data: any) => request.post('/datasource/editField', data)
}