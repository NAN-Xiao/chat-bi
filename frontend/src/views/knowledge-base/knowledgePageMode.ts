import type { KnowledgeBaseCapabilities } from '@/api/knowledgeBase'

export type KnowledgePageMode = KnowledgeBaseCapabilities['management_mode']

export interface KnowledgePageNotice {
  titleKey: string
  descriptionKey: string
  readonly: boolean
}

export function resolveKnowledgePageMode(
  capabilities:
    | (Pick<KnowledgeBaseCapabilities, 'management_mode'> &
        Partial<Pick<KnowledgeBaseCapabilities, 'v2_write_enabled'>>)
    | null
    | undefined
): KnowledgePageMode {
  const mode = capabilities?.management_mode
  if (mode === 'V2' && capabilities?.v2_write_enabled === false) return 'MAINTENANCE'
  if (mode === 'UPGRADING' || mode === 'V2' || mode === 'MAINTENANCE') return mode
  return 'LEGACY'
}

export function isKnowledgeV2Mode(mode: KnowledgePageMode): mode is 'V2' {
  return mode === 'V2'
}

export function knowledgePageNotice(mode: Exclude<KnowledgePageMode, 'LEGACY' | 'V2'>): KnowledgePageNotice {
  if (mode === 'UPGRADING') {
    return {
      titleKey: 'knowledge_base.mode_upgrading_title',
      descriptionKey: 'knowledge_base.mode_upgrading_description',
      readonly: true,
    }
  }
  return {
    titleKey: 'knowledge_base.mode_maintenance_title',
    descriptionKey: 'knowledge_base.mode_maintenance_description',
    readonly: true,
  }
}
