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

const fullLoadingMatch = source.match(
  /const showFullChartLoading = computed\(\s*\(\) =>([\s\S]*?)\r?\n\)/
)
assert.ok(fullLoadingMatch, '需要集中判断图表是否显示完整加载态')
assert.match(
  fullLoadingMatch[1],
  /chartDataLoading\.value/,
  '首次数据未完成时必须显示完整加载态'
)
assert.match(
  fullLoadingMatch[1],
  /showChartContent\.value && !chartFrameReady\.value/,
  '数据就绪后仍必须等待图表首帧提交才能移除完整加载态'
)

const chartContentMatch = source.match(
  /const showChartContent = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)/
)
assert.ok(chartContentMatch, '需要集中判断图表内容是否可以挂载')
assert.match(
  chartContentMatch[1],
  /hasRenderedChartData\.value/,
  '只有存在可渲染数据时才挂载图表'
)
assert.doesNotMatch(
  chartContentMatch[1],
  /showFullChartLoading\.value/,
  '图表必须能在首次完整遮罩后挂载并完成首帧，不能形成等待闭环'
)
assert.match(
  source,
  /const chartFrameReady = ref\(false\)/,
  '卡片需要独立记录图表首帧是否已经提交'
)
assert.match(
  source,
  /function handleChartRenderReady\(\) \{\s*chartFrameReady\.value = true\s*\}/,
  '收到图表提交事件后应结束首次遮罩'
)
assert.match(
  source,
  /watch\(\s*chartComponentKey,\s*\(\) => \{\s*chartFrameReady\.value = false\s*\}\s*\)/,
  '只有图表实例身份变化时才重置首帧状态，后台刷新不能回退到首次加载'
)
assert.match(
  source,
  /<div v-if="showFullChartLoading" class="chart-loading-info">[\s\S]*?<div\s+v-if="showChartContent"/,
  '模板必须让完整加载遮罩与图表挂载独立存在'
)
assert.match(
  source,
  /<ChartComponent[\s\S]*?@render-ready="handleChartRenderReady"/,
  '卡片必须接收图表原子提交后的首帧事件'
)
assert.match(
  source,
  /const chartRenderColumns = computed\(\(\) => \[\s*\.\.\.\(props\.viewInfo\.chart\.columns \|\| \[\]\),\s*\.\.\.insightColumns\.value,?\s*\]\)/,
  '传给图表的列配置必须使用稳定 computed 引用'
)
const chartComponentTemplateMatch = source.match(/<ChartComponent([\s\S]*?)\/>/)
assert.ok(chartComponentTemplateMatch, '需要保留图表组件挂载')
assert.match(
  chartComponentTemplateMatch[1],
  /:columns="chartRenderColumns"/,
  '父组件 ready 状态变化时不能创建新的 columns 数组并反向触发一次图表重绘'
)
assert.doesNotMatch(
  chartComponentTemplateMatch[1],
  /:columns="\[/,
  '图表组件模板不能使用内联数组作为受监听的内容属性'
)
assert.doesNotMatch(
  source,
  /chartRef\.value\?\.destroyChart\(\)[\s\S]*?chartRef\.value\?\.renderChart\(\)/,
  '看板外层不得先清空可见图表再调用异步重绘'
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
