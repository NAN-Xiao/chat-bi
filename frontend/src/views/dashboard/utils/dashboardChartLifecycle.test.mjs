import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import ts from 'typescript'

const currentDir = fileURLToPath(new URL('.', import.meta.url))
const lifecyclePath = join(currentDir, 'dashboardChartLifecycle.ts')

assert.equal(existsSync(lifecyclePath), true, '看板预览和编辑必须复用统一的图表加载生命周期')

const source = readFileSync(lifecyclePath, 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
})
const tempDir = mkdtempSync(join(tmpdir(), 'dashboard-chart-lifecycle-'))
const compiledPath = join(tempDir, 'dashboardChartLifecycle.mjs')
writeFileSync(compiledPath, compiled.outputText, 'utf8')

try {
  const { hasDashboardChartSnapshot, prepareDashboardChartRefreshState, reconcileDashboardViewInfo } =
    await import(pathToFileURL(compiledPath).href)

  const rows = [{ day: '2026-08-01', value: 10 }]
  const snapshot = {
    status: 'loading',
    dataState: 'loading',
    refreshState: 'waiting',
    loadingProgress: 0,
    data: { data: rows, fields: ['day', 'value'] },
    fields: ['day', 'value'],
  }
  assert.equal(prepareDashboardChartRefreshState(snapshot, 'waiting'), true)
  assert.equal(snapshot.data.data, rows, '后台刷新不能清空接口已返回的图表快照')
  assert.equal(snapshot.status, 'success')
  assert.equal(snapshot.dataState, 'ready')
  assert.equal(snapshot.refreshState, '', '保留旧帧时不得重新触发全屏 loading')
  assert.equal(snapshot.loadingProgress, 100)

  const completedEmpty = {
    status: 'success',
    dataState: 'ready',
    snapshotRefreshedAt: 123,
    data: { data: [], fields: ['day', 'value'] },
    fields: ['day', 'value'],
  }
  assert.equal(
    prepareDashboardChartRefreshState(completedEmpty, 'loading'),
    true,
    '已经完成的空结果也应保留为空态，不能退回加载态闪烁'
  )
  assert.equal(completedEmpty.status, 'success')
  assert.equal(completedEmpty.dataState, 'ready')

  const refreshedFieldOnly = {
    status: 'success',
    dataState: 'ready',
    data: { data: [], fields: ['day', 'value'], snapshotRefreshedAt: 456 },
    fields: ['day', 'value'],
  }
  assert.equal(
    hasDashboardChartSnapshot(refreshedFieldOnly),
    true,
    '已刷新成功的字段快照即使没有行，也必须被所有刷新入口视为可用快照'
  )

  const pending = { data: { data: [], fields: [] }, fields: [] }
  assert.equal(prepareDashboardChartRefreshState(pending, 'waiting'), false)
  assert.equal(pending.status, 'loading')
  assert.equal(pending.dataState, 'loading')
  assert.equal(pending.refreshState, 'waiting')
  assert.equal(pending.loadingProgress, 0)

  const existingChart = {
    id: 'chart-1',
    status: 'success',
    data: { data: [{ value: 1 }], fields: ['value'] },
  }
  const target = {
    'chart-1': existingChart,
    removed: { id: 'removed' },
  }
  const incoming = {
    'chart-1': {
      id: 'chart-1',
      status: 'success',
      data: { data: [{ value: 2 }], fields: ['value'] },
    },
    'chart-2': { id: 'chart-2', data: { data: [] } },
  }
  const reconciled = reconcileDashboardViewInfo(target, incoming)
  assert.equal(reconciled, target, '刷新必须复用当前 viewInfo 容器')
  assert.equal(target['chart-1'], existingChart, '同一图表刷新必须保留组件持有的对象身份')
  assert.deepEqual(target['chart-1'].data.data, [{ value: 2 }])
  assert.equal('removed' in target, false, '服务端已删除的图表配置不能残留')
  assert.equal(target['chart-2'], incoming['chart-2'])
} finally {
  rmSync(tempDir, { recursive: true, force: true })
}

const templateSource = readFileSync(
  join(currentDir, '../../system/dashboard-template/index.vue'),
  'utf8'
)
const refreshFunction =
  templateSource.match(/const refreshTemplateCharts = async \([\s\S]*?\n\}/)?.[0] || ''
assert.ok(refreshFunction, '平台模板必须保留统一刷新入口')
assert.match(
  templateSource,
  /prepareDashboardChartRefreshState\(/,
  '平台模板必须复用公共快照保留协议'
)
assert.match(
  refreshFunction,
  /reconcileDashboardViewInfo\(/,
  '平台模板刷新结果必须原地合并'
)
assert.doesNotMatch(
  refreshFunction,
  /previewKey\.value\s*\+=\s*1/,
  '后台刷新不能通过变更 key 销毁并重挂全部看板面板'
)

for (const relativePath of [
  '../preview/SQPreviewShow.vue',
  '../editor/index.vue',
  '../preview/SQComponentWrapper.vue',
]) {
  const consumerSource = readFileSync(join(currentDir, relativePath), 'utf8')
  assert.match(
    consumerSource,
    /prepareDashboardChartRefreshState\(/,
    `${relativePath} 必须复用公共快照保留协议`
  )
  assert.match(
    consumerSource,
    /hasDashboardChartSnapshot/,
    `${relativePath} 必须直接使用公共快照判断，不能继续维护 row-only 快照定义`
  )
  assert.doesNotMatch(
    consumerSource,
    /function hasChartSnapshot\(/,
    `${relativePath} 不能继续定义局部 row-only hasChartSnapshot`
  )
}

console.log('Dashboard chart lifecycle tests passed')
