import assert from 'node:assert/strict'
import esbuild from 'esbuild'
import { existsSync } from 'node:fs'

assert.equal(
  existsSync('src/views/dashboard/roi/roiNavigationBehavior.ts'),
  true,
  '必须提供可独立验证的 ROI 导航行为'
)

const build = await esbuild.build({
  entryPoints: ['src/views/dashboard/roi/roiNavigationBehavior.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})

const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const {
  createDashboardNodeClickPlan,
  canAccessRoiDashboard,
  publishCurrentTreeBranch,
  resolveRoiPreviewAccessPlan,
  createRoiEntryRouteQuery,
  shouldResetOrdinaryDashboardStore,
  shouldInitializeOrdinaryDashboardCanvas,
} = await import(moduleUrl)

assert.equal(typeof resolveRoiPreviewAccessPlan, 'function', '必须提供 ROI 直达权限计划')
assert.equal(typeof shouldResetOrdinaryDashboardStore, 'function', '必须提供普通 store 重置判断')
assert.equal(typeof createRoiEntryRouteQuery, 'function', '必须提供固定 ROI 入口路由构造函数')

for (const role of ['owner', 'admin']) {
  assert.deepEqual(resolveRoiPreviewAccessPlan('roi', canAccessRoiDashboard({ getTenantRole: role })), {
    shortCircuitOrdinaryDashboard: true,
    renderRoiDashboard: true,
    redirectToLanding: false,
  })
}
for (const userState of [
  { getTenantRole: 'member' },
  { getTenantRole: 'owner', isPlatformWorkspaceDelegate: true },
  { getTenantRole: 'owner', isSystemAdminUser: true },
]) {
  assert.deepEqual(resolveRoiPreviewAccessPlan('roi', canAccessRoiDashboard(userState)), {
    shortCircuitOrdinaryDashboard: true,
    renderRoiDashboard: false,
    redirectToLanding: true,
  })
}
assert.deepEqual(resolveRoiPreviewAccessPlan('my', canAccessRoiDashboard({ getTenantRole: 'member' })), {
  shortCircuitOrdinaryDashboard: false,
  renderRoiDashboard: false,
  redirectToLanding: false,
})

assert.deepEqual(createDashboardNodeClickPlan('roi'), {
  resetOrdinaryDashboardSelection: false,
  syncRoute: true,
  emitNodeClick: true,
})
assert.deepEqual(createDashboardNodeClickPlan('my'), {
  resetOrdinaryDashboardSelection: true,
  syncRoute: true,
  emitNodeClick: true,
})
assert.equal(shouldResetOrdinaryDashboardStore('default'), true)
assert.equal(shouldResetOrdinaryDashboardStore('my'), true)
assert.equal(shouldResetOrdinaryDashboardStore('roi'), false)
assert.equal(shouldInitializeOrdinaryDashboardCanvas('preview', 'roi'), false)
assert.equal(shouldInitializeOrdinaryDashboardCanvas('preview', 'my'), true)

assert.deepEqual(
  createRoiEntryRouteQuery({ resourceId: 'old', dashboardId: 'old', dashboardMode: 'my', tab: 'x' }),
  { dashboardMode: 'roi', tab: 'x' },
  '固定 ROI 入口必须移除资源 ID，并保留无关查询参数'
)

const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

for (const outcome of ['success', 'failure']) {
  const request = deferred()
  let current = true
  const published = []
  const completed = []
  const pending = publishCurrentTreeBranch({
    request: request.promise,
    isCurrent: () => current,
    publish: (nodes) => published.push(nodes),
    complete: () => completed.push(true),
  })
  current = false
  if (outcome === 'success') request.resolve([{ id: 'stale' }])
  else request.reject(new Error('stale failure'))
  await pending
  assert.deepEqual(published, [], `旧代次${outcome}不得发布树节点`)
  assert.deepEqual(completed, [], `旧代次${outcome}不得完成当前树分支`)
}

const currentRequest = deferred()
const published = []
let completed = 0
const pending = publishCurrentTreeBranch({
  request: currentRequest.promise,
  isCurrent: () => true,
  publish: (nodes) => published.push(nodes),
  complete: () => {
    completed += 1
  },
})
currentRequest.resolve([{ id: 'current' }])
await pending
assert.deepEqual(published, [[{ id: 'current' }]])
assert.equal(completed, 1)

console.log('ROI navigation behavior tests passed')
