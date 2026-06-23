import { request } from '@/utils/request'

export type KnowledgeBaseScope = 'ADMIN_PUBLIC' | 'PLATFORM_PUBLIC'
export type KnowledgeBaseStatus = 'PENDING' | 'PROCESSING' | 'READY' | 'FAILED'

export interface KnowledgeBaseItem {
  id: number | string
  tenant_id: number | string
  create_by?: number | string | null
  name: string
  description?: string | null
  content?: string | null
  visibility_scope: KnowledgeBaseScope
  active: boolean
  status: KnowledgeBaseStatus
  file_id?: string | null
  file_name?: string | null
  file_ext?: string | null
  task_id?: string | null
  error_message?: string | null
  create_time?: string | null
  update_time?: string | null
  can_manage?: boolean
}

export interface KnowledgeBaseSavePayload {
  id?: number | string | null
  name: string
  description?: string
  active: boolean
  visibility_scope: KnowledgeBaseScope
  file?: File | null
}

const buildFormData = (payload: KnowledgeBaseSavePayload) => {
  const formData = new FormData()
  if (payload.id) formData.append('id', String(payload.id))
  formData.append('name', payload.name)
  formData.append('description', payload.description || '')
  formData.append('active', String(payload.active))
  formData.append('visibility_scope', payload.visibility_scope)
  if (payload.file) formData.append('file', payload.file)
  return formData
}

export const knowledgeBaseApi = {
  list: (params: { visibility_scope: KnowledgeBaseScope; keyword?: string }) =>
    request.get<KnowledgeBaseItem[]>('/knowledge-base/list', { params }),
  save: (payload: KnowledgeBaseSavePayload) =>
    request.post<KnowledgeBaseItem>('/knowledge-base/save', buildFormData(payload), {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }),
  delete: (id: number | string) => request.delete(`/knowledge-base/${id}`),
}
