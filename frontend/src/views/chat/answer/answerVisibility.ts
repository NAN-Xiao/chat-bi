export interface FinalAnswerRecordLike {
  finish?: boolean
  finish_time?: unknown
  error?: unknown
  stopped?: boolean
  local_answer?: unknown
  analysis_notice?: unknown
}

export interface FinalAnswerVisibilityInput {
  record?: FinalAnswerRecordLike
  isTyping?: boolean
  finalAnswerReady?: boolean
}

export interface TerminalRecordLike extends FinalAnswerRecordLike {
  task_id?: unknown
}

export function shouldShowTerminalResult({
  record,
  isTyping,
  finalAnswerReady,
}: FinalAnswerVisibilityInput) {
  return !!(record && !isTyping && (record.finish || record.finish_time) && finalAnswerReady)
}

export function partitionTerminalRecordUpdate<T extends TerminalRecordLike>(
  record: T,
  currentTaskId?: unknown
) {
  const content = { ...record } as Record<string, unknown>
  delete content.finish
  delete content.finish_time
  delete content.error
  delete content.stopped
  delete content.local_answer
  delete content.task_id
  content.task_id = currentTaskId
  return {
    content,
    afterData: {
      analysis: content.analysis,
      analysis_notice: content.analysis_notice,
    },
    terminal: {
      finish: record.finish,
      finish_time: record.finish_time,
      error: record.error,
      stopped: record.stopped,
      local_answer: record.local_answer,
    },
  }
}

export function shouldShowFinalAnswer({
  record,
  isTyping,
  finalAnswerReady,
}: FinalAnswerVisibilityInput) {
  if (!record) {
    return false
  }
  if (record.error || record.stopped || record.local_answer || record.analysis_notice) {
    return true
  }
  if (isTyping) {
    return false
  }
  return !!(record.finish || record.finish_time) && !!finalAnswerReady
}
