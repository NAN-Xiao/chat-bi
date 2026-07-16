import assert from 'node:assert/strict'
import esbuild from 'esbuild'

const build = await esbuild.build({
  entryPoints: ['src/views/dashboard/roi/roiLandingRedirectCoordinator.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})

const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const { createRoiLandingRedirectCoordinator, runRoiLandingRedirect } = await import(moduleUrl)

assert.equal(typeof runRoiLandingRedirect, 'function', '必须提供生产使用的 rejection 消费 runner')

const snapshot = (resourceId) => ({
  tenantId: 'tenant-a',
  resourceId,
  mode: 'roi',
  canAccessRoi: false,
})
const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

for (const failureStage of ['resolve', 'commit']) {
  const coordinator = createRoiLandingRedirectCoordinator()
  const errors = []
  const commits = []
  const current = snapshot(`roi-${failureStage}`)
  const expectedError = new Error(`${failureStage} failed: connection detail`)
  const task = () =>
    coordinator.redirect({
      snapshot: current,
      getCurrentSnapshot: () => current,
      resolveLanding: () =>
        failureStage === 'resolve' ? Promise.reject(expectedError) : Promise.resolve('landing'),
      commit: async (target) => {
        if (failureStage === 'commit') throw expectedError
        commits.push(target)
      },
    })

  await assert.doesNotReject(
    runRoiLandingRedirect(task, (error) => errors.push(error)),
    `${failureStage} 拒绝必须由 runner 消费`
  )
  assert.deepEqual(errors, [expectedError])
  assert.equal(coordinator.isResolving(), false)
  assert.deepEqual(commits, [], 'resolve 或 commit 失败均不得产生成功提交')
}

{
  const coordinator = createRoiLandingRedirectCoordinator()
  const oldLanding = deferred()
  const newLanding = deferred()
  const errors = []
  const commits = []
  let current = snapshot('roi-old')
  const oldSnapshot = current
  const oldPending = runRoiLandingRedirect(
    () =>
      coordinator.redirect({
        snapshot: oldSnapshot,
        getCurrentSnapshot: () => current,
        resolveLanding: () => oldLanding.promise,
        commit: (target) => commits.push(target),
      }),
    (error) => errors.push(error)
  )
  current = snapshot('roi-new')
  const newSnapshot = current
  const newPending = runRoiLandingRedirect(
    () =>
      coordinator.redirect({
        snapshot: newSnapshot,
        getCurrentSnapshot: () => current,
        resolveLanding: () => newLanding.promise,
        commit: (target) => commits.push(target),
      }),
    (error) => errors.push(error)
  )

  oldLanding.reject(new Error('stale connection detail'))
  await oldPending
  assert.deepEqual(errors, [], '旧 token 异常不得污染当前错误处理')
  assert.equal(coordinator.isResolving(), true, '旧 token finally 不得清除新 token')
  newLanding.resolve('landing-new')
  await newPending
  assert.deepEqual(commits, ['landing-new'])
  assert.equal(coordinator.isResolving(), false)
}

console.log('ROI landing redirect error tests passed')
