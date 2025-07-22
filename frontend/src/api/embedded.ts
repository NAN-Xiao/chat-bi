import { request } from '@/utils/request'

export const getList = () => request.get('/system/assistant')
export const updateAssistant = (data: any) => request.put('/system/assistant', data)
export const saveAssistant = (data: any) => request.post('/system/assistant', data)
export const getOne = (id: any) => request.get(`/system/assistant/${id}`)
export const delOne = (id: any) => request.delete(`/system/assistant/${id}`)
