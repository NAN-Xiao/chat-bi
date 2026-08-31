export const REVENUE_OBSERVATION_MIN_DAYS = 1
export const REVENUE_OBSERVATION_MAX_DAYS = 365
export const DEFAULT_REVENUE_OBSERVATION_DAYS = 30

export type RevenueMetricMethod =
  | 'count'
  | 'entity_count'
  | 'per_entity_count'
  | 'period_cumulative_count'
  | 'period_average_count'
  | 'period_cumulative_entity_count'
  | 'period_average_entity_count'
  | 'property_sum'
  | 'property_avg'

export type RevenueMetricConfig = {
  method: RevenueMetricMethod
  field: string
}

export const REVENUE_METRIC_OPTIONS: Array<{ label: string; value: RevenueMetricMethod }> = [
  { label: '总次数', value: 'count' },
  { label: '触发主体数', value: 'entity_count' },
  { label: '人均次数', value: 'per_entity_count' },
  { label: '总次数的周期累计总和', value: 'period_cumulative_count' },
  { label: '总次数的周期累计均值', value: 'period_average_count' },
  { label: '触发主体数的周期累计总和', value: 'period_cumulative_entity_count' },
  { label: '触发主体数的周期累计均值', value: 'period_average_entity_count' },
  { label: '事件属性求和', value: 'property_sum' },
  { label: '事件属性均值', value: 'property_avg' },
]

export function revenueMetricLabel(method: RevenueMetricMethod) {
  return REVENUE_METRIC_OPTIONS.find((option) => option.value === method)?.label || '总次数'
}

export function revenueMetricUsesProperty(method: RevenueMetricMethod) {
  return method === 'property_sum' || method === 'property_avg'
}

export function clampRevenueObservationDays(value: unknown) {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return DEFAULT_REVENUE_OBSERVATION_DAYS
  return Math.min(REVENUE_OBSERVATION_MAX_DAYS, Math.max(REVENUE_OBSERVATION_MIN_DAYS, Math.round(numericValue)))
}
