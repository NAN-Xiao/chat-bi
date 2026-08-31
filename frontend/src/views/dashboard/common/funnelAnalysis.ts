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
  const numericValue = Number(config.value)
  return Number.isInteger(numericValue)
    && numericValue >= 1
    && numericValue <= maxFunnelWindowValue(config.unit)
}

export function normalizeFunnelWindow(value: unknown, legacyWindowDays?: unknown): FunnelWindowConfig {
  if (isValidFunnelWindow(value)) {
    if (value.mode === 'same_day') return { mode: 'same_day', value: 1, unit: 'day' }
    return { mode: 'duration', value: Number(value.value), unit: value.unit }
  }

  // Known legacy migration: older dashboard configs stored only a 1-365 day value.
  const legacyDays = Number(legacyWindowDays)
  if (Number.isFinite(legacyDays)) {
    return {
      mode: 'duration',
      value: Math.min(365, Math.max(1, Math.trunc(legacyDays))),
      unit: 'day',
    }
  }

  return { ...DEFAULT_FUNNEL_WINDOW }
}

export function formatFunnelWindow(value: FunnelWindowConfig) {
  const normalized = normalizeFunnelWindow(value)
  if (normalized.mode === 'same_day') return '当天'
  return `${normalized.value}${UNIT_LABELS[normalized.unit]}`
}
