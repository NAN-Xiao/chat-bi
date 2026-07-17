import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import esbuild from 'esbuild'

const panelPath = 'src/views/dashboard/roi/RoiDashboardPanel.vue'
const behaviorPath = 'src/views/dashboard/roi/roiDashboardPanelBehavior.ts'

assert.equal(existsSync(panelPath), true, '必须提供 ROI 看板主页面')
assert.equal(existsSync(behaviorPath), true, '必须提供可独立验证的新建流程')

const panel = readFileSync(panelPath, 'utf8')
assert.match(panel, /ensureRoiDatasourceBeforeCreate/)
assert.match(panel, /openCreateDashboardNameDialog/)
assert.match(panel, /openFirstChartEditor/)
assert.match(panel, /editorState\.value\s*=\s*\{[\s\S]*mode:\s*'create'/)
assert.doesNotMatch(panel, /DashboardSqlEditor\.vue|useDatasourceContextStore/)

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
  createFirstChartEditorState,
  runRoiDashboardCreateFlow,
  closeRoiChartEditor,
} =
  await import(moduleUrl)

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
  const calls = []
  let published = null
  let route = null
  let editor = null
  let config = null
  const created = await runRoiDashboardCreateFlow({
    ensureConfigLoaded: async () => calls.push('config'),
    getConfig: () => config,
    requestDatasource: async () => {
      calls.push('datasource')
      config = {
        id: '1',
        tenant_id: '11',
        datasource_id: 101,
        datasource_name: 'ROI 数据源',
        version: 1,
        can_execute: true,
        can_edit: true,
      }
      return true
    },
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
    'datasource',
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
  let created = false
  const result = await runRoiDashboardCreateFlow({
    ensureConfigLoaded: async () => {},
    getConfig: () => null,
    requestDatasource: async () => false,
    requestName: async () => '不应请求',
    createDashboard: async () => {
      created = true
    },
    publishDashboard: () => {},
    navigate: async () => {},
    openEditor: () => {},
  })
  assert.equal(result, null)
  assert.equal(created, false, '取消数据源设置不得创建空看板')
}

{
  let editorOpened = false
  const result = await runRoiDashboardCreateFlow({
    ensureConfigLoaded: async () => {},
    getConfig: () => ({
      id: '1',
      tenant_id: '11',
      datasource_id: 101,
      datasource_name: '无权数据源',
      version: 1,
      can_execute: false,
      can_edit: false,
    }),
    requestDatasource: async () => true,
    requestName: async () => '空看板',
    createDashboard: async (name) => ({ id: '901', name }),
    publishDashboard: () => {},
    navigate: async () => {},
    openEditor: () => {
      editorOpened = true
    },
  })
  assert.equal(result.id, '901', '无数据源权限仍可创建并导航到空看板')
  assert.equal(editorOpened, false, 'config.can_edit=false 时不得打开首图编辑器')
}

assert.match(panel, /config\.value\?\.can_edit/)
assert.match(panel, /当前账号无此数据源权限/)
assert.doesNotMatch(panel, /currentCharts\.value\.some\(\(chart\)\s*=>\s*chart\.can_execute/)
assert.match(
  panel,
  /const datasourceDialogVisible = computed\([\s\S]*datasourceDialogOpen\.value[\s\S]*configLoaded\.value/
)
assert.match(panel, /:model-value="datasourceDialogVisible"/)
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
