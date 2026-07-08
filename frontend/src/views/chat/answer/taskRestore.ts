import type { ChatRecord } from '@/api/chat'

type RestorableRecord = Pick<
  ChatRecord,
  | 'id'
  | 'finish'
  | 'finish_time'
  | 'error'
  | 'stopped'
  | 'local_answer'
  | 'chart'
  | 'analysis'
  | 'predict'
  | 'predict_content'
  | 'task_id'
  | 'first_chat'
  | 'question'
>

export function hasStoredFinalAnswer(record?: RestorableRecord) {
  return !!(
    record?.finish ||
    record?.finish_time ||
    record?.error ||
    record?.stopped ||
    record?.local_answer
  )
}

export function hasDisplayableAnswerRecord(record?: RestorableRecord) {
  return !!(
    record?.local_answer ||
    record?.chart ||
    record?.analysis ||
    record?.predict ||
    record?.predict_content
  )
}

export function isRestorableAnswerRecord(record?: RestorableRecord, isLatestRecord = true) {
  if (!record || record.first_chat || hasStoredFinalAnswer(record)) {
    return false
  }
  if (record.task_id) {
    return true
  }
  if (!isLatestRecord) {
    return false
  }
  return !!record.id || !hasDisplayableAnswerRecord(record)
}

export function shouldUseRememberedTask(record?: RestorableRecord) {
  return !!record && !hasStoredFinalAnswer(record)
}

export function shouldLookupRecordTask(record?: RestorableRecord) {
  return !!record?.id && !hasStoredFinalAnswer(record)
}

export function shouldRefreshRecordAfterNoActiveTask(record?: RestorableRecord) {
  return !!record?.id && !hasStoredFinalAnswer(record)
}

export function shouldRestoreWhenAnswerRecordChanges(
  previousRecord?: RestorableRecord,
  nextRecord?: RestorableRecord,
  isLatestRecord = true
) {
  return previousRecord !== nextRecord && isRestorableAnswerRecord(nextRecord, isLatestRecord)
}

export function shouldMarkChatTypingOnRestore(records?: RestorableRecord[]) {
  if (!records?.length) {
    return false
  }
  const latestRecord = records[records.length - 1]
  return isRestorableAnswerRecord(latestRecord, true)
}
