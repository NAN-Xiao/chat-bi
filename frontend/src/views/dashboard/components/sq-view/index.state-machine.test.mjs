import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'index.vue')
const source = readFileSync(componentPath, 'utf8')

assert.match(source, /const CHART_RESULT_STATES = Object\.freeze\(/, '图表结果状态需要集中定义')
assert.match(source, /const CHART_REFRESH_STATES = Object\.freeze\(/, '图表刷新状态需要集中定义')

const pendingFunctionMatch = source.match(
  /function isChartResultPendingState\(viewInfo: any, loading: boolean\) \{([\s\S]*?)\r?\n\}/
)
const emptyFunctionMatch = source.match(
  /function isChartEmptyResultState\(viewInfo: any, hasData: boolean, hasSourceData: boolean, loading: boolean\) \{([\s\S]*?)\r?\n\}/
)
const refreshFunctionMatch = source.match(
  /function isChartRefreshPendingState\(refreshState: any\) \{([\s\S]*?)\r?\n\}/
)
const unsnapshottedFunctionMatch = source.match(
  /function isRefreshableChartWithoutSnapshot\(viewInfo: any\) \{([\s\S]*?)\r?\n\}/
)
const shapeFunctionMatch = source.match(
  /function ensureViewInfoShape\(\) \{([\s\S]*?)\r?\n\}/
)

assert.ok(pendingFunctionMatch, '需要用状态机函数判断图表结果是否仍在 pending')
assert.ok(emptyFunctionMatch, '需要用状态机函数判断图表是否是真实空结果')
assert.ok(refreshFunctionMatch, '需要用状态机函数判断刷新等待/排队/加载状态')
assert.ok(unsnapshottedFunctionMatch, '需要识别有查询但没有结果快照的图表')
assert.ok(shapeFunctionMatch, '需要在 viewInfo 归一化入口统一修正旧保存态')

assert.match(
  pendingFunctionMatch[1],
  /viewInfo\?\.dataState !== CHART_RESULT_STATES\.READY/,
  '图表结果未 ready 时必须视为 pending'
)
assert.match(
  pendingFunctionMatch[1],
  /isRefreshableChartWithoutSnapshot\(viewInfo\)/,
  '有 SQL 但没有结果快照的保存态必须视为 pending，不能直接显示空态'
)
assert.match(
  pendingFunctionMatch[1],
  /viewInfo\?\.status !== CHART_STATUS\.SUCCESS/,
  '图表状态未 success 时必须视为 pending'
)
assert.match(
  emptyFunctionMatch[1],
  /viewInfo\?\.status === CHART_STATUS\.SUCCESS/,
  '只有成功状态才能显示空结果'
)
assert.match(
  emptyFunctionMatch[1],
  /viewInfo\?\.dataState === CHART_RESULT_STATES\.READY/,
  '只有结果 ready 后才能显示空结果'
)
assert.match(
  emptyFunctionMatch[1],
  /!hasSourceData/,
  '原始数据已有行但渲染数据暂时为空时不能显示空结果，避免透视/筛选初始化误报'
)
assert.match(
  emptyFunctionMatch[1],
  /!isChartRefreshPendingState\(viewInfo\?\.refreshState\)/,
  '刷新等待或排队期间不能显示空结果'
)
assert.match(
  unsnapshottedFunctionMatch[1],
  /chartSnapshotRefreshedAt\(viewInfo\) <= 0/,
  '只有没有刷新完成戳的图表才需要从保存态强制回到 loading'
)
assert.match(
  shapeFunctionMatch[1],
  /isRefreshableChartWithoutSnapshot\(props\.viewInfo\)[\s\S]*?props\.viewInfo\.status = CHART_STATUS\.LOADING[\s\S]*?props\.viewInfo\.dataState = CHART_RESULT_STATES\.LOADING[\s\S]*?props\.viewInfo\.refreshState = CHART_REFRESH_STATES\.WAITING/,
  'viewInfo 归一化时必须把有查询但无快照的旧 success/ready 空保存态改成 loading/waiting'
)

const computedWiringMatch = source.match(
  /const showEmptyChartState = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)/
)
assert.ok(computedWiringMatch, '需要保留空结果计算属性')
assert.match(
  computedWiringMatch[1],
  /isChartEmptyResultState\(\s*props\.viewInfo,\s*hasRenderedChartData\.value,\s*hasSourceChartData\.value,\s*chartLoading\.value\s*\)/,
  '空结果显示必须通过状态机函数统一判断'
)

const staleRecoveryMatch = source.match(
  /async function recoverStaleLoadingState\(\) \{([\s\S]*?)\r?\n\}/
)
assert.ok(staleRecoveryMatch, '需要保留陈旧 loading 状态恢复逻辑')
assert.match(
  staleRecoveryMatch[1],
  /isChartRefreshPendingState\(props\.viewInfo\?\.refreshState\)/,
  '刷新等待/排队/加载中的图表不能被陈旧状态恢复改成 ready，否则会短暂误显示“没有找到数据”'
)
assert.doesNotMatch(
  staleRecoveryMatch[1],
  /props\.viewInfo\.status = props\.viewInfo\.status === 'failed' \? 'failed' : 'success'/,
  '没有持久化图表形状或快照时，陈旧 loading 恢复不能直接落成 success/ready，否则空数组会被误判为真实空结果'
)
assert.match(
  staleRecoveryMatch[1],
  /if \(!hasChartShape\(props\.viewInfo\)\) \{\s*return\s*\}/,
  '陈旧 loading 恢复必须要求已有持久化图表形状或快照；新建/新增看板等待接口期间应保持 loading'
)
