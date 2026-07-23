import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import ts from 'typescript'

const currentDir = fileURLToPath(new URL('.', import.meta.url))
const sourcePath = join(currentDir, 'dashboardLandingRedirectCoordinator.ts')

assert.equal(existsSync(sourcePath), true, '应提供普通看板 landing 最新请求协调器')

const source = readFileSync(sourcePath, 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
})
const tempDir = mkdtempSync(join(tmpdir(), 'dashboard-landing-redirect-'))
const compiledPath = join(tempDir, 'dashboardLandingRedirectCoordinator.mjs')
writeFileSync(compiledPath, compiled.outputText, 'utf8')

const deferred = () => {
  let resolve
  const promise = new Promise((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

try {
  const { createDashboardLandingRedirectCoordinator } = await import(
    pathToFileURL(compiledPath).href
  )

  {
    const coordinator = createDashboardLandingRedirectCoordinator()
    const first = deferred()
    const second = deferred()
    const commits = []
    let currentFullPath = '/dashboard/index?dashboardMode=roi'

    const pendingFirst = coordinator.redirect({
      sourceFullPath: currentFullPath,
      getCurrentFullPath: () => currentFullPath,
      resolveLanding: () => first.promise,
      commit: (target) => commits.push(target),
    })

    currentFullPath = '/dashboard/index?dashboardMode=unknown'
    const pendingSecond = coordinator.redirect({
      sourceFullPath: currentFullPath,
      getCurrentFullPath: () => currentFullPath,
      resolveLanding: () => second.promise,
      commit: (target) => commits.push(target),
    })

    first.resolve('/dashboard/index?dashboardMode=my')
    await pendingFirst
    assert.deepEqual(commits, [], '先发请求不得覆盖后发请求')
    assert.equal(coordinator.isResolving(), true, '旧请求结束时不得清除新请求的 loading')

    second.resolve('/dashboard/index?dashboardMode=my')
    await pendingSecond
    assert.deepEqual(commits, ['/dashboard/index?dashboardMode=my'])
    assert.equal(coordinator.isResolving(), false)
  }

  {
    const coordinator = createDashboardLandingRedirectCoordinator()
    const landing = deferred()
    const commits = []
    const currentFullPath = '/dashboard/index?dashboardMode=roi'
    const pending = coordinator.redirect({
      sourceFullPath: currentFullPath,
      getCurrentFullPath: () => currentFullPath,
      resolveLanding: () => landing.promise,
      commit: (target) => commits.push(target),
    })

    coordinator.invalidate()
    landing.resolve('/dashboard/index?dashboardMode=my')
    await pending
    assert.deepEqual(commits, [], '组件卸载或离开无效路由后不得提交旧重定向')
    assert.equal(coordinator.isResolving(), false)
  }
} finally {
  rmSync(tempDir, { recursive: true, force: true })
}

console.log('Dashboard landing redirect coordinator tests passed')
