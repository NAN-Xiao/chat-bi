import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import ts from 'typescript'

const currentDir = fileURLToPath(new URL('.', import.meta.url))
const handoffSourcePath = join(currentDir, 'canvasRouteHandoff.ts')
const previewHeadPath = join(currentDir, '../preview/SQPreviewHead.vue')
const editorPath = join(currentDir, 'index.vue')

assert.equal(
  existsSync(handoffSourcePath),
  true,
  '编辑页必须提供可独立验证的一次性路由数据交接模块'
)

const handoffSource = readFileSync(handoffSourcePath, 'utf8')
const compiled = ts.transpileModule(handoffSource, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
})
const tempDir = mkdtempSync(join(tmpdir(), 'dashboard-canvas-route-handoff-'))
const compiledPath = join(tempDir, 'canvasRouteHandoff.mjs')
writeFileSync(compiledPath, compiled.outputText, 'utf8')

try {
  const {
    clearCanvasRouteHandoff,
    consumeCanvasRouteHandoff,
    primeCanvasRouteHandoff,
  } = await import(pathToFileURL(compiledPath).href)
  const platformPayload = {
    sourceKey: 'platform-template:template-1',
    dashboardInfo: { id: 'template-1', name: '养成看板' },
    canvasDataResult: [{ id: 'chart-1', component: 'SQView' }],
    canvasStyleResult: { width: 1920 },
    canvasViewInfoPreview: { 'chart-1': { chart: { type: 'table' } } },
  }
  const dashboardPayload = {
    sourceKey: 'dashboard:dashboard-1',
    dashboardInfo: { id: 'dashboard-1', name: '经营看板', dashboardMode: 'my' },
    canvasDataResult: [{ id: 'chart-2', component: 'SQView' }],
    canvasStyleResult: { width: 1440 },
    canvasViewInfoPreview: { 'chart-2': { chart: { type: 'line' } } },
  }

  clearCanvasRouteHandoff()
  primeCanvasRouteHandoff(platformPayload)
  assert.deepEqual(
    consumeCanvasRouteHandoff(platformPayload.sourceKey),
    platformPayload,
    '编辑页应消费当前模板的预取数据'
  )
  assert.equal(
    consumeCanvasRouteHandoff(platformPayload.sourceKey),
    null,
    '路由交接数据只能消费一次，避免重复进入时复用旧请求结果'
  )

  primeCanvasRouteHandoff(platformPayload)
  assert.equal(
    consumeCanvasRouteHandoff('platform-template:other-template'),
    null,
    '来源键不匹配时不能把其他模板的数据交给当前编辑页'
  )
  assert.equal(
    consumeCanvasRouteHandoff(platformPayload.sourceKey),
    null,
    '来源键不匹配后应清理悬挂交接，避免后续导航误用'
  )

  primeCanvasRouteHandoff(dashboardPayload)
  assert.deepEqual(
    consumeCanvasRouteHandoff(dashboardPayload.sourceKey),
    dashboardPayload,
    '普通看板必须复用同一个按来源键隔离的一次性交接协议'
  )
} finally {
  rmSync(tempDir, { recursive: true, force: true })
}

const previewHeadSource = readFileSync(previewHeadPath, 'utf8')
const editorSource = readFileSync(editorPath, 'utf8')
assert.match(
  previewHeadSource,
  /primeCanvasRouteHandoff\([\s\S]*?await router\.push\(/,
  '看板必须先完成数据交接，再切换到编辑路由'
)
assert.match(
  previewHeadSource,
  /getDashboardCanvasSourceKey\(/,
  '普通看板编辑必须使用与编辑器一致的来源键'
)
assert.doesNotMatch(
  previewHeadSource,
  /if \(isPlatformTemplate\) \{[\s\S]*?primeCanvasRouteHandoff\(/,
  '数据交接不能只覆盖平台模板入口'
)
assert.match(
  previewHeadSource,
  /canvasStyleResult:\s*props\.canvasStyleData/,
  '交接必须保留完整画布样式，不能只传图表数据'
)
assert.match(
  editorSource,
  /consumeCanvasRouteHandoff\(/,
  '编辑页必须在首帧消费通用看板交接数据'
)
assert.match(
  editorSource,
  /initialPlatformTemplateId[\s\S]*?initialResourceId[\s\S]*?consumeCanvasRouteHandoff/,
  '编辑页首帧必须同时解析平台模板和普通看板来源键'
)
assert.match(
  editorSource,
  /prefetchedRouteSourceKey === sourceKey[\s\S]*?dataInitState\.value = true/,
  '权威数据后台加载时必须保持已交接画布可见，不能重新关闭公共就绪门'
)

console.log('Dashboard canvas route handoff tests passed')
