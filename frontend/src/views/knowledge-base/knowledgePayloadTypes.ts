export interface DocumentBlock {
  id: string
  title: string
  markdown: string
  enabled: boolean
  block_revision: number
}

export interface DocumentPayload {
  knowledge_type: 'DOCUMENT'
  blocks: DocumentBlock[]
  structure_revision: number
  tags: string[]
  datasource_neutral: boolean
  object_references: KnowledgeObjectReference[]
}

export interface KnowledgeObjectReference {
  object_type: string
  schema?: string | null
  table?: string | null
  field?: string | null
  json_path?: string | null
  event_name?: string | null
  event_property_key?: string | null
}

export interface SqlExample {
  name: string
  question: string
  sql: string
  dialect?: string
  notes?: string
}

export interface BusinessKnowledgePayload {
  knowledge_type: 'BUSINESS'
  term: string
  aliases: string[]
  definition: string
  formula: string
  constraints: string[]
  related_objects: KnowledgeObjectReference[]
  examples: SqlExample[]
}

export interface EventParameter {
  name: string
  display_name?: string
  data_type: string
  required?: boolean
  description?: string
  value_mappings?: Record<string, string>
}

export interface EventKnowledgePayload {
  knowledge_type: 'EVENT'
  event_name: string
  display_name: string
  aliases: string[]
  description: string
  table_name: string
  event_name_field: string
  event_time_field: string
  parameters: EventParameter[]
}

export interface JsonFieldKnowledgePayload {
  knowledge_type: 'JSON_FIELD'
  schema_name: string
  table_name: string
  source_field: string
  json_path: string
  field_name: string
  display_name: string
  data_type: string
  expression: string
  aliases: string[]
  description: string
  value_mappings: Record<string, string>
}

export type KnowledgePayload =
  | DocumentPayload
  | BusinessKnowledgePayload
  | EventKnowledgePayload
  | JsonFieldKnowledgePayload

function documentBlockId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID().replaceAll('-', '')
  }
  return `block-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function createDocumentBlock(title = '', markdown = ''): DocumentBlock {
  return {
    id: documentBlockId(),
    title,
    markdown,
    enabled: true,
    block_revision: 1,
  }
}

export function normalizeDocumentPayload(value: Record<string, any> | DocumentPayload): DocumentPayload {
  const rawBlocks = Array.isArray(value?.blocks) ? value.blocks : null
  const blocks = rawBlocks
    ? rawBlocks.map((block: any) => ({
        id: String(block?.id || documentBlockId()),
        title: String(block?.title || ''),
        markdown: String(block?.markdown || ''),
        enabled: block?.enabled !== false,
        block_revision: Math.max(1, Number(block?.block_revision) || 1),
      }))
    : [createDocumentBlock('正文', String((value as Record<string, any>)?.markdown || ''))]
  return {
    knowledge_type: 'DOCUMENT',
    blocks: blocks.length ? blocks : [createDocumentBlock()],
    structure_revision: Math.max(1, Number(value?.structure_revision) || 1),
    tags: Array.isArray(value?.tags) ? value.tags.map(String) : [],
    datasource_neutral: value?.datasource_neutral !== false,
    object_references: Array.isArray(value?.object_references)
      ? value.object_references.map((item: any) => ({ ...item }))
      : [],
  }
}

export function defaultKnowledgePayload(type: KnowledgePayload['knowledge_type']): KnowledgePayload {
  if (type === 'BUSINESS') {
    return {
      knowledge_type: 'BUSINESS',
      term: '',
      aliases: [],
      definition: '',
      formula: '',
      constraints: [],
      related_objects: [],
      examples: [],
    }
  }
  if (type === 'EVENT') {
    return {
      knowledge_type: 'EVENT',
      event_name: '',
      display_name: '',
      aliases: [],
      description: '',
      table_name: '',
      event_name_field: '',
      event_time_field: '',
      parameters: [],
    }
  }
  if (type === 'JSON_FIELD') {
    return {
      knowledge_type: 'JSON_FIELD',
      schema_name: '',
      table_name: '',
      source_field: '',
      json_path: '$.',
      field_name: '',
      display_name: '',
      data_type: 'string',
      expression: '',
      aliases: [],
      description: '',
      value_mappings: {},
    }
  }
  return {
    knowledge_type: 'DOCUMENT',
    blocks: [createDocumentBlock()],
    structure_revision: 1,
    tags: [],
    datasource_neutral: false,
    object_references: [],
  }
}

export function serializeKnowledgeDraft(payload: KnowledgePayload): KnowledgePayload {
  if (payload.knowledge_type === 'BUSINESS') {
    return {
      ...payload,
      aliases: [...(payload.aliases || [])],
      constraints: [...(payload.constraints || [])],
      examples: (payload.examples || []).map((item) => ({ ...item })),
    }
  }
  if (payload.knowledge_type === 'EVENT') {
    return {
      ...payload,
      aliases: [...(payload.aliases || [])],
      parameters: (payload.parameters || []).map((item) => ({ ...item })),
    }
  }
  if (payload.knowledge_type === 'JSON_FIELD') {
    return {
      ...payload,
      aliases: [...(payload.aliases || [])],
      value_mappings: { ...(payload.value_mappings || {}) },
      json_path: payload.json_path || '$.',
    }
  }
  return {
    ...normalizeDocumentPayload(payload),
    blocks: normalizeDocumentPayload(payload).blocks.map((block) => ({ ...block })),
  }
}

export function serializeEvent(payload: EventKnowledgePayload): EventKnowledgePayload {
  return serializeKnowledgeDraft(payload) as EventKnowledgePayload
}

export function serializeJsonField(payload: JsonFieldKnowledgePayload): JsonFieldKnowledgePayload {
  return serializeKnowledgeDraft(payload) as JsonFieldKnowledgePayload
}

export function applyParsedUpload(parsedMarkdown: string, _previousMarkdown: string): string {
  return String(parsedMarkdown || '')
}
