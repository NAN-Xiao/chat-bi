export interface DashboardSqlFieldMapping {
  columns: string[]
  x: string
  y: string[]
  series: string
}

export type StrictFieldMappingIssue = 'columns' | 'x' | 'y' | 'series'

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))]
}

export function reconcileDashboardSqlFieldMapping(
  mapping: DashboardSqlFieldMapping,
  fields: string[],
  data: Array<Record<string, unknown>>,
  strict: boolean
): DashboardSqlFieldMapping {
  const availableFields = unique(fields)
  const available = new Set(availableFields)
  const reconciled: DashboardSqlFieldMapping = {
    columns: unique(mapping.columns).filter((field) => available.has(field)),
    x: available.has(mapping.x) ? mapping.x : '',
    y: unique(mapping.y).filter((field) => available.has(field)),
    series: available.has(mapping.series) ? mapping.series : '',
  }
  if (strict || availableFields.length === 0) return reconciled

  if (reconciled.columns.length === 0) {
    reconciled.columns = availableFields.slice(0, 8)
  }
  if (!reconciled.x) {
    reconciled.x = availableFields[0] || ''
  }
  if (reconciled.y.length === 0) {
    const numericField = availableFields.find((field) =>
      data.some((row) => typeof row?.[field] === 'number')
    )
    reconciled.y = [
      numericField || availableFields[Math.min(1, availableFields.length - 1)] || availableFields[0],
    ].filter(Boolean)
  }
  return reconciled
}

export function resolveDashboardSqlTableColumns(
  columns: string[],
  fields: string[],
  strict: boolean
): string[] {
  return columns.length || strict ? [...columns] : [...fields]
}

export function getStrictFieldMappingIssue(
  chartType: string,
  mapping: DashboardSqlFieldMapping
): StrictFieldMappingIssue | null {
  if (chartType === 'table') return mapping.columns.length ? null : 'columns'
  if (chartType === 'metric') return mapping.y.length ? null : 'y'
  if (chartType === 'pie') {
    if (!mapping.y.length) return 'y'
    return mapping.series || mapping.x ? null : 'series'
  }
  if (!mapping.x) return 'x'
  if (!mapping.y.length) return 'y'
  if (['heatmap', 'sankey'].includes(chartType) && !mapping.series) return 'series'
  return null
}
