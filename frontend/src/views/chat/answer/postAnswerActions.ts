import type { ChatRecord } from '@/api/chat'

export const POST_ANSWER_ACTION_START_RETRY_LIMIT = 8
export const POST_ANSWER_ACTION_RETRY_DELAY_MS = 50

export function hasRecommendedQuestions(value?: string | null): boolean {
  if (!value?.trim()) {
    return false
  }
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) && parsed.length > 0
  } catch {
    return false
  }
}

export function shouldRunPostAnswerActions(record?: Partial<ChatRecord>): boolean {
  if (!record?.id) {
    return false
  }
  if (record.first_chat) {
    return false
  }
  if (!record.finish && !record.finish_time) {
    return false
  }
  if (record.error || record.stopped || record.local_answer) {
    return false
  }
  return !hasRecommendedQuestions(record.recommended_question)
}

export function isPostAnswerActionPending(
  recordId?: number,
  pendingRecordIds: ReadonlySet<number> = new Set()
): boolean {
  return !!recordId && pendingRecordIds.has(recordId)
}

export function shouldRetryPostAnswerActionStart(
  started: boolean,
  attempt: number,
  maxAttempts = POST_ANSWER_ACTION_START_RETRY_LIMIT
): boolean {
  return !started && attempt < maxAttempts
}
