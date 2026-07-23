export interface DashboardSqlPreviewRequest {
  datasource: number | string
  sql: string
  pivot?: unknown
  title: string
  chartType: string
  chartConfig: Record<string, unknown>
}

export interface DashboardSqlPreviewResult {
  status?: string
  fields?: string[]
  data?: Array<Record<string, unknown>>
  message?: string
  raw?: unknown
}

export type DashboardSqlPreviewExecutor = (
  request: DashboardSqlPreviewRequest
) => Promise<DashboardSqlPreviewResult>

type DefaultDashboardSqlPreviewExecutor = (request: {
  datasource: number | string
  sql: string
  pivot?: unknown
}) => Promise<DashboardSqlPreviewResult>

export function resolveDashboardSqlPreviewExecutor(
  customExecutor: DashboardSqlPreviewExecutor | undefined,
  defaultExecutor: DefaultDashboardSqlPreviewExecutor
): DashboardSqlPreviewExecutor {
  if (customExecutor) return customExecutor
  return ({ datasource, sql, pivot }) => defaultExecutor({ datasource, sql, pivot })
}
