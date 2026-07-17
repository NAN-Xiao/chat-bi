import assert from 'node:assert/strict'
import esbuild from 'esbuild'
import { existsSync } from 'node:fs'

assert.equal(
  existsSync('src/views/dashboard/roi/roiLandingRedirectCoordinator.ts'),
  true,
  '必须提供 ROI landing 最新代次协调器'
)

const build = await esbuild.build({
  entryPoints: ['src/views/dashboard/roi/roiLandingRedirectCoordinator.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})

const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const { createRoiLandingRedirectCoordinator } = await import(moduleUrl)

const deferred = () => {
  let resolve
  const promise = new Promise((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}
const snapshot = (tenantId, resourceId, mode = 'roi', canAccessRoi = false) => ({
  tenantId,
  resourceId,
  mode,
  canAccessRoi,
})

{
  const coordinator = createRoiLandingRedirectCoordinator()
  const tenantA = deferred()
  const tenantB = deferred()
  const commits = []
  let current = snapshot('tenant-a', 'roi-1')
  const pendingA = coordinator.redirect({
    snapshot: current,
    getCurrentSnapshot: () => current,
    resolveLanding: () => tenantA.promise,
    commit: (target) => commits.push(target),
  })
  current = snapshot('tenant-b', 'roi-1')
  const pendingB = coordinator.redirect({
    snapshot: current,
    getCurrentSnapshot: () => current,
    resolveLanding: () => tenantB.promise,
    commit: (target) => commits.push(target),
  })
  tenantA.resolve('landing-a')
  await pendingA
  assert.deepEqual(commits, [], 'tenant A 的旧 landing 不得覆盖 tenant B')
  assert.equal(coordinator.isResolving(), true, '旧请求 finally 不得清除 tenant B 的 resolving')
  tenantB.resolve('landing-b')
  await pendingB
  assert.deepEqual(commits, ['landing-b'])
  assert.equal(coordinator.isResolving(), false)
}

{
  const coordinator = createRoiLandingRedirectCoordinator()
  const roiA = deferred()
  const roiB = deferred()
  const commits = []
  let current = snapshot('tenant-a', 'roi-a')
  const pendingA = coordinator.redirect({
    snapshot: current,
    getCurrentSnapshot: () => current,
    resolveLanding: () => roiA.promise,
    commit: (target) => commits.push(target),
  })
  current = snapshot('tenant-a', 'roi-b')
  const pendingB = coordinator.redirect({
    snapshot: current,
    getCurrentSnapshot: () => current,
    resolveLanding: () => roiB.promise,
    commit: (target) => commits.push(target),
  })
  roiB.resolve('landing-b')
  await pendingB
  roiA.resolve('landing-a')
  await pendingA
  assert.deepEqual(commits, ['landing-b'], 'ROI id A 的旧结果不得覆盖 B')
}

{
  const coordinator = createRoiLandingRedirectCoordinator()
  const roiLanding = deferred()
  const commits = []
  let current = snapshot('tenant-a', 'roi-a')
  const pending = coordinator.redirect({
    snapshot: current,
    getCurrentSnapshot: () => current,
    resolveLanding: () => roiLanding.promise,
    commit: (target) => commits.push(target),
  })
  current = snapshot('tenant-a', 'my-dashboard', 'my')
  coordinator.invalidate()
  roiLanding.resolve('stale-roi-landing')
  await pending
  assert.deepEqual(commits, [], '离开 ROI 后旧 landing 不得 replace 合法路由')
  assert.equal(coordinator.isResolving(), false)
}

console.log('ROI landing redirect coordinator tests passed')
