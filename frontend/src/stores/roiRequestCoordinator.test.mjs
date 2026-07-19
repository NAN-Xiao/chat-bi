import assert from 'node:assert/strict'
import esbuild from 'esbuild'
import { existsSync } from 'node:fs'

assert.equal(
  existsSync('src/stores/roiRequestCoordinator.ts'),
  true,
  '必须提供无 Pinia 依赖的 ROI 请求协调器'
)

const build = await esbuild.build({
  entryPoints: ['src/stores/roiRequestCoordinator.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})

const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const {
  beginRoiRequest,
  createRoiRequestState,
  finishRoiRequest,
  getRoiPermissionError,
  isLatestRoiRequest,
  isRoiRequestLoading,
  resetRoiRequests,
  setRoiPermissionError,
} = await import(moduleUrl)

const state = createRoiRequestState()
const configRequest = beginRoiRequest(state, 'config')
const dashboardRequest = beginRoiRequest(state, 'dashboards')
assert.equal(isRoiRequestLoading(state), true)
finishRoiRequest(state, configRequest)
assert.equal(isRoiRequestLoading(state), true, '其他当前代次请求未完成时 loading 必须保持')
finishRoiRequest(state, dashboardRequest)
assert.equal(isRoiRequestLoading(state), false)

const configDenied = beginRoiRequest(state, 'config')
setRoiPermissionError(state, configDenied, 'config forbidden')
finishRoiRequest(state, configDenied)
const chartsRequest = beginRoiRequest(state, 'charts:dashboard-1', 'charts')
assert.equal(getRoiPermissionError(state), 'config forbidden', 'charts 开始不能清除 config 权限错误')
setRoiPermissionError(state, chartsRequest, 'charts forbidden')
finishRoiRequest(state, chartsRequest)
const configRetry = beginRoiRequest(state, 'config')
assert.equal(getRoiPermissionError(state), 'charts forbidden', 'config 重试只能清理自己的权限错误')
finishRoiRequest(state, configRetry)

const oldRequest = beginRoiRequest(state, 'dashboards')
resetRoiRequests(state)
assert.equal(isLatestRoiRequest(state, oldRequest), false)
assert.equal(setRoiPermissionError(state, oldRequest, 'stale forbidden'), false)
assert.equal(finishRoiRequest(state, oldRequest), false)
assert.equal(isRoiRequestLoading(state), false)
assert.equal(getRoiPermissionError(state), '')

const nextWorkspaceRequest = beginRoiRequest(state, 'dashboards')
assert.equal(isLatestRoiRequest(state, oldRequest), false)
assert.equal(isLatestRoiRequest(state, nextWorkspaceRequest), true)
finishRoiRequest(state, nextWorkspaceRequest)

const firstCharts = beginRoiRequest(state, 'charts:dashboard-1', 'charts')
const secondCharts = beginRoiRequest(state, 'charts:dashboard-1', 'charts')
assert.equal(isLatestRoiRequest(state, firstCharts), false)
assert.equal(isLatestRoiRequest(state, secondCharts), true)
finishRoiRequest(state, secondCharts)
assert.equal(isRoiRequestLoading(state), true, '同操作旧请求仍未完成时 loading 不能提前结束')
finishRoiRequest(state, firstCharts)
assert.equal(isRoiRequestLoading(state), false)

console.log('ROI request coordinator tests passed')
