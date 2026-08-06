export interface KnowledgeEditorActionState {
  save: boolean
  validate: boolean
  publish: boolean
  archive: boolean
  rollback: boolean
}

const ACTIVE_PUBLISH_STATUSES = new Set(['QUEUED', 'RUNNING', 'PENDING_CONFIRMATION'])

export function knowledgeActionState(input: {
  status?: string | null
  canManage: boolean
  hasDraft: boolean
  publishing?: boolean
  publishJobStatus?: string | null
}): KnowledgeEditorActionState {
  const busy = Boolean(input.publishing) || ACTIVE_PUBLISH_STATUSES.has(input.publishJobStatus || '')
  const editable = input.canManage && input.hasDraft && !busy
  return {
    save: editable,
    validate: editable,
    publish: editable && input.status === 'READY_TO_PUBLISH',
    archive: input.canManage && !busy,
    rollback: input.canManage && !busy,
  }
}
