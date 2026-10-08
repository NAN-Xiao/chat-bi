export type FunnelWindowMode = 'same_day' | 'duration'
export type FunnelWindowUnit = 'day' | 'hour' | 'minute'

export type FunnelWindowConfig = {
  mode: FunnelWindowMode
  value: number
  unit: FunnelWindowUnit
}

export const FUNNEL_WINDOW_MAX_SECONDS = 365 * 24 * 60 * 60
export const DEFAULT_FUNNEL_WINDOW: FunnelWindowConfig = {
  mode: 'duration',
  value: 1,
  unit: 'day',
}

const UNIT_SECONDS: Record<FunnelWindowUnit, number> = {
  day: 24 * 60 * 60,
  hour: 60 * 60,
  minute: 60,
}

const UNIT_LABELS: Record<FunnelWindowUnit, string> = {
  day: '天',
  hour: '小时',
  minute: '分钟',
}

export function maxFunnelWindowValue(unit: FunnelWindowUnit) {
  return Math.floor(FUNNEL_WINDOW_MAX_SECONDS / UNIT_SECONDS[unit])
}

export function isValidFunnelWindow(value: unknown): value is FunnelWindowConfig {
  if (!value || typeof value !== 'object') return false
  const config = value as Partial<FunnelWindowConfig>
  if (config.mode === 'same_day') return true
  if (config.mode !== 'duration' || !config.unit || !(config.unit in UNIT_SECONDS)) return false
  const numericValue = config.value
  return typeof numericValue === 'number' && Number.isInteger(numericValue)
    && numericValue >= 1
    && numericValue <= maxFunnelWindowValue(config.unit)
}

export function parseStoredFunnelWindow(value: unknown, legacyWindowDays?: unknown): {
  value: FunnelWindowConfig | null; issue: string | null
} {
  if (isValidFunnelWindow(value)) {
    return { value: value.mode === 'same_day'
      ? { mode: 'same_day', value: 1, unit: 'day' }
      : { mode: 'duration', value: value.value, unit: value.unit }, issue: null }
  }
  // A present invalid current configuration must never be overridden by legacy data.
  if (value === undefined && typeof legacyWindowDays === 'number'
    && Number.isInteger(legacyWindowDays) && legacyWindowDays >= 1 && legacyWindowDays <= 365) {
    return { value: { mode: 'duration', value: legacyWindowDays, unit: 'day' }, issue: null }
  }
  return { value: null, issue: '漏斗分析窗口期配置无效，请重新设置。' }
}

export function normalizeFunnelWindow(value: unknown, legacyWindowDays?: unknown): FunnelWindowConfig | null {
  return parseStoredFunnelWindow(value, legacyWindowDays).value
}

export function formatFunnelWindow(value: unknown) {
  const normalized = normalizeFunnelWindow(value)
  if (!normalized) return '窗口配置无效'
  if (normalized.mode === 'same_day') return '当天'
  return `${normalized.value}${UNIT_LABELS[normalized.unit]}`
}
