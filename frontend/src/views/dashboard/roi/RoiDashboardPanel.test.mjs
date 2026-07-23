import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import esbuild from 'esbuild'

const panelPath = 'src/views/dashboard/roi/RoiDashboardPanel.vue'
const behaviorPath = 'src/views/dashboard/roi/roiDashboardPanelBehavior.ts'

assert.equal(existsSync(panelPath), true, '必须提供 ROI 看板主页面')
assert.equal(existsSync(behaviorPath), true, '必须提供可独立验证的新建流程')

const panel = readFileSync(panelPath, 'utf8')
assert.doesNotMatch(panel, /openCreateDashboardNameDialog|requestName|新建下属看板/)
assert.match(panel, /openNewChartEditor/)
assert.match(panel, /runRoiEnsureChartFlow/)
assert.doesNotMatch(panel, /DashboardSqlEditor\.vue|useDatasourceContextStore/)
assert.doesNotMatch(panel, /RoiDatasourceDialog|openDatasourceSettings|设置数据源/)
assert.match(panel, /请联系 SaaS 管理员配置 ROI 数据源/)
assert.match(panel, /添加图表/)

const build = await esbuild.build({
  entryPoints: [behaviorPath],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const {
  buildRoiPanelLoadPlan,
  canEditRoiConfig,
  createRoiConfigLoadCoordinator,
  createFirstChartEditorState,
  createRoiNewChartEditorState,
  refreshRoiChartsWithConfig,
  runRoiEnsureChartFlow,
  closeRoiChartEditor,
} =
  await import(moduleUrl)

const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

assert.deepEqual(
  buildRoiPanelLoadPlan({ reason: 'mounted', routeMode: 'ordinary' }),
  [],
  '普通路由隐藏 Panel 挂载时不得请求任何 ROI API'
)
assert.deepEqual(
  buildRoiPanelLoadPlan({ reason: 'mounted', routeMode: 'roi' }),
  ['config', 'dashboard'],
  'ROI 路由挂载必须加载配置和唯一看板'
)
assert.deepEqual(
  buildRoiPanelLoadPlan({ reason: 'route-enter', routeMode: 'roi' }),
  ['config', 'dashboard'],
  'ordinary→roi 必须补齐配置和唯一看板'
)
assert.deepEqual(
  buildRoiPanelLoadPlan({ reason: 'explicit-config', routeMode: 'ordinary' }),
  ['config'],
  '普通路由只有显式 ROI 动作才允许懒加载配置'
)
assert.match(panel, /buildRoiPanelLoadPlan/)
assert.match(panel, /reason:\s*'mounted'/)
assert.match(panel, /loadPage\('route-enter'\)/)

{
  let loaded = false
  let apiCalls = 0
  const request = deferred()
  const coordinator = createRoiConfigLoadCoordinator({
    load: async () => {
      apiCalls += 1
      await request.promise
      loaded = true
    },
    isLoaded: () => loaded,
  })
  const configLoad = coordinator.ensure()
  const createLoad = coordinator.ensure()
  assert.equal(apiCalls, 1, '配置读取与新建流程必须共享同一个配置请求')
  request.resolve()
  await Promise.all([configLoad, createLoad])
  assert.equal(loaded, true)
}

{
  let loaded = false
  let apiCalls = 0
  const requests = [deferred(), deferred()]
  const coordinator = createRoiConfigLoadCoordinator({
    load: async () => {
      const request = requests[apiCalls]
      apiCalls += 1
      await request.promise
      loaded = true
    },
    isLoaded: () => loaded,
  })
  const first = coordinator.ensure()
  const shared = coordinator.ensure()
  requests[0].reject(new Error('load failed'))
  const failed = await Promise.allSettled([first, shared])
  assert.deepEqual(failed.map((item) => item.status), ['rejected', 'rejected'])
  assert.equal(apiCalls, 1, '共享失败不得产生第二个交错请求')

  const retry = coordinator.ensure()
  assert.equal(apiCalls, 2, '失败清理后必须允许下一次动作重试')
  requests[1].resolve()
  await retry
  assert.equal(loaded, true)
}

{
  let loaded = false
  const requests = [deferred(), deferred()]
  let apiCalls = 0
  const coordinator = createRoiConfigLoadCoordinator({
    load: async () => {
      const request = requests[apiCalls]
      apiCalls += 1
      await request.promise
    },
    isLoaded: () => loaded,
  })
  const stale = coordinator.ensure()
  coordinator.invalidate()
  const current = coordinator.ensure()
  requests[0].resolve()
  await assert.rejects(stale, /invalidated/)
  assert.equal(loaded, false, '旧代次完成不得恢复已重置的配置状态')
  loaded = true
  requests[1].resolve()
  await current
  assert.equal(apiCalls, 2)
}

for (const chartCount of [0, 1]) {
  let config = { can_execute: true, can_edit: true }
  const calls = []
  await refreshRoiChartsWithConfig({
    loadCharts: async () => calls.push(`charts:${chartCount}`),
    refreshConfig: async () => {
      calls.push('config')
      config = { can_execute: false, can_edit: false }
    },
  })
  assert.deepEqual(calls, [`charts:${chartCount}`, 'config'])
  assert.equal(canEditRoiConfig(config), false, '动态撤权后空看板和已有图表都必须禁用编辑')
  assert.equal(
    createRoiNewChartEditorState(config, '901', chartCount === 0),
    null,
    '动态撤权后不得生成新增或首图编辑器状态'
  )
}
assert.match(panel, /refreshRoiChartsWithConfig/)
assert.match(panel, /roiConfigLoadCoordinator\.refresh/)
assert.match(panel, /canEditRoiConfig\(config\.value\)/)
assert.match(panel, /runRoiEnsureChartFlow\([\s\S]*getDashboard:\s*\(\) => dashboard\.value/)
assert.match(
  panel,
  /onBeforeUnmount\([\s\S]*roiConfigLoadCoordinator\.invalidate\(\)[\s\S]*roiDashboardStore\.reset\(\)/
)

{
  const calls = []
  let editor = null
  const config = {
    id: '1',
    tenant_id: '11',
    datasource_id: 101,
    datasource_name: 'ROI 数据源',
    version: 1,
    can_execute: true,
    can_edit: true,
  }
  const created = await runRoiEnsureChartFlow({
    ensureConfigLoaded: async () => calls.push('config'),
    getConfig: () => config,
    getDashboard: () => null,
    onMissingConfig: () => calls.push('missing'),
    onForbiddenConfig: () => calls.push('forbidden'),
    ensureDashboard: async () => {
      calls.push('ensure')
      return { id: '9223372036854775807', name: 'ROI 看板' }
    },
    firstChart: true,
    openEditor: (state) => {
      calls.push('editor')
      editor = state
    },
  })

  assert.equal(created.id, '9223372036854775807')
  assert.deepEqual(calls, ['config', 'ensure', 'editor'])
  assert.deepEqual(editor, createFirstChartEditorState('9223372036854775807'))
}

{
  const calls = []
  const result = await runRoiEnsureChartFlow({
    ensureConfigLoaded: async () => calls.push('config'),
    getConfig: () => null,
    getDashboard: () => null,
    onMissingConfig: () => calls.push('missing'),
    onForbiddenConfig: () => calls.push('forbidden'),
    ensureDashboard: async () => calls.push('ensure'),
    firstChart: true,
    openEditor: () => calls.push('editor'),
  })
  assert.equal(result, null)
  assert.deepEqual(calls, ['config', 'missing'])
}

{
  const calls = []
  const result = await runRoiEnsureChartFlow({
    ensureConfigLoaded: async () => calls.push('config'),
    getConfig: () => ({
      id: '1',
      tenant_id: '11',
      datasource_id: 101,
      datasource_name: '无权数据源',
      version: 1,
      can_execute: false,
      can_edit: false,
    }),
    getDashboard: () => null,
    onMissingConfig: () => calls.push('missing'),
    onForbiddenConfig: () => calls.push('forbidden'),
    ensureDashboard: async () => calls.push('ensure'),
    firstChart: true,
    openEditor: () => calls.push('editor'),
  })
  assert.equal(result, null, '无数据源权限不得创建空看板')
  assert.deepEqual(calls, ['config', 'forbidden'])
}

{
  const calls = []
  const existing = { id: '901', name: 'ROI 看板' }
  const result = await runRoiEnsureChartFlow({
    ensureConfigLoaded: async () => calls.push('config'),
    getConfig: () => ({ can_execute: true, can_edit: true }),
    getDashboard: () => existing,
    onMissingConfig: () => calls.push('missing'),
    onForbiddenConfig: () => calls.push('forbidden'),
    ensureDashboard: async () => calls.push('ensure'),
    firstChart: false,
    openEditor: (state) => calls.push(`editor:${state.dashboardId}:${state.firstChart}`),
  })
  assert.equal(result, existing)
  assert.deepEqual(calls, ['config', 'editor:901:false'])
}

assert.match(panel, /canEditRoiConfig\(config\.value\)/)
assert.match(panel, /当前账号无此数据源权限/)
assert.doesNotMatch(panel, /currentCharts\.value\.some\(\(chart\)\s*=>\s*chart\.can_execute/)
assert.doesNotMatch(panel, /defineProps|props\.dashboardId|createDashboardRequestId/)
assert.match(panel, /:dashboard-id="editorState\.dashboardId"/)
assert.match(panel, /@saved="handleChartSaved"/)
assert.match(panel, /@cancelled="cancelChartEditor"/)
assert.doesNotMatch(panel, /@update:model-value=/, '关闭只由 cancelled 事件处理，避免重复清理编辑器状态')
assert.match(panel, /watch\(\s*routeMode,[\s\S]*?loadPage\('route-enter'\)/)
assert.match(panel, /WORKSPACE_CONTEXT_CHANGE_EVENT/)
assert.match(
  panel,
  /name:\s*WORKSPACE_CONTEXT_CHANGE_EVENT,[\s\S]*?event\?\.phase === 'changing'[\s\S]*?roiConfigLoadCoordinator\.invalidate\(\)[\s\S]*?event\?\.phase === 'changed'[\s\S]*?loadPage\('route-enter'\)/
)
assert.match(panel, /\.roi-dashboard-panel__identity[\s\S]*span[\s\S]*min-width:\s*0/)
assert.match(panel, /\.roi-dashboard-panel__identity[\s\S]*span[\s\S]*overflow:\s*hidden/)
assert.match(panel, /\.roi-dashboard-panel__identity[\s\S]*span[\s\S]*text-overflow:\s*ellipsis/)
assert.match(panel, /\.roi-dashboard-panel__identity[\s\S]*span[\s\S]*white-space:\s*nowrap/)

{
  const state = createFirstChartEditorState('9001')
  const closed = closeRoiChartEditor(state)
  assert.equal(closed.visible, false)
  assert.equal(closed.dashboardId, '9001', '取消首次编辑必须保留已创建看板引用')
  assert.equal('removeDashboard' in closed, false, '关闭编辑器不得隐式删除空看板')
}

console.log('ROI dashboard panel tests passed')
