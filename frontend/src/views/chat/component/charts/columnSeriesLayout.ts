export type ColumnSeriesLayout = 'stacked' | 'grouped'

export type ColumnSeriesTransform = {
  type: 'stackY' | 'dodgeX'
}

export function resolveColumnSeriesTransform(
  layout: ColumnSeriesLayout,
  hasSeries: boolean
): ColumnSeriesTransform[] | undefined {
  if (!hasSeries) return undefined
  return [{ type: layout === 'grouped' ? 'dodgeX' : 'stackY' }]
}
