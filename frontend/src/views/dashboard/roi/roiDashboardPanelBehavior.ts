import type { RoiChartEditorState, RoiConfig, RoiDashboard } from './types'

export const ROI_DASHBOARD_TREE_REFRESH_EVENT = 'roi-dashboard-tree-refresh'

export type RoiDashboardRouteTarget = {
  path: '/dashboard/index'
  query: { resourceId: string; dashboardMode: 'roi' }
}

type CreateFlowDependencies = {
  config: RoiConfig | null
  requestDatasource: () => Promise<boolean>
  requestName: () => Promise<string | null>
  createDashboard: (name: string) => Promise<RoiDashboard>
  publishDashboard: (dashboard: RoiDashboard) => void
  navigate: (target: RoiDashboardRouteTarget) => Promise<unknown>
  openEditor: (state: RoiChartEditorState) => void
}

export const createFirstChartEditorState = (dashboardId: string): RoiChartEditorState => ({
  visible: true,
  mode: 'create',
  dashboardId,
  chartId: null,
  initialValue: null,
  firstChart: true,
})

export const closeRoiChartEditor = (state: RoiChartEditorState): RoiChartEditorState => ({
  ...state,
  visible: false,
})

export async function runRoiDashboardCreateFlow(dependencies: CreateFlowDependencies) {
  if (!dependencies.config && !(await dependencies.requestDatasource())) return null
  const name = (await dependencies.requestName())?.trim()
  if (!name) return null

  const created = await dependencies.createDashboard(name)
  dependencies.publishDashboard(created)
  await dependencies.navigate({
    path: '/dashboard/index',
    query: { resourceId: String(created.id), dashboardMode: 'roi' },
  })
  dependencies.openEditor(createFirstChartEditorState(String(created.id)))
  return created
}
