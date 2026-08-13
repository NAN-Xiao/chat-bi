export function shouldMarkRecordTyping({
  recordIndex,
  lastRecordIndex,
  isTyping,
  isUnfinished,
}: {
  recordIndex: number
  lastRecordIndex: number
  isTyping: boolean
  isUnfinished: boolean
}): boolean {
  return recordIndex === lastRecordIndex && isTyping && isUnfinished
}
