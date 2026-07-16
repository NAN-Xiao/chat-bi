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
  publishCurrentTreeBranch,
  shouldInitializeOrdinaryDashboardCanvas,
} = await import(moduleUrl)

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
assert.equal(shouldInitializeOrdinaryDashboardCanvas('preview', 'roi'), false)
assert.equal(shouldInitializeOrdinaryDashboardCanvas('preview', 'my'), true)

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
