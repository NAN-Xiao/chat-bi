import { ChartValidationError } from '@/views/chat/component/chartValidation.ts'

export const RADIAL_PERCENTAGE_FIELD = 'shuzhi_radial_percentage'

export type RadialPartitionValidationCode =
  | 'missing_category_field'
  | 'missing_value_field'
  | 'empty_category'
  | 'duplicate_category'
  | 'invalid_value'
  | 'negative_value'
  | 'zero_total'
  | 'too_many_categories'

export class RadialPartitionValidationError extends ChartValidationError {
  constructor(public readonly code: RadialPartitionValidationCode) {
    super(code)
    this.name = 'RadialPartitionValidationError'
  }
}

export interface PreparedRadialSlices {
  data: Array<Record<string, unknown>>
  total: number
}

function parseRadialValue(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }
  if (typeof value !== 'string') {
    return null
  }
  const normalized = value.trim().replace(/,/g, '')
  if (!normalized) {
    return null
  }
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

export function formatRadialPercentage(value: number, total: number): string {
  return Number(((value / total) * 100).toFixed(2)).toString()
}

export function prepareRadialSlices(
  data: Array<Record<string, unknown>>,
  categoryField: string,
  valueField: string,
  maxCategories = 12
): PreparedRadialSlices {
  if (!categoryField) {
    throw new RadialPartitionValidationError('missing_category_field')
  }
  if (!valueField) {
    throw new RadialPartitionValidationError('missing_value_field')
  }
  if (data.length > maxCategories) {
    throw new RadialPartitionValidationError('too_many_categories')
  }

  const categories = new Set<string>()
  const normalized = data.map((row) => {
    if (!(categoryField in row)) {
      throw new RadialPartitionValidationError('missing_category_field')
    }
    if (!(valueField in row)) {
      throw new RadialPartitionValidationError('missing_value_field')
    }

    const category = String(row[categoryField] ?? '').trim()
    if (!category) {
      throw new RadialPartitionValidationError('empty_category')
    }
    if (categories.has(category)) {
      throw new RadialPartitionValidationError('duplicate_category')
    }
    categories.add(category)

    const value = parseRadialValue(row[valueField])
    if (value === null) {
      throw new RadialPartitionValidationError('invalid_value')
    }
    if (value < 0) {
      throw new RadialPartitionValidationError('negative_value')
    }
    return { row, value }
  })

  const total = normalized.reduce((sum, item) => sum + item.value, 0)
  if (total <= 0) {
    throw new RadialPartitionValidationError('zero_total')
  }

  return {
    total,
    data: normalized.map(({ row, value }) => ({
      ...row,
      [valueField]: value,
      [RADIAL_PERCENTAGE_FIELD]: Number(formatRadialPercentage(value, total)),
    })),
  }
}
