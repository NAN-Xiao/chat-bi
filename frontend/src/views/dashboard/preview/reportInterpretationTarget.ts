import type { ReportInterpretationTarget } from '@/api/analysisAssistant'

interface ReportChartEntry {
  component?: { id?: unknown }
  viewInfo?: any
}

function currentRows(entry: ReportChartEntry, snapshots: Record<string, any>): any[] {
  const componentId = `${entry.component?.id ?? ''}`.trim()
  const snapshot = componentId ? snapshots?.[componentId] : null
  if (snapshot && Array.isArray(snapshot.data)) {
    return snapshot.data
  }
  return Array.isArray(entry.viewInfo?.data?.data) ? entry.viewInfo.data.data : []
}

function isPermissionDenied(entry: ReportChartEntry): boolean {
  const viewInfo = entry.viewInfo || {}
  const status = viewInfo.status || viewInfo.data?.status
  const errorType = viewInfo.error_type || viewInfo.data?.error_type
  return status === 'failed' && errorType === 'permission_denied'
}

export function buildReportInterpretationTarget(
  dashboardId: unknown,
  entries: ReportChartEntry[],
  snapshots: Record<string, any> = {}
): ReportInterpretationTarget {
  const componentIds = Array.from(
    new Set(
      entries
        .map((entry) => `${entry.component?.id ?? ''}`.trim())
        .filter((componentId) => componentId !== '')
    )
  )
  return {
    dashboard_id: `${dashboardId ?? ''}`.trim(),
    component_ids: componentIds,
    has_visible_data: entries.some((entry) => currentRows(entry, snapshots).length > 0),
    has_permission_denied: entries.some(isPermissionDenied),
  }
}
