import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'index.vue')
const source = readFileSync(componentPath, 'utf8')

const pendingStateMatch = source.match(
  /function isChartResultPendingState\(viewInfo: any, loading: boolean\) \{([\s\S]*?)\r?\n\}/
)
const emptyStateMatch = source.match(
  /function isChartEmptyResultState\(viewInfo: any, hasData: boolean, hasSourceData: boolean, loading: boolean\) \{([\s\S]*?)\r?\n\}/
)
const dataLoadingStateMatch = source.match(
  /const chartDataLoading = computed\(([\s\S]*?)\r?\n\)\r?\nconst chartLoadingText/
)
const loadingStateMatch = source.match(
  /const showFullChartLoading = computed\(([\s\S]*?)\r?\n\)\r?\nconst insightDensity/
)

assert.ok(pendingStateMatch, '需要显式区分图表结果是否仍在首次加载/等待中')
assert.ok(emptyStateMatch, '需要保留看板图表空数据状态判断')
assert.ok(dataLoadingStateMatch, '需要保留看板图表首次数据加载状态判断')
assert.ok(loadingStateMatch, '需要保留看板图表全屏加载状态判断')

assert.match(
  pendingStateMatch[1],
  /viewInfo\?\.status !== CHART_STATUS\.SUCCESS/,
  '图表结果未成功落定前应视为 pending，避免首次空数组误显示“没有找到数据”'
)
assert.match(
  pendingStateMatch[1],
  /viewInfo\?\.dataState !== CHART_RESULT_STATES\.READY/,
  '图表结果未 ready 前应视为 pending，避免缓存/接口结果尚未写入时误显示空态'
)
assert.match(
  pendingStateMatch[1],
  /isChartRefreshPendingState\(viewInfo\?\.refreshState\)/,
  '图表刷新排队或等待时应视为 pending，避免 busy 后短暂显示“没有找到数据”'
)
assert.match(
  dataLoadingStateMatch[1],
  /!hasRenderedChartData\.value/,
  '首次加载且没有可渲染数据时应显示加载态，而不是空数据态'
)
assert.match(
  dataLoadingStateMatch[1],
  /chartResultPending\.value/,
  '图表结果 pending 时应进入首次数据加载态'
)
assert.match(
  loadingStateMatch[1],
  /chartDataLoading\.value/,
  '全屏加载态必须复用首次数据加载状态'
)
assert.match(
  loadingStateMatch[1],
  /showChartContent\.value && !chartFrameReady\.value/,
  '有图表内容但首帧未就绪时必须保留完整遮罩'
)
assert.match(
  emptyStateMatch[1],
  /viewInfo\?\.status === CHART_STATUS\.SUCCESS/,
  '只有接口或缓存明确成功返回后，才能显示“没有找到数据”'
)
assert.match(
  emptyStateMatch[1],
  /viewInfo\?\.dataState === CHART_RESULT_STATES\.READY/,
  '只有数据写入完成后，才能显示“没有找到数据”'
)
assert.match(
  emptyStateMatch[1],
  /!hasSourceData/,
  '原始数据已有行但透视/筛选渲染暂时为空时不能显示“没有找到数据”'
)
assert.match(
  emptyStateMatch[1],
  /!isChartRefreshPendingState\(viewInfo\?\.refreshState\)/,
  '刷新等待或排队期间不能显示“没有找到数据”'
)
