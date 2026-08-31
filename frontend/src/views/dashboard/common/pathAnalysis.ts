export const PATH_EVENT_LIMIT = 30
export const PATH_SESSION_GAP_MIN_SECONDS = 1
export const PATH_SESSION_GAP_MAX_SECONDS = 24 * 60 * 60
export const DEFAULT_PATH_SESSION_GAP_SECONDS = 30 * 60

export type PathAnalysisEvent = {
  id: string
  event: string
  splitProperties: string[]
}

export type PathAnalysisConfig = {
  events: PathAnalysisEvent[]
  initialEvent: string
  sessionGapSeconds: number
}

export function clampPathSessionGapSeconds(value: unknown) {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return DEFAULT_PATH_SESSION_GAP_SECONDS
  return Math.min(PATH_SESSION_GAP_MAX_SECONDS, Math.max(PATH_SESSION_GAP_MIN_SECONDS, Math.round(numericValue)))
}

export function formatPathSessionGap(seconds: number) {
  const normalized = clampPathSessionGapSeconds(seconds)
  if (normalized % 3600 === 0) return `${normalized / 3600}小时`
  if (normalized % 60 === 0) return `${normalized / 60}分钟`
  return `${normalized}秒`
}
