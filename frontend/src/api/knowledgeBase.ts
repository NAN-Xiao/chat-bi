import { request } from '@/utils/request'
import type { AxiosResponse } from 'axios'

export type KnowledgeBaseScope = 'ADMIN_PUBLIC' | 'PLATFORM_PUBLIC'
export type KnowledgeBaseStatus = 'PENDING' | 'PROCESSING' | 'READY' | 'FAILED'

export interface KnowledgeBaseItem {
  id: number | string
  tenant_id: number | string
  create_by?: number | string | null
  uploaded_by?: number | string | null
  uploaded_by_name?: string | null
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
  tenant_id?: number | string
  name: string
  description?: string
  active: boolean
  visibility_scope: KnowledgeBaseScope
  file?: File | null
}

export interface KnowledgeDocumentDownload {
  blob: Blob
  filename: string
  recovered: boolean
}

function downloadFilename(disposition: string): string {
  const encoded = disposition.match(/(?:^|;)\s*filename\*=utf-8''([^;]+)/i)
  const plain = disposition.match(/(?:^|;)\s*filename=(?:"([^"]+)"|([^;]+))/i)
  const filename = encoded
    ? decodeURIComponent(encoded[1].trim())
    : (plain?.[1] || plain?.[2] || '').trim()
  if (!filename) throw new Error('下载文件名缺失，无法保存文件。')
  return filename
}

const buildFormData = (payload: KnowledgeBaseSavePayload) => {
  const formData = new FormData()
  if (payload.id) formData.append('id', String(payload.id))
  if (payload.tenant_id !== undefined) formData.append('tenant_id', String(payload.tenant_id))
  formData.append('name', payload.name)
  formData.append('description', payload.description || '')
  formData.append('active', String(payload.active))
  formData.append('visibility_scope', payload.visibility_scope)
  if (payload.file) formData.append('file', payload.file)
  return formData
}

export const knowledgeBaseApi = {
  list: (params: {
    visibility_scope: KnowledgeBaseScope
    tenant_id?: number | string
    keyword?: string
  }) => request.get<KnowledgeBaseItem[]>('/knowledge-base/list', { params }),
  save: (payload: KnowledgeBaseSavePayload) =>
    request.post<KnowledgeBaseItem>('/knowledge-base/save', buildFormData(payload), {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }),
  delete: (id: number | string, tenantId?: number | string) =>
    request.delete(`/knowledge-base/${id}`, {
      params: tenantId === undefined ? undefined : { tenant_id: tenantId },
    }),
  download: async (id: number | string, tenantId?: number | string): Promise<KnowledgeDocumentDownload> => {
    const response = await request.get<AxiosResponse<Blob>>(`/knowledge-base/${id}/download`, {
      params: tenantId === undefined ? undefined : { tenant_id: tenantId },
      responseType: 'blob',
      requestOptions: { rawResponse: true },
    })
    return {
      blob: response.data,
      filename: downloadFilename(String(response.headers['content-disposition'] || '')),
      recovered: response.headers['x-knowledge-document-recovered'] === 'true',
    }
  },
}
