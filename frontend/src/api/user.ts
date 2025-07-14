import { request } from '@/utils/request'

export const userImportApi = {
  downExcelTemplateApi: () => request.post('/user/excelTemplate', {}, { responseType: 'blob' }),
  importUserApi: (data: any) =>
    request.post('/user/batchImport', data, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }),
  downErrorRecordApi: (key: string) =>
    request.get(`/user/errorRecord/${key}`, { responseType: 'blob' }),
  clearErrorApi: (key: string) => {
    request.get(`/user/clearErrorRecord/${key}`)
  },
}
