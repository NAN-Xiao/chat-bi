import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import ts from 'typescript'

const currentDir = fileURLToPath(new URL('.', import.meta.url))
const dashboardDir = join(currentDir, '..')
const routeModePath = join(currentDir, 'dashboardRouteMode.ts')
const source = readFileSync(routeModePath, 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
})
const tempDir = mkdtempSync(join(tmpdir(), 'dashboard-editor-navigation-'))
const compiledPath = join(tempDir, 'dashboardRouteMode.mjs')
writeFileSync(compiledPath, compiled.outputText, 'utf8')

try {
  const { buildOrdinaryDashboardQuery } = await import(pathToFileURL(compiledPath).href)

  assert.equal(
    typeof buildOrdinaryDashboardQuery,
    'function',
    '应提供普通看板编辑与返回共用的查询参数构造函数'
  )
  assert.deepEqual(buildOrdinaryDashboardQuery('dashboard-1', 'my'), {
    resourceId: 'dashboard-1',
    dashboardMode: 'my',
  })
  assert.deepEqual(buildOrdinaryDashboardQuery('dashboard-2', 'default'), {
    resourceId: 'dashboard-2',
    dashboardMode: 'default',
  })
  assert.deepEqual(buildOrdinaryDashboardQuery('dashboard-3', 'unknown'), {
    resourceId: 'dashboard-3',
    dashboardMode: 'my',
  })

  const previewHeadSource = readFileSync(join(dashboardDir, 'preview', 'SQPreviewHead.vue'), 'utf8')
  const resourceTreeSource = readFileSync(join(dashboardDir, 'common', 'ResourceTree.vue'), 'utf8')
  const editorSource = readFileSync(join(dashboardDir, 'editor', 'index.vue'), 'utf8')
  const toolbarSource = readFileSync(join(dashboardDir, 'editor', 'Toolbar.vue'), 'utf8')

  assert.match(previewHeadSource, /buildOrdinaryDashboardQuery/)
  assert.match(
    previewHeadSource,
    /buildOrdinaryDashboardQuery\([\s\S]*?props\.dashboardInfo\.id,[\s\S]*?props\.dashboardInfo\.dashboardMode[\s\S]*?\)/,
    '看板头部编辑入口应使用预览页已经解析好的模式，兼容不在 URL 中携带 dashboardMode 的默认看板页'
  )
  assert.match(resourceTreeSource, /buildOrdinaryDashboardQuery/)
  assert.match(editorSource, /dashboardMode\s*=\s*resolveOrdinaryDashboardMode/)
  assert.match(editorSource, /dashboardMode:\s*state\.dashboardMode/)
  assert.match(toolbarSource, /buildOrdinaryDashboardQuery/)
  assert.match(toolbarSource, /baseParams\?\.dashboardMode/)
  assert.match(toolbarSource, /path:\s*['"]\/system\/dashboard-template['"]/)
} finally {
  rmSync(tempDir, { recursive: true, force: true })
}

console.log('Dashboard editor navigation tests passed')
