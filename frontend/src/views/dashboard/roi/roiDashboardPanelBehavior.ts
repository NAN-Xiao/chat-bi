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

type RoiConfigLoadDependencies = {
  load: () => Promise<unknown>
  isLoaded: () => boolean
}

export function createRoiConfigLoadCoordinator(dependencies: RoiConfigLoadDependencies) {
  let generation = 0
  let inFlight: Promise<void> | null = null

  const run = (force: boolean) => {
    if (!force && dependencies.isLoaded()) return Promise.resolve()
    if (inFlight) return inFlight

    const requestGeneration = generation
    const request = (async () => {
      await dependencies.load()
      if (requestGeneration !== generation || !dependencies.isLoaded()) {
        throw new Error('ROI config load invalidated')
      }
    })()
    const tracked = request.finally(() => {
      if (inFlight === tracked) inFlight = null
    })
    inFlight = tracked
    return tracked
  }

  return {
    ensure: () => run(false),
    refresh: () => run(true),
    invalidate: () => {
      generation += 1
      inFlight = null
    },
  }
}

export async function refreshRoiChartsWithConfig(dependencies: {
  loadCharts: () => Promise<unknown>
  refreshConfig: () => Promise<unknown>
}) {
  await dependencies.loadCharts()
  await dependencies.refreshConfig()
}

export const canEditRoiConfig = (config: Pick<RoiConfig, 'can_edit'> | null) =>
  config?.can_edit === true

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

export function createRoiNewChartEditorState(
  config: Pick<RoiConfig, 'can_edit'> | null,
  dashboardId: string,
  firstChart: boolean
): RoiChartEditorState | null {
  if (!canEditRoiConfig(config)) return null
  return {
    ...createFirstChartEditorState(dashboardId),
    firstChart,
  }
}

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
  const editorState = createRoiNewChartEditorState(
    dependencies.getConfig(),
    String(created.id),
    true
  )
  if (editorState) dependencies.openEditor(editorState)
  return created
}
