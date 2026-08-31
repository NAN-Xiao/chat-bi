export const INTERVAL_LIMIT_MIN_SECONDS = 60
export const INTERVAL_LIMIT_MAX_SECONDS = 180 * 24 * 60 * 60
export const DEFAULT_INTERVAL_LIMIT_SECONDS = 60 * 60

export type IntervalAnalysisConfig = {
  entityField: string
  startEvent: string
  startEventFilterLogic: 'and' | 'or'
  startEventFilters: Array<Record<string, any>>
  endEvent: string
  endEventFilterLogic: 'and' | 'or'
  endEventFilters: Array<Record<string, any>>
  relatedProperty: {
    enabled: boolean
    startProperty: string
    endProperty: string
  }
  limitSeconds: number
}

export function clampIntervalLimitSeconds(value: unknown) {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return DEFAULT_INTERVAL_LIMIT_SECONDS
  return Math.min(INTERVAL_LIMIT_MAX_SECONDS, Math.max(INTERVAL_LIMIT_MIN_SECONDS, Math.round(numericValue)))
}

export function formatIntervalLimit(seconds: number) {
  const normalized = clampIntervalLimitSeconds(seconds)
  if (normalized % 86400 === 0) return `${normalized / 86400}天`
  if (normalized % 3600 === 0) return `${normalized / 3600}小时`
  if (normalized % 60 === 0) return `${normalized / 60}分钟`
  return `${normalized}秒`
}
