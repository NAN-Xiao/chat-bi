export type PivotGroupValueMode = 'all' | 'custom'

export type PivotGroupValueConfig = {
  group_value_mode?: unknown
  group_values?: unknown
}

export function normalizePivotGroupValueMode(
  config?: PivotGroupValueConfig | null
): PivotGroupValueMode {
  if (config?.group_value_mode === 'all' || config?.group_value_mode === 'custom') {
    return config.group_value_mode
  }
  return Array.isArray(config?.group_values) && config.group_values.length > 0 ? 'custom' : 'all'
}

export function buildPersistedPivotGroupValueSelection(
  mode: PivotGroupValueMode,
  values: string[]
): { group_value_mode: PivotGroupValueMode; group_values: string[] } {
  return {
    group_value_mode: mode,
    group_values: mode === 'all' ? [] : [...values],
  }
}

export function shouldConstrainPivotGroupValues(config?: PivotGroupValueConfig | null) {
  return normalizePivotGroupValueMode(config) === 'custom'
}
