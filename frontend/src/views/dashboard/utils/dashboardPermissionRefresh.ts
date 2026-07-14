export type DashboardChartEntry = {
  component?: { id?: unknown } | null
  viewInfo?: unknown
}

export type DashboardRefreshResult = {
  status?: unknown
  error_type?: unknown
}

export type DashboardCacheRefreshDisposition = 'permission_denied' | 'refresh_database' | 'ready'

function chartEntryId(entry: DashboardChartEntry) {
  const id = entry?.component?.id
  return id === undefined || id === null ? '' : String(id)
}

export function createPermissionDeniedChartRegistry() {
  const deniedChartIds = new Set<string>()

  return {
    mark(entry: DashboardChartEntry) {
      const id = chartEntryId(entry)
      if (id) deniedChartIds.add(id)
    },
    has(entry: DashboardChartEntry) {
      const id = chartEntryId(entry)
      return Boolean(id && deniedChartIds.has(id))
    },
    reset() {
      deniedChartIds.clear()
    },
  }
}

export function isPermissionDeniedRefreshResult(result: DashboardRefreshResult) {
  return result?.status === 'failed' && result?.error_type === 'permission_denied'
}

export function dashboardCacheRefreshDisposition(
  result: DashboardRefreshResult,
  hasUsableSnapshot: boolean
): DashboardCacheRefreshDisposition {
  if (isPermissionDeniedRefreshResult(result)) {
    return 'permission_denied'
  }
  if (result?.status === 'failed' || !hasUsableSnapshot) {
    return 'refresh_database'
  }
  return 'ready'
}

export function shouldRetryDashboardChartFailure(
  result: DashboardRefreshResult,
  hasSnapshot: boolean
) {
  return result?.status === 'failed' && !isPermissionDeniedRefreshResult(result) && !hasSnapshot
}
