type DashboardViewInfo = Record<string, any>
type DashboardViewInfoMap = Record<string, DashboardViewInfo>

function finitePositiveNumber(value: unknown) {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) && numberValue > 0 ? numberValue : 0
}

function snapshotRefreshedAt(viewInfo: DashboardViewInfo) {
  return finitePositiveNumber(
    viewInfo?.snapshotRefreshedAt ??
      viewInfo?.data?.snapshotRefreshedAt ??
      viewInfo?.refreshed_at ??
      viewInfo?.data?.refreshed_at
  )
}

function normalizeChartResultArrays(viewInfo: DashboardViewInfo) {
  if (!viewInfo.data || typeof viewInfo.data !== 'object') {
    viewInfo.data = {}
  }
  viewInfo.data.data = Array.isArray(viewInfo.data.data) ? viewInfo.data.data : []
  viewInfo.data.fields = Array.isArray(viewInfo.data.fields) ? viewInfo.data.fields : []
  viewInfo.fields = Array.isArray(viewInfo.fields) ? viewInfo.fields : viewInfo.data.fields
}

export function hasDashboardChartSnapshot(viewInfo: DashboardViewInfo) {
  const rows = viewInfo?.data?.data
  if (Array.isArray(rows) && rows.length > 0) {
    return true
  }
  return (
    snapshotRefreshedAt(viewInfo) > 0 &&
    viewInfo?.status === 'success' &&
    viewInfo?.dataState === 'ready'
  )
}

export function prepareDashboardChartRefreshState(
  viewInfo: DashboardViewInfo,
  refreshState: 'waiting' | 'loading' = 'waiting'
) {
  if (!viewInfo || typeof viewInfo !== 'object') {
    return false
  }
  normalizeChartResultArrays(viewInfo)
  viewInfo.message = ''
  if (hasDashboardChartSnapshot(viewInfo)) {
    viewInfo.status = 'success'
    viewInfo.dataState = 'ready'
    viewInfo.loadingProgress = 100
    viewInfo.refreshState = ''
    return true
  }
  viewInfo.status = 'loading'
  viewInfo.dataState = 'loading'
  viewInfo.loadingProgress = 0
  viewInfo.refreshState = refreshState
  return false
}

export function reconcileDashboardViewInfo(
  target: DashboardViewInfoMap,
  incoming: DashboardViewInfoMap
) {
  const next = incoming && typeof incoming === 'object' ? incoming : {}
  Object.keys(target).forEach((key) => {
    if (!Object.prototype.hasOwnProperty.call(next, key)) {
      delete target[key]
    }
  })
  Object.entries(next).forEach(([key, value]) => {
    const current = target[key]
    if (
      current &&
      typeof current === 'object' &&
      !Array.isArray(current) &&
      value &&
      typeof value === 'object' &&
      !Array.isArray(value)
    ) {
      Object.keys(current).forEach((currentKey) => {
        if (!Object.prototype.hasOwnProperty.call(value, currentKey)) {
          delete current[currentKey]
        }
      })
      Object.assign(current, value)
      return
    }
    target[key] = value
  })
  return target
}
