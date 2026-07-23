import type { RoiChartEditorState, RoiConfig, RoiDashboard } from './types'

type EnsureChartFlowDependencies = {
  ensureConfigLoaded: () => Promise<unknown>
  getConfig: () => RoiConfig | null
  getDashboard: () => RoiDashboard | null
  onMissingConfig: () => void
  onForbiddenConfig: () => void
  ensureDashboard: () => Promise<RoiDashboard>
  firstChart: boolean
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
}): Array<'config' | 'dashboard'> {
  if (input.reason === 'explicit-config') return ['config']
  if (input.routeMode !== 'roi') return []
  return ['config', 'dashboard']
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

export async function runRoiEnsureChartFlow(dependencies: EnsureChartFlowDependencies) {
  await dependencies.ensureConfigLoaded()
  const config = dependencies.getConfig()
  if (!config) {
    dependencies.onMissingConfig()
    return null
  }
  if (!canEditRoiConfig(config)) {
    dependencies.onForbiddenConfig()
    return null
  }
  const dashboard = dependencies.getDashboard() || (await dependencies.ensureDashboard())
  const editorState = createRoiNewChartEditorState(
    config,
    String(dashboard.id),
    dependencies.firstChart
  )
  if (editorState) dependencies.openEditor(editorState)
  return dashboard
}
