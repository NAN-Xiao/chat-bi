import type { RawData, S2DataConfig, TableSheet } from '@antv/s2'

export const EMPTY_FILTER_VALUE = 'empty:'

export type TableFilterKey = string

export type TableFilterOption = {
  key: TableFilterKey
  label: string
  count: number
  isEmpty: boolean
}

export type TableFilters = Map<string, Set<TableFilterKey>>

type TableRow = RawData

export function normalizeTableFilterValue(value: unknown): TableFilterKey {
  if (value === null || value === undefined || value === '') {
    return EMPTY_FILTER_VALUE
  }

  if (value instanceof Date) {
    return `date:${value.toISOString()}`
  }

  const valueType = typeof value
  if (valueType === 'object') {
    return `object:${JSON.stringify(value)}`
  }

  return `${valueType}:${String(value)}`
}

export function collectTableFilterOptions(rows: TableRow[], field: string): TableFilterOption[] {
  const options = new Map<TableFilterKey, TableFilterOption>()

  rows.forEach((row) => {
    const value = row[field]
    const key = normalizeTableFilterValue(value)
    const existing = options.get(key)
    if (existing) {
      existing.count += 1
      return
    }

    const isEmpty = key === EMPTY_FILTER_VALUE
    options.set(key, {
      key,
      label: isEmpty ? '（空值）' : String(value),
      count: 1,
      isEmpty,
    })
  })

  return Array.from(options.values())
}

export function searchTableFilterOptions(
  options: TableFilterOption[],
  keyword: string,
  limit = 200
): TableFilterOption[] {
  const normalizedKeyword = keyword.trim().toLocaleLowerCase()
  const matchedOptions = normalizedKeyword
    ? options.filter((option) => option.label.toLocaleLowerCase().includes(normalizedKeyword))
    : options

  return matchedOptions.slice(0, Math.max(limit, 0))
}

export function applyTableFilters<T extends TableRow>(rows: T[], filters: TableFilters): T[] {
  if (filters.size === 0) {
    return [...rows]
  }

  return rows.filter((row) =>
    Array.from(filters.entries()).every(([field, selectedValues]) =>
      selectedValues.has(normalizeTableFilterValue(row[field]))
    )
  )
}

export async function refreshFilteredTableData<T extends TableRow>(
  table: Pick<TableSheet, 'setDataCfg' | 'render'>,
  dataConfig: S2DataConfig,
  sourceData: T[],
  filters: TableFilters
): Promise<T[]> {
  const filteredData = applyTableFilters(sourceData, filters)
  table.setDataCfg({ ...dataConfig, data: filteredData })
  await table.render(true)
  return filteredData
}
