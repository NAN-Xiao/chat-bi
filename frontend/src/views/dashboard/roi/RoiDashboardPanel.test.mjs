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
const { createFirstChartEditorState, runRoiDashboardCreateFlow, closeRoiChartEditor } =
  await import(moduleUrl)

{
  const calls = []
  let published = null
  let route = null
  let editor = null
  const created = await runRoiDashboardCreateFlow({
    config: null,
    requestDatasource: async () => {
      calls.push('datasource')
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
    config: null,
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
  const state = createFirstChartEditorState('9001')
  const closed = closeRoiChartEditor(state)
  assert.equal(closed.visible, false)
  assert.equal(closed.dashboardId, '9001', '取消首次编辑必须保留已创建看板引用')
  assert.equal('removeDashboard' in closed, false, '关闭编辑器不得隐式删除空看板')
}

console.log('ROI dashboard panel tests passed')
