export type DashboardChartEntry = {
  component?: { id?: unknown } | null
  viewInfo?: unknown
}

export type DashboardRefreshResult = {
  status?: unknown
  error_type?: unknown
  recoverable?: unknown
}

export type DashboardCacheRefreshDisposition =
  | 'permission_denied'
  | 'refresh_database'
  | 'ready'
  | 'failed'
export type DashboardChartRenderState = 'loading' | 'ready' | 'refreshing' | 'stale' | 'failed'
export type DashboardFailureClass = 'none' | 'terminal' | 'transient'

const TRANSIENT_ERROR_TYPES = new Set([
  'dashboard_query_busy',
  'request_timeout',
  'network_error',
  'datasource_connection_failed',
])
const RETRY_DELAYS_MS = [2000, 5000, 15000]

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

export function classifyDashboardChartFailure(result: DashboardRefreshResult): DashboardFailureClass {
  if (result?.status !== 'failed') return 'none'
  const errorType = String(result?.error_type || '')
  if (!TRANSIENT_ERROR_TYPES.has(errorType)) return 'terminal'
  if (errorType === 'datasource_connection_failed' && result?.recoverable !== true) return 'terminal'
  return 'transient'
}

export function nextDashboardChartRetryDelayMs(
  retryIndex: number,
  random: () => number = Math.random
): number | null {
  const base = RETRY_DELAYS_MS[retryIndex]
  if (base === undefined) return null
  const boundedRandom = Math.min(1, Math.max(0, Number(random()) || 0))
  const jitter = (boundedRandom * 0.4) - 0.2
  return Math.round(base * (1 + jitter))
}

export function resolveDashboardChartRenderState(input: {
  phase: 'loading' | 'refreshing'
  failed: boolean
  hasSnapshot: boolean
}): DashboardChartRenderState {
  if (!input.failed) return 'ready'
  return input.hasSnapshot ? 'stale' : 'failed'
}

export function dashboardChartFailureResultFromError(error: unknown): DashboardRefreshResult {
  const candidate = error && typeof error === 'object' ? error as Record<string, unknown> : {}
  const errorType = String(candidate.error_type || candidate.code || '')
  const isTransient = candidate.name === 'TimeoutError'
    || candidate.name === 'TypeError'
    || ['ECONNABORTED', 'ETIMEDOUT', 'ERR_NETWORK'].includes(errorType)
  return {
    status: 'failed',
    error_type: isTransient ? 'network_error' : 'query_failed',
    recoverable: isTransient,
    message: candidate.message,
  } as DashboardRefreshResult
}

export function dashboardCacheRefreshDisposition(
  result: DashboardRefreshResult,
  hasUsableSnapshot: boolean
): DashboardCacheRefreshDisposition {
  if (isPermissionDeniedRefreshResult(result)) {
    return 'permission_denied'
  }
  if (result?.status === 'failed') {
    return result?.error_type === 'dashboard_cache_miss' ? 'refresh_database' : 'failed'
  }
  if (!hasUsableSnapshot) {
    return 'refresh_database'
  }
  return 'ready'
}

export function shouldRetryDashboardChartFailure(
  result: DashboardRefreshResult,
  hasSnapshot: boolean
) {
  return classifyDashboardChartFailure(result) === 'transient' && !hasSnapshot
}

export function shouldKeepDashboardChartPending(
  result: DashboardRefreshResult,
  hasSnapshot: boolean,
  retryCount: number,
  maxRetries: number
) {
  return retryCount < maxRetries && shouldRetryDashboardChartFailure(result, hasSnapshot)
}
