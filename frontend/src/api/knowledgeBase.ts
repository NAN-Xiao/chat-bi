import { request } from '@/utils/request'

export type KnowledgeBaseScope = 'ADMIN_PUBLIC' | 'PLATFORM_PUBLIC'
export type KnowledgeBaseStatus = 'PENDING' | 'PROCESSING' | 'READY' | 'FAILED'
export type KnowledgeType = 'DOCUMENT' | 'BUSINESS' | 'EVENT' | 'JSON_FIELD'

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
  archived?: boolean
  knowledge_type?: KnowledgeType | null
  stable_key?: string | null
  draft_version_id?: number | null
  current_version_id?: number | null
  publishing_version_id?: number | null
}

export interface KnowledgeBaseCapabilities {
  phase: 'LEGACY_OPEN' | 'CUTOVER_BARRIER' | 'V2_ACTIVE'
  management_mode: 'LEGACY' | 'UPGRADING' | 'V2' | 'MAINTENANCE'
  legacy_write_enabled: boolean
  v2_write_enabled: boolean
  runtime_context_enabled: boolean
}

export interface KnowledgeBaseVersion {
  id: number
  knowledge_base_id: number
  tenant_id: number
  version_number: number
  revision: number
  status: string
  index_status: string
  payload: Record<string, any>
  normalized_content?: string | null
  validation_report?: {
    valid?: boolean
    errors?: Array<{ code?: string; message?: string; field_path?: string | null }>
    warnings?: Array<{ code?: string; message?: string; field_path?: string | null }>
  } | null
  content_hash?: string | null
  file_name?: string | null
  file_ext?: string | null
  parser_version?: string | null
}

export interface KnowledgePublishJob {
  id: number
  knowledge_base_id: number
  version_id: number
  revision: number
  content_hash: string
  status: string
  task_id?: string | null
  stage?: string | null
  error_code?: string | null
  error_message?: string | null
}

export interface KnowledgeRetrievalPreviewResult {
  context?: string
  citations?: Array<{
    knowledge_base_id?: number | string | null
    section_path?: string | null
    score?: number | null
    visibility_scope?: KnowledgeBaseScope | null
  }>
  warnings?: Array<{ message?: string } | string>
  latency_ms?: number
}

export interface KnowledgeBaseSavePayload {
  id?: number | string | null
  name: string
  description?: string
  active: boolean
  visibility_scope: KnowledgeBaseScope
  file?: File | null
}

export interface KnowledgeBaseCreatePayload {
  name: string
  description?: string
  visibility_scope: KnowledgeBaseScope
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
  capabilities: () => request.get<KnowledgeBaseCapabilities>('/knowledge-base/capabilities'),
  list: (params?: { visibility_scope?: KnowledgeBaseScope; keyword?: string }) =>
    request.get<KnowledgeBaseItem[]>('/knowledge-base/list', { params }),
  detail: (id: number | string) => request.get<KnowledgeBaseItem>(`/knowledge-base/${id}`),
  create: (payload: KnowledgeBaseCreatePayload) =>
    request.post<KnowledgeBaseItem>('/knowledge-base/create', payload),
  save: (payload: KnowledgeBaseSavePayload) =>
    request.post<KnowledgeBaseItem>('/knowledge-base/save', buildFormData(payload), {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }),
  delete: (id: number | string) => request.delete(`/knowledge-base/${id}`),
  createDraft: (id: number | string, payload: Record<string, any>) =>
    request.post<KnowledgeBaseVersion>(`/knowledge-base/${id}/draft`, { payload }),
  saveDraft: (
    id: number | string,
    payload: { version_id: number; revision: number; content: Record<string, any> }
  ) =>
    request.put<KnowledgeBaseVersion>(`/knowledge-base/${id}/draft`, {
      version_id: payload.version_id,
      revision: payload.revision,
      payload: payload.content,
    }),
  replaceDraftFile: (
    id: number | string,
    payload: { version_id: number; revision: number; file: File }
  ) => {
    const formData = new FormData()
    formData.append('version_id', String(payload.version_id))
    formData.append('revision', String(payload.revision))
    formData.append('file', payload.file)
    return request.post<KnowledgeBaseVersion>(`/knowledge-base/${id}/draft/file`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  validateDraft: (
    id: number | string,
    payload: {
      version_id: number
      revision: number
      content_hash: string
      context?: Record<string, any>
    }
  ) => request.post<KnowledgeBaseVersion>(`/knowledge-base/${id}/draft/validate`, payload),
  versions: (id: number | string) =>
    request.get<KnowledgeBaseVersion[]>(`/knowledge-base/${id}/versions`),
  version: (id: number | string, versionId: number | string) =>
    request.get<KnowledgeBaseVersion>(`/knowledge-base/${id}/versions/${versionId}`),
  download: (id: number | string, versionId: number | string) =>
    request.download(`/knowledge-base/${id}/versions/${versionId}/download`),
  publish: (
    id: number | string,
    payload: { version_id: number; revision: number; content_hash: string }
  ) => request.post<KnowledgePublishJob>(`/knowledge-base/${id}/publish`, payload),
  publishJob: (id: number | string) =>
    request.get<KnowledgePublishJob | null>(`/knowledge-base/${id}/publish-job`),
  rollback: (id: number | string, version_id: number) =>
    request.post<KnowledgeBaseVersion>(`/knowledge-base/${id}/rollback`, { version_id }),
  workspaceEnabled: (id: number | string, enabled: boolean, reason?: string) =>
    request.put<{ knowledge_base_id: number | string; tenant_id: number | string; enabled: boolean; reason?: string | null }>(
      `/knowledge-base/${id}/workspace-enabled`,
      { enabled, reason }
    ),
  workspaceEnabledState: (id: number | string) =>
    request.get<{ knowledge_base_id: number | string; tenant_id: number | string; enabled: boolean; reason?: string | null }>(
      `/knowledge-base/${id}/workspace-enabled`
    ),
  retrievalPreview: (payload: {
    datasource_id: number
    query: string
    surface?: string
    top_k?: number
    max_context_chars?: number
  }) => request.post<KnowledgeRetrievalPreviewResult>('/knowledge-base/retrieval-preview', payload),
}
