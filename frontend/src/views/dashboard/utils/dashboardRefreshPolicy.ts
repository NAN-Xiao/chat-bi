const DEFAULT_SNAPSHOT_MAX_AGE_MS = 3 * 60 * 60 * 1000
const MAX_TIMEOUT_DELAY_MS = 2_147_483_647

export const DASHBOARD_AUTO_REFRESH_MIN_DELAY_MS = 60 * 1000

type DashboardRefreshPolicy = {
  auto_refresh?: boolean
  autoRefresh?: boolean
  snapshot_max_age_hours?: number | string | null
  snapshotMaxAgeHours?: number | string | null
  snapshot_max_age_minutes?: number | string | null
  snapshotMaxAgeMinutes?: number | string | null
}

function finiteNumber(value: unknown) {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : null
}

export function normalizeDashboardRefreshPolicy(policy?: DashboardRefreshPolicy | null) {
  const autoRefreshValue = policy?.auto_refresh ?? policy?.autoRefresh
  const minutesValue = finiteNumber(policy?.snapshot_max_age_minutes ?? policy?.snapshotMaxAgeMinutes)
  const hoursValue = finiteNumber(policy?.snapshot_max_age_hours ?? policy?.snapshotMaxAgeHours)
  const maxAgeMs = minutesValue !== null
    ? minutesValue * 60 * 1000
    : hoursValue !== null
      ? hoursValue * 60 * 60 * 1000
      : DEFAULT_SNAPSHOT_MAX_AGE_MS

  return {
    autoRefresh: autoRefreshValue !== false,
    snapshotMaxAgeMs: Math.max(0, Math.min(maxAgeMs, 30 * 24 * 60 * 60 * 1000)),
  }
}

export function chartSnapshotRefreshedAt(viewInfo: any) {
  const values = [
    viewInfo?.snapshotRefreshedAt,
    viewInfo?.data?.snapshotRefreshedAt,
    viewInfo?.refreshed_at,
    viewInfo?.data?.refreshed_at,
    viewInfo?.sourceConfig?.sql?.lastResult?.refreshed_at,
    viewInfo?.sourceConfig?.sql?.lastResult?.cache_refreshed_at,
  ]
  for (const value of values) {
    const timestamp = finiteNumber(value)
    if (timestamp !== null && timestamp > 0) {
      return timestamp
    }
  }
  return 0
}

export function ensureChartSnapshotRefreshedAt(viewInfo: any, refreshedAt = Date.now()) {
  if (!viewInfo || chartSnapshotRefreshedAt(viewInfo) > 0) {
    return
  }
  if (!viewInfo.data || typeof viewInfo.data !== 'object') {
    viewInfo.data = {}
  }
  viewInfo.snapshotRefreshedAt = refreshedAt
  viewInfo.data.snapshotRefreshedAt = refreshedAt
}

export function chartRefreshDueInMs(
  viewInfo: any,
  policy?: DashboardRefreshPolicy | null,
  now = Date.now()
) {
  const normalized = normalizeDashboardRefreshPolicy(policy)
  if (!normalized.autoRefresh) {
    return null
  }
  const refreshedAt = chartSnapshotRefreshedAt(viewInfo)
  if (refreshedAt <= 0) {
    return 0
  }
  return Math.max(0, refreshedAt + normalized.snapshotMaxAgeMs - now)
}

export function nextDashboardRefreshDelayMs(
  viewInfos: any[],
  policy?: DashboardRefreshPolicy | null,
  now = Date.now(),
  minDelayMs = DASHBOARD_AUTO_REFRESH_MIN_DELAY_MS
) {
  const normalized = normalizeDashboardRefreshPolicy(policy)
  if (!normalized.autoRefresh) {
    return null
  }
  const dueTimes = viewInfos
    .map((viewInfo) => chartRefreshDueInMs(viewInfo, policy, now))
    .filter((value): value is number => value !== null)
  if (!dueTimes.length) {
    return null
  }
  return Math.min(MAX_TIMEOUT_DELAY_MS, Math.max(minDelayMs, Math.min(...dueTimes)))
}
