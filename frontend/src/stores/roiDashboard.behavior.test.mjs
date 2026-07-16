import assert from 'node:assert/strict'
import esbuild from 'esbuild'

globalThis.__roiDashboardApi = {}

const build = await esbuild.build({
  stdin: {
    contents: `
      import { createPinia, setActivePinia } from 'pinia'
      import { useRoiDashboardStore } from '@/stores/roiDashboard'
      export const createStore = () => {
        setActivePinia(createPinia())
        return useRoiDashboardStore()
      }
    `,
    resolveDir: process.cwd(),
    sourcefile: 'roiDashboardStoreTestEntry.ts',
  },
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
  alias: { '@': './src' },
  plugins: [
    {
      name: 'roi-dashboard-api-test-double',
      setup(buildApi) {
        buildApi.onResolve({ filter: /^@\/api\/roiDashboard$/ }, () => ({
          path: 'roi-dashboard-api',
          namespace: 'test-double',
        }))
        buildApi.onLoad({ filter: /.*/, namespace: 'test-double' }, () => ({
          contents: `
            export const roiCustomErrorRequestConfig = { requestOptions: { customError: true } }
            export const roiDashboardApi = globalThis.__roiDashboardApi
          `,
          loader: 'js',
        }))
      },
    },
  ],
})

const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const { createStore } = await import(moduleUrl)

const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}
const forbidden = () => ({ response: { status: 403 } })

{
  const config = deferred()
  const dashboards = deferred()
  globalThis.__roiDashboardApi.getConfig = (requestConfig) => {
    assert.equal(requestConfig.requestOptions.customError, true)
    return config.promise
  }
  globalThis.__roiDashboardApi.list = (requestConfig) => {
    assert.equal(requestConfig.requestOptions.customError, true)
    return dashboards.promise
  }
  const store = createStore()
  const configPending = store.loadConfig()
  const dashboardsPending = store.loadDashboards()
  config.resolve(null)
  await configPending
  assert.equal(store.loading, true, '并发看板请求未完成时 loading 必须保持')
  dashboards.resolve([])
  await dashboardsPending
  assert.equal(store.loading, false)
}

{
  const store = createStore()
  globalThis.__roiDashboardApi.getConfig = () => Promise.reject(forbidden())
  await assert.rejects(store.loadConfig())
  assert.equal(store.permissionError, '没有管理 ROI 看板的权限')

  const charts = deferred()
  globalThis.__roiDashboardApi.listCharts = () => charts.promise
  const chartsPending = store.loadCharts('dashboard-1')
  assert.equal(store.permissionError, '没有管理 ROI 看板的权限')
  charts.reject(forbidden())
  await assert.rejects(chartsPending)
  assert.equal(store.permissionError, '没有执行 ROI 图表的权限')

  const config = deferred()
  globalThis.__roiDashboardApi.getConfig = () => config.promise
  const configPending = store.loadConfig()
  assert.equal(store.permissionError, '没有执行 ROI 图表的权限')
  config.resolve(null)
  await configPending
}

{
  const store = createStore()
  const dashboards = deferred()
  globalThis.__roiDashboardApi.list = () => dashboards.promise
  const pending = store.loadDashboards()
  store.reset()
  dashboards.resolve([{ id: 'stale' }])
  await pending
  assert.deepEqual(store.dashboards, [])
  assert.equal(store.loading, false)
  assert.equal(store.permissionError, '')

  const charts = deferred()
  globalThis.__roiDashboardApi.listCharts = () => charts.promise
  const chartsPending = store.loadCharts('dashboard-1')
  store.reset()
  charts.reject(forbidden())
  await assert.rejects(chartsPending)
  assert.deepEqual(store.charts, {})
  assert.equal(store.loading, false)
  assert.equal(store.permissionError, '')
}

{
  const store = createStore()
  const first = deferred()
  const second = deferred()
  const requests = [first, second]
  globalThis.__roiDashboardApi.list = () => requests.shift().promise
  const firstPending = store.loadDashboards()
  const secondPending = store.loadDashboards()
  second.resolve([{ id: 'new' }])
  await secondPending
  assert.deepEqual(store.dashboards, [{ id: 'new' }])
  assert.equal(store.loading, true)
  first.resolve([{ id: 'old' }])
  await firstPending
  assert.deepEqual(store.dashboards, [{ id: 'new' }])
  assert.equal(store.loading, false)
}

{
  const store = createStore()
  assert.equal(store.editorState.createDashboardRequestId, 0)
  store.requestDashboardCreation()
  store.requestDashboardCreation()
  assert.equal(store.editorState.createDashboardRequestId, 2, '树菜单新建请求必须可重复触发')

  store.publishDashboard({ id: '9223372036854775807', name: '经营总览' })
  store.publishCharts('9223372036854775807', [{ id: '9223372036854775806' }])
  assert.equal(store.dashboards[0].id, '9223372036854775807', '看板 Snowflake ID 不得转成 number')
  assert.equal(store.charts['9223372036854775807'][0].id, '9223372036854775806')

  store.reset()
  assert.equal(store.editorState.createDashboardRequestId, 0)
  assert.deepEqual(store.dashboards, [])
  assert.deepEqual(store.charts, {})
}

console.log('ROI dashboard store behavior tests passed')
