import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import ts from 'typescript'

const currentDir = fileURLToPath(new URL('.', import.meta.url))
const lifecycleSourcePath = join(currentDir, 'routeLoadLifecycle.ts')
const editorSourcePath = join(currentDir, 'index.vue')

assert.equal(
  existsSync(lifecycleSourcePath),
  true,
  '需要提供可独立验证的编辑页路由加载生命周期令牌'
)

const lifecycleSource = readFileSync(lifecycleSourcePath, 'utf8')
const compiled = ts.transpileModule(lifecycleSource, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
})
const tempDir = mkdtempSync(join(tmpdir(), 'dashboard-route-load-lifecycle-'))
const compiledPath = join(tempDir, 'routeLoadLifecycle.mjs')
writeFileSync(compiledPath, compiled.outputText, 'utf8')

try {
  const { createRouteLoadLifecycle } = await import(pathToFileURL(compiledPath).href)
  const lifecycle = createRouteLoadLifecycle()

  const firstLoad = lifecycle.begin()
  assert.equal(lifecycle.isCurrent(firstLoad), true, '首个加载令牌应当有效')

  const secondLoad = lifecycle.begin()
  assert.equal(lifecycle.isCurrent(firstLoad), false, '新加载开始后旧令牌必须失效')
  assert.equal(lifecycle.isCurrent(secondLoad), true, '最新加载令牌应当有效')

  lifecycle.dispose()
  assert.equal(lifecycle.isCurrent(secondLoad), false, '组件卸载后当前令牌也必须失效')
  assert.equal(lifecycle.isCurrent(lifecycle.begin()), false, '已卸载实例不能重新产生有效令牌')
} finally {
  rmSync(tempDir, { recursive: true, force: true })
}

const editorSource = readFileSync(editorSourcePath, 'utf8')
const applyLoadedCanvasResource =
  editorSource.match(/const applyLoadedCanvasResource = async \(([\s\S]*?)\r?\n\}/)?.[0] || ''
const loadCanvasFromRoute =
  editorSource.match(/const loadCanvasFromRoute = async \(\) => \{([\s\S]*?)\r?\n\}/)?.[0] || ''
const beforeUnmount =
  editorSource.match(/onBeforeUnmount\(\(\) => \{([\s\S]*?)\r?\n\}\)/)?.[0] || ''

assert.match(
  editorSource,
  /import \{ createRouteLoadLifecycle \} from ['"]@\/views\/dashboard\/editor\/routeLoadLifecycle['"]/,
  '编辑页必须使用可卸载的路由加载生命周期令牌'
)
assert.ok(applyLoadedCanvasResource, '需要保留画布资源提交入口')
assert.match(
  applyLoadedCanvasResource,
  /loadVersion: number[\s\S]*?await datasourceContext\.activateDatasourceById\([\s\S]*?if \(!routeLoadLifecycle\.isCurrent\(loadVersion\)\) \{\s*return false\s*\}[\s\S]*?dashboardStore\.setDashboardInfo/,
  '异步数据源激活后必须重新校验令牌，旧请求不能写入 Pinia'
)
assert.match(
  editorSource,
  /await applyLoadedCanvasResource\(templateId, result, loadVersion, sourceKey\)/,
  '平台模板加载提交必须携带当前令牌'
)
assert.match(
  editorSource,
  /await applyLoadedCanvasResource\(resourceId, result, loadVersion\)/,
  '普通看板加载提交必须携带当前令牌'
)
assert.ok(loadCanvasFromRoute, '需要保留统一的路由画布加载入口')
assert.match(
  loadCanvasFromRoute,
  /let routeStateApplied = false/,
  '每次路由加载必须独立记录目标状态是否已经提交'
)
assert.match(
  loadCanvasFromRoute,
  /if \(!result\?\.dashboardInfo\?\.id\) \{\s*routeStateApplied = await resetCanvasAfterLoadFailure\(loadVersion\)\s*return\s*\}/,
  '资源请求返回空结果时必须显式清空旧画布'
)
assert.match(
  loadCanvasFromRoute,
  /catch \(error\) \{[\s\S]*?routeStateApplied = await resetCanvasAfterLoadFailure\(loadVersion\)/,
  '数据源或资源加载抛错时必须显式清空旧画布'
)
assert.match(
  loadCanvasFromRoute,
  /if \(routeLoadLifecycle\.isCurrent\(loadVersion\) && routeStateApplied\) \{\s*dataInitState\.value = true/,
  '只有已经提交或清空目标状态的当前加载才能重新挂载编辑器'
)
assert.match(
  editorSource,
  /const resetCanvasAfterLoadFailure = async \(loadVersion: number\) => \{[\s\S]*?dashboardStore\.canvasDataInit\(\)[\s\S]*?return routeLoadLifecycle\.isCurrent\(loadVersion\)/,
  '失败恢复必须在当前令牌下清空全局画布状态'
)
assert.match(beforeUnmount, /routeLoadLifecycle\.dispose\(\)/, '组件卸载必须使未完成加载失效')

console.log('Dashboard editor route load lifecycle tests passed')
