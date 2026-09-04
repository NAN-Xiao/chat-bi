export type AttributionMethod = 'first' | 'last' | 'linear'
export type AttributionWindowUnit = 'day' | 'hour' | 'minute'

export type AttributionWindowMode = 'same_day' | 'duration'

export type AttributionWindowConfig = {
  mode: AttributionWindowMode
  value: number
  unit: AttributionWindowUnit
}

export const ATTRIBUTION_EVENT_LIMIT = 30
export const ATTRIBUTION_WINDOW_MAX_SECONDS = 365 * 24 * 60 * 60
export const DEFAULT_ATTRIBUTION_WINDOW: AttributionWindowConfig = {
  mode: 'same_day',
  value: 1,
  unit: 'day',
}

const UNIT_SECONDS: Record<AttributionWindowUnit, number> = {
  day: 24 * 60 * 60,
  hour: 60 * 60,
  minute: 60,
}

export function maxAttributionWindowValue(unit: AttributionWindowUnit) {
  return Math.floor(ATTRIBUTION_WINDOW_MAX_SECONDS / UNIT_SECONDS[unit])
}

export function isValidAttributionWindow(value: unknown): value is AttributionWindowConfig {
  if (!value || typeof value !== 'object') return false
  const config = value as Partial<AttributionWindowConfig>
  if (config.mode === 'same_day') return true
  // Migrate the pre-mode shape that stored custom windows as mode="custom".
  if ((config.mode !== 'duration' && config.mode !== ('custom' as AttributionWindowMode))
    || !config.unit
    || !(config.unit in UNIT_SECONDS)) return false
  const numericValue = Number(config.value)
  return Number.isInteger(numericValue)
    && numericValue >= 1
    && numericValue <= maxAttributionWindowValue(config.unit)
}

export function normalizeAttributionWindow(value: unknown): AttributionWindowConfig {
  if (!isValidAttributionWindow(value)) return { ...DEFAULT_ATTRIBUTION_WINDOW }
  if (value.mode === 'same_day') return { mode: 'same_day', value: 1, unit: 'day' }
  return {
    mode: 'duration',
    value: Number(value.value),
    unit: value.unit,
  }
}
