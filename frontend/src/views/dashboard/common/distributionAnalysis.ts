export type DistributionIntervalMode = 'auto' | 'discrete' | 'custom'

export type DistributionIntervalConfig = {
  mode: DistributionIntervalMode
  customBounds: number[]
}

export type DistributionMetricKind = 'count' | 'days' | 'hours' | 'property'

export type DistributionPropertyAggregation =
  | 'sum'
  | 'avg'
  | 'median'
  | 'max'
  | 'min'
  | 'count_distinct'
  | 'variance'
  | 'stddev'
  | 'percentile_99'
  | 'percentile_95'
  | 'percentile_90'
  | 'percentile_80'
  | 'percentile_75'
  | 'percentile_70'
  | 'percentile_60'
  | 'percentile_40'
  | 'percentile_30'
  | 'percentile_25'
  | 'percentile_20'
  | 'percentile_10'
  | 'percentile_05'

export type DistributionMetricConfig = {
  kind: DistributionMetricKind
  field: string
  aggregation: DistributionPropertyAggregation
}
