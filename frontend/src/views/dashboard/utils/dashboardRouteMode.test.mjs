import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import ts from 'typescript'

const currentDir = fileURLToPath(new URL('.', import.meta.url))
const sourcePath = join(currentDir, 'dashboardRouteMode.ts')

assert.equal(existsSync(sourcePath), true, '应提供普通看板路由模式校验工具')

const source = readFileSync(sourcePath, 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
})
const tempDir = mkdtempSync(join(tmpdir(), 'dashboard-route-mode-'))
const compiledPath = join(tempDir, 'dashboardRouteMode.mjs')
writeFileSync(compiledPath, compiled.outputText, 'utf8')

try {
  const { resolveOrdinaryDashboardMode, isUnsupportedDashboardMode } = await import(
    pathToFileURL(compiledPath).href
  )

  assert.equal(resolveOrdinaryDashboardMode('default', false), 'default')
  assert.equal(resolveOrdinaryDashboardMode('my', false), 'my')
  assert.equal(resolveOrdinaryDashboardMode('roi', false), 'my')
  assert.equal(resolveOrdinaryDashboardMode('default', true), 'default')
  assert.equal(isUnsupportedDashboardMode(undefined), false)
  assert.equal(isUnsupportedDashboardMode('default'), false)
  assert.equal(isUnsupportedDashboardMode('my'), false)
  assert.equal(isUnsupportedDashboardMode('roi'), true)
  assert.equal(isUnsupportedDashboardMode('unknown'), true)
} finally {
  rmSync(tempDir, { recursive: true, force: true })
}

console.log('Dashboard route mode tests passed')
