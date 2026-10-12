import type { InjectionKey } from 'vue'

type Payload = Record<string, any>
export type DashboardChartSnapshotRefresher = (payload: Payload) => Promise<any>
export const DASHBOARD_CHART_SNAPSHOT_REFRESHER: InjectionKey<DashboardChartSnapshotRefresher> = Symbol('dashboard-chart-snapshot-refresher')

export async function queryDashboardChartWithPersistence(
  payload: Payload,
  forceRefresh: boolean,
  preview: (payload: Payload, forceRefresh: boolean) => Promise<any>,
  persistRefresh: DashboardChartSnapshotRefresher | undefined,
  chartId: string,
  applyDateFilter = false
) {
  if (!forceRefresh || !persistRefresh) return preview(payload, forceRefresh)
  const result = await persistRefresh({ ...payload, chart_id: chartId, apply_date_filter: applyDateFilter })
  if (result?.status === 'success' && result?.snapshot_saved !== true) {
    throw new Error('刷新结果未保存，请重新刷新')
  }
  return result
}

export function hasSavedDashboardChartSnapshot(viewInfo: Payload): boolean {
  return viewInfo?.snapshotContext?.version === 1
    && Boolean(viewInfo.snapshotContext.fingerprint)
    && viewInfo.status === 'success' && viewInfo.dataState === 'ready'
    && Array.isArray(viewInfo.data?.data)
}

export function applySavedDashboardSnapshotMetadata(viewInfo: Payload, result: Payload): void {
  if (result?.snapshot_saved !== true) return
  viewInfo.snapshotContext = result.snapshot_context
  if (viewInfo.data && typeof viewInfo.data === 'object') {
    delete viewInfo.data.source_data
    delete viewInfo.data.source_fields
  }
}
