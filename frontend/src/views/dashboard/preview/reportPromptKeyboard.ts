export interface ReportPromptKeyboardEvent {
  key?: string
  keyCode?: number
  isComposing?: boolean
  shiftKey?: boolean
  ctrlKey?: boolean
  altKey?: boolean
  metaKey?: boolean
}

export function shouldSubmitReportPromptOnEnter(event: ReportPromptKeyboardEvent): boolean {
  return (
    event.key === 'Enter' &&
    !event.isComposing &&
    event.keyCode !== 229 &&
    !event.shiftKey &&
    !event.ctrlKey &&
    !event.altKey &&
    !event.metaKey
  )
}
