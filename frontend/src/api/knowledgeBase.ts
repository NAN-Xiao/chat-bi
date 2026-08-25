import { request } from '@/utils/request'

export type KnowledgeBaseScope = 'ADMIN_PUBLIC' | 'PLATFORM_PUBLIC'

export interface KnowledgeBaseItem {
  id: number | string
  tenant_id: number | string
  create_by?: number | string | null
  name: string
  description?: string | null
  content?: string | null
  visibility_scope: KnowledgeBaseScope
  active: boolean
  file_id?: string | null
  file_name?: string | null
  file_ext?: string | null
  create_time?: string | null
  update_time?: string | null
  can_manage?: boolean
  archived?: boolean
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
  create_time?: string | null
  publish_time?: string | null
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

export interface KnowledgeApplicabilityState {
  knowledge_base_id: number | string
  version_id?: number | string | null
  datasource_id: number | string
  status: 'VALID' | 'INVALID' | 'STALE' | 'ERROR'
  status_text: '可用' | '不适用' | '待检查' | '检查失败'
  schema_hash_prefix?: string | null
  reference_count: number
  resolved_count: number
  warnings: string[]
  checked_at?: string | null
}

export interface KnowledgeRetrievalPreviewResult {
  context?: string
  citations?: Array<{
    knowledge_base_name?: string | null
    knowledge_base_id?: number | string | null
    version_number?: number | null
    section_path?: string | null
    source_block_id?: string | null
    source_file_name?: string | null
    score?: number | null
    content?: string | null
    visibility_scope?: KnowledgeBaseScope | null
  }>
  warnings?: Array<{ message?: string } | string>
  failure_type?: string | null
  latency_ms?: number
}

export interface KnowledgeConflictDetails {
  conflict_type?: 'BLOCK' | 'BLOCK_DELETED' | 'STRUCTURE'
  block_id?: string
  structure_revision?: number
  server_block?: Record<string, any>
  server_payload?: Record<string, any>
}

export interface KnowledgeBaseCreatePayload {
  name: string
  description?: string
  visibility_scope: KnowledgeBaseScope
  tenant_id?: number | string | null
}

export interface KnowledgeRemovalResult {
  id: number | string
  archived: boolean
  deleted: boolean
  file_cleanup: {
    deleted: number
    missing: number
    referenced: number
    failed: number
  }
}

export const knowledgeBaseApi = {
  capabilities: () => request.get<KnowledgeBaseCapabilities>('/knowledge-base/capabilities'),
  list: (params?: { visibility_scope?: KnowledgeBaseScope; keyword?: string; tenant_id?: number | string; archived?: boolean }) =>
    request.get<KnowledgeBaseItem[]>('/knowledge-base/list', { params }),
  detail: (id: number | string) => request.get<KnowledgeBaseItem>(`/knowledge-base/${id}`),
  create: (payload: KnowledgeBaseCreatePayload) =>
    request.post<KnowledgeBaseItem>('/knowledge-base/create', payload),
  delete: (id: number | string) =>
    request.delete<KnowledgeRemovalResult>(`/knowledge-base/${id}`),
  permanentDelete: (id: number | string) =>
    request.delete<KnowledgeRemovalResult>(`/knowledge-base/${id}/permanent`),
  restore: (id: number | string) =>
    request.post<KnowledgeBaseItem>(`/knowledge-base/${id}/restore`),
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
  saveDocumentBlock: (
    id: number | string,
    blockId: string,
    payload: {
      version_id: number
      block_revision: number
      title: string
      markdown: string
      enabled: boolean
    }
  ) => request.patch<KnowledgeBaseVersion>(`/knowledge-base/${id}/draft/blocks/${blockId}`, payload),
  saveDocumentStructure: (
    id: number | string,
    payload: { version_id: number; structure_revision: number; content: Record<string, any> }
  ) => request.patch<KnowledgeBaseVersion>(`/knowledge-base/${id}/draft/structure`, {
    version_id: payload.version_id,
    structure_revision: payload.structure_revision,
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
    request.download(`/knowledge-base/${id}/versions/${versionId}/download`, {
      requestOptions: { customError: true },
    }),
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
  applicability: (id: number | string, datasourceId: number | string) =>
    request.get<KnowledgeApplicabilityState>(`/knowledge-base/${id}/applicability`, {
      params: { datasource_id: datasourceId },
    }),
  retrievalPreview: (payload: {
    datasource_id: number
    query: string
    surface?: string
    top_k?: number
    max_context_chars?: number
  }) => request.post<KnowledgeRetrievalPreviewResult>('/knowledge-base/retrieval-preview', payload),
}
