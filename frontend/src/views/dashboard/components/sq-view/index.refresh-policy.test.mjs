import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'index.vue')
const source = readFileSync(componentPath, 'utf8')

const refreshDataMatch = source.match(
  /async function refreshData\(options: RefreshDataOptions = \{\}\) \{([\s\S]*?)\r?\n  if \(props\.platformTemplate\)/
)
const normalizeLoadedChartStateMatch = source.match(
  /function normalizeLoadedChartState\(\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction normalizePlatformTemplateSnapshotState/
)
const recoverStaleLoadingStateMatch = source.match(
  /async function recoverStaleLoadingState\(\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nwatch\(/
)

assert.ok(refreshDataMatch, '需要保留看板图表 refreshData 入口')
assert.ok(normalizeLoadedChartStateMatch, '需要保留持久化图表结果恢复逻辑')
assert.ok(recoverStaleLoadingStateMatch, '需要保留看板图表 loading 状态恢复入口')
assert.match(
  refreshDataMatch[1],
  /const forceRefresh = options\.forceRefresh === true/,
  '打开看板或编辑页时，refreshData 默认不能强制执行 SQL，只有显式 forceRefresh=true 才强刷'
)
assert.doesNotMatch(
  refreshDataMatch[1],
  /options\.forceRefresh !== false/,
  '不能把未传 forceRefresh 当作强刷，否则进入页面会主动跑 SQL'
)
assert.match(
  source,
  /refreshData\(\{ silent: true, forceRefresh: true, blocking: true \}\)/,
  '用户在图表编辑器里主动执行/刷新时，仍需要显式强制刷新'
)
assert.match(
  normalizeLoadedChartStateMatch[1],
  /hasChartShape\(props\.viewInfo\)/,
  '持久化结果即使只有字段没有数据行，也应该结束 loading 并直接渲染空结果'
)
assert.doesNotMatch(
  normalizeLoadedChartStateMatch[1],
  /hasChartResult\(props\.viewInfo\)/,
  '打开页面恢复持久化结果时不能只认有数据行，否则空结果图表会被误判为需要刷新'
)
assert.doesNotMatch(
  recoverStaleLoadingStateMatch[1],
  /refreshData\(\{ silent: true, forceRefresh: false \}\)/,
  '打开看板或编辑页恢复 loading 状态时不能主动请求 SQL，应等待用户手动刷新'
)
