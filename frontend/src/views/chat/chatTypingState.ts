export function shouldMarkRecordTyping({
  recordIndex,
  lastRecordIndex,
  isTyping,
  isUnfinished,
  hasActiveTask,
}: {
  recordIndex: number
  lastRecordIndex: number
  isTyping: boolean
  isUnfinished: boolean
  hasActiveTask: boolean
}): boolean {
  if (!isUnfinished) {
    return false
  }
  return hasActiveTask || (recordIndex === lastRecordIndex && isTyping)
}
