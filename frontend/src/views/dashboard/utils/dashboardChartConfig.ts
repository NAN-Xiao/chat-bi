import {
  dashboardDateParameterTokens,
  scanDashboardDateParameterTokens,
} from './dashboardDateFilter.ts'

export const DASHBOARD_DATE_FILTER_MIGRATION_REQUIRED = 'dashboard_date_filter_migration_required'

export type DashboardDateParameterType = keyof typeof dashboardDateParameterTokens

export type DashboardDateFilterConfig = {
  enabled: boolean
  parameterType: DashboardDateParameterType
  expression: Record<string, unknown>
}

export type DashboardChartConfig = Record<string, any> & {
  configVersion: 2
  dateFilter?: DashboardDateFilterConfig
  pivot?: Record<string, unknown>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isParameterType(value: unknown): value is DashboardDateParameterType {
  return typeof value === 'string' && Object.prototype.hasOwnProperty.call(dashboardDateParameterTokens, value)
}

function hasMatchingTokens(sql: string, parameterType: DashboardDateParameterType): boolean {
  const activeTokens = scanDashboardDateParameterTokens(sql)
  if (activeTokens.length === 0) return false
  const expectedTokens = dashboardDateParameterTokens[parameterType]
  const isCompleteRange = activeTokens.length === expectedTokens.length
    && expectedTokens.every((token) => activeTokens.includes(token))
  const isSingleBoundary = activeTokens.length === 1
    && (expectedTokens as readonly string[]).includes(activeTokens[0])
  return isCompleteRange || isSingleBoundary
}

function hasControlledDateTokens(sql: string): boolean {
  return scanDashboardDateParameterTokens(sql).length > 0
}

function migrationRequired(): never {
  throw new Error(DASHBOARD_DATE_FILTER_MIGRATION_REQUIRED)
}

function normalizeDateFilter(value: unknown, sql: string): DashboardDateFilterConfig {
  if (!isRecord(value)) return migrationRequired()
  const parameterType = value.parameterType
  const expression = value.expression
  if (value.enabled === false
    || !isParameterType(parameterType)
    || !isRecord(expression)
    || !hasMatchingTokens(sql, parameterType)) {
    return migrationRequired()
  }
  return {
    enabled: value.enabled !== false,
    parameterType,
    expression: { ...expression },
  }
}

function legacyDateFilter(pivot: Record<string, unknown>, sql: string): DashboardDateFilterConfig {
  const parameterType = pivot.date_parameter_type
  const expression = pivot.date_expression
  if (!isParameterType(parameterType) || !isRecord(expression) || !hasMatchingTokens(sql, parameterType)) {
    return migrationRequired()
  }
  return {
    enabled: true,
    parameterType,
    expression: { ...expression },
  }
}

export function buildDashboardDateFilterConfig(
  sql: string,
  parameterType: unknown,
  expression: unknown,
  enabled = true
): DashboardDateFilterConfig | undefined {
  if (!hasControlledDateTokens(sql)) return undefined
  return normalizeDateFilter({ enabled, parameterType, expression }, sql)
}

export function normalizeDashboardPivot(pivot: unknown): Record<string, unknown> {
  if (!isRecord(pivot)) return { enabled: false }
  const {
    date_parameter_type: _dateParameterType,
    date_expression: _dateExpression,
    ...nextPivot
  } = pivot
  void _dateParameterType
  void _dateExpression
  return nextPivot
}

export function normalizeDashboardChartConfig(input: Record<string, any>): DashboardChartConfig {
  const sql = String(input.sql || '')
  const pivot = isRecord(input.pivot) ? input.pivot : {}
  const next: DashboardChartConfig = {
    ...input,
    configVersion: 2,
    pivot: normalizeDashboardPivot(pivot),
  }

  if (!hasControlledDateTokens(sql)) {
    delete next.dateFilter
    return next
  }

  if (input.configVersion === 2 || input.dateFilter !== undefined) {
    next.dateFilter = normalizeDateFilter(input.dateFilter, sql)
    return next
  }

  next.dateFilter = legacyDateFilter(pivot, sql)
  return next
}
