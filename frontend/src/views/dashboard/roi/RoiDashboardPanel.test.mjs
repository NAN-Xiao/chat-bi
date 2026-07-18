import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import esbuild from 'esbuild'

const currentDir = dirname(fileURLToPath(import.meta.url))
const frontendRoot = resolve(currentDir, '../../../..')
const panelPath = join(currentDir, 'RoiDashboardPanel.vue')
const behaviorPath = join(currentDir, 'roiDashboardPanelBehavior.ts')

assert.equal(existsSync(panelPath), true, '必须提供 ROI 看板主页面')
assert.equal(existsSync(behaviorPath), true, '必须提供可独立验证的新建流程')

const panel = readFileSync(panelPath, 'utf8')
assert.match(panel, /openCreateDashboardNameDialog/)
assert.match(panel, /openFirstChartEditor/)
assert.match(panel, /createRoiNewChartEditorState/)
assert.doesNotMatch(panel, /DashboardSqlEditor\.vue|useDatasourceContextStore/)
assert.doesNotMatch(panel, /RoiDatasourceDialog|openDatasourceSettings|设置数据源/)
assert.match(panel, /请联系 SaaS 管理员配置 ROI 数据源/)

const build = await esbuild.build({
  entryPoints: [behaviorPath],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: frontendRoot,
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const {
  buildRoiPanelLoadPlan,
  canEditRoiConfig,
  createRoiConfigLoadCoordinator,
  createFirstChartEditorState,
  createRoiNewChartEditorState,
  refreshRoiChartsWithConfig,
  runRoiDashboardCreateFlow,
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
  buildRoiPanelLoadPlan({ reason: 'mounted', routeMode: 'ordinary', dashboardId: '301' }),
  [],
  '普通路由隐藏 Panel 挂载时不得请求任何 ROI API'
)
assert.deepEqual(
  buildRoiPanelLoadPlan({ reason: 'mounted', routeMode: 'roi', dashboardId: '301' }),
  ['config', 'dashboards', 'charts'],
  'ROI 路由挂载必须加载完整页面合同'
)
assert.deepEqual(
  buildRoiPanelLoadPlan({ reason: 'route-enter', routeMode: 'roi', dashboardId: '301' }),
  ['config', 'dashboards', 'charts'],
  'ordinary→roi 必须补齐 config/list/charts，不能只刷新图表'
)
assert.deepEqual(
  buildRoiPanelLoadPlan({ reason: 'explicit-config', routeMode: 'ordinary', dashboardId: '' }),
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
  const firstLoad = coordinator.ensure()
  const createLoad = coordinator.ensure()
  assert.equal(apiCalls, 1, '并发新建流程必须共享同一个配置请求')
  request.resolve()
  await Promise.all([firstLoad, createLoad])
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
assert.match(panel, /createRoiNewChartEditorState\([\s\S]*config\.value/)
assert.match(
  panel,
  /onBeforeUnmount\([\s\S]*roiConfigLoadCoordinator\.invalidate\(\)[\s\S]*roiDashboardStore\.reset\(\)/
)

{
  const calls = []
  const created = await runRoiDashboardCreateFlow({
    ensureConfigLoaded: async () => calls.push('config'),
    getConfig: () => null,
    onMissingConfig: () => calls.push('missing'),
    onForbiddenConfig: () => calls.push('forbidden'),
    requestName: async () => {
      calls.push('name')
      return '空看板'
    },
    createDashboard: async (name) => {
      calls.push('create')
      return { id: '901', name }
    },
    publishDashboard: () => calls.push('publish'),
    navigate: async () => calls.push('navigate'),
    openEditor: () => calls.push('editor'),
  })
  assert.equal(created, null)
  assert.deepEqual(calls, ['config', 'missing'])
}

{
  const calls = []
  let published = null
  let route = null
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
  const created = await runRoiDashboardCreateFlow({
    ensureConfigLoaded: async () => calls.push('config'),
    getConfig: () => config,
    onMissingConfig: () => calls.push('missing'),
    onForbiddenConfig: () => calls.push('forbidden'),
    requestName: async () => {
      calls.push('name')
      return '经营总览'
    },
    createDashboard: async (name) => {
      calls.push(`create:${name}`)
      return { id: '9223372036854775807', name }
    },
    publishDashboard: (dashboard) => {
      calls.push('publish')
      published = dashboard
    },
    navigate: async (target) => {
      calls.push('navigate')
      route = target
    },
    openEditor: (state) => {
      calls.push('editor')
      editor = state
    },
  })

  assert.equal(created.id, '9223372036854775807')
  assert.deepEqual(calls, [
    'config',
    'name',
    'create:经营总览',
    'publish',
    'navigate',
    'editor',
  ])
  assert.equal(published.id, '9223372036854775807')
  assert.deepEqual(route, {
    path: '/dashboard/index',
    query: { resourceId: '9223372036854775807', dashboardMode: 'roi' },
  })
  assert.deepEqual(editor, createFirstChartEditorState('9223372036854775807'))
}

{
  const calls = []
  const result = await runRoiDashboardCreateFlow({
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
    onMissingConfig: () => calls.push('missing'),
    onForbiddenConfig: () => calls.push('forbidden'),
    requestName: async () => {
      calls.push('name')
      return '空看板'
    },
    createDashboard: async (name) => {
      calls.push('create')
      return { id: '901', name }
    },
    publishDashboard: () => calls.push('publish'),
    navigate: async () => calls.push('navigate'),
    openEditor: () => calls.push('editor'),
  })
  assert.equal(result, null, '无数据源权限不得创建空看板')
  assert.deepEqual(calls, ['config', 'forbidden'])
}

assert.match(panel, /canEditRoiConfig\(config\.value\)/)
assert.match(panel, /当前账号无此数据源权限/)
assert.doesNotMatch(panel, /currentCharts\.value\.some\(\(chart\)\s*=>\s*chart\.can_execute/)
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
