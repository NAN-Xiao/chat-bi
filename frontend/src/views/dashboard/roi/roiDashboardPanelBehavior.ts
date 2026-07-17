import type { RoiChartEditorState, RoiConfig, RoiDashboard } from './types'

export const ROI_DASHBOARD_TREE_REFRESH_EVENT = 'roi-dashboard-tree-refresh'

export type RoiDashboardRouteTarget = {
  path: '/dashboard/index'
  query: { resourceId: string; dashboardMode: 'roi' }
}

type CreateFlowDependencies = {
  ensureConfigLoaded: () => Promise<unknown>
  getConfig: () => RoiConfig | null
  requestDatasource: () => Promise<boolean>
  requestName: () => Promise<string | null>
  createDashboard: (name: string) => Promise<RoiDashboard>
  publishDashboard: (dashboard: RoiDashboard) => void
  navigate: (target: RoiDashboardRouteTarget) => Promise<unknown>
  openEditor: (state: RoiChartEditorState) => void
}

export type RoiPanelLoadReason = 'mounted' | 'route-enter' | 'explicit-config'

export function buildRoiPanelLoadPlan(input: {
  reason: RoiPanelLoadReason
  routeMode: 'roi' | 'ordinary'
  dashboardId: string
}): Array<'config' | 'dashboards' | 'charts'> {
  if (input.reason === 'explicit-config') return ['config']
  if (input.routeMode !== 'roi') return []
  return input.dashboardId ? ['config', 'dashboards', 'charts'] : ['config', 'dashboards']
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
  await dependencies.ensureConfigLoaded()
  if (!dependencies.getConfig() && !(await dependencies.requestDatasource())) return null
  const name = (await dependencies.requestName())?.trim()
  if (!name) return null

  const created = await dependencies.createDashboard(name)
  dependencies.publishDashboard(created)
  await dependencies.navigate({
    path: '/dashboard/index',
    query: { resourceId: String(created.id), dashboardMode: 'roi' },
  })
  if (dependencies.getConfig()?.can_edit) {
    dependencies.openEditor(createFirstChartEditorState(String(created.id)))
  }
  return created
}
