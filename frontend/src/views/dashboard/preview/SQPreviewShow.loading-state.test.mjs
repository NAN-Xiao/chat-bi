import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'SQPreviewShow.vue'), 'utf8')

const inheritDatasourceMatch = source.match(
  /function inheritDashboardDatasource\(viewInfo: any\) \{([\s\S]*?)\r?\n\}/
)
const normalizedChartsMatch = source.match(
  /function collectNormalizedDashboardCharts\(canvasData: any = state\.canvasDataPreview\) \{([\s\S]*?)\r?\n\}/
)
const prepareChartsMatch = source.match(
  /function prepareDashboardCharts\(canvasData: any\) \{([\s\S]*?)\r?\n\}/
)
const preparePreviewStateMatch = source.match(
  /function prepareChartPreviewState\(viewInfo: any\) \{([\s\S]*?)\r?\n\}/
)
const prepareDatabaseStateMatch = source.match(
  /function prepareChartDatabaseRefreshState\(viewInfo: any\) \{([\s\S]*?)\r?\n\}/
)
const refreshChartsMatch = source.match(
  /async function refreshDashboardCharts\([\s\S]*?\n\}/
)
const autoRefreshMatch = source.match(
  /function scheduleNextDashboardAutoRefresh\([\s\S]*?\n\}/
)
const loadCanvasMatch = source.match(
  /const loadCanvasData = \(params: any\) => \{([\s\S]*?)\r?\n\}/
)

assert.ok(
  inheritDatasourceMatch,
  '预览页需要把看板级 datasource 补给缺失 datasource 的图表，避免跳过 loading/刷新'
)
assert.match(
  inheritDatasourceMatch[1],
  /state\.dashboardInfo\?\.datasource/,
  '补 datasource 时必须使用当前看板绑定的数据源，而不是猜测全局默认数据源'
)
assert.match(
  inheritDatasourceMatch[1],
  /if \(viewInfo\.datasource \|\| !dashboardDatasource\) \{\s*return\s*\}/,
  '图表已有 datasource 时不能覆盖；看板没有绑定数据源时也不能伪造'
)
assert.match(
  inheritDatasourceMatch[1],
  /viewInfo\.datasource = dashboardDatasource/,
  '缺失 datasource 的 SQL 图表应继承看板级 datasource，才能进入 loading 并刷新'
)

assert.ok(normalizedChartsMatch, '预览页需要提供统一的图表归一化入口')
assert.match(
  normalizedChartsMatch[1],
  /collectDashboardCharts\(canvasData\)[\s\S]*?inheritDashboardDatasource\(entry\.viewInfo\)/,
  '归一化入口必须先收集图表，并为缺失 datasource 的图表继承看板数据源'
)
assert.ok(prepareChartsMatch, '首次加载需要通过统一的图表准备入口初始化状态')
assert.match(
  prepareChartsMatch[1],
  /collectNormalizedDashboardCharts\(canvasData\)[\s\S]*?canLookupChartCache\(entry\.viewInfo\)[\s\S]*?prepareChartPreviewState\(entry\.viewInfo\)/,
  '首次加载必须在归一化后再判断是否可查询并设置 loading 状态'
)
assert.ok(preparePreviewStateMatch, '首次加载需要明确初始化图表等待状态')
assert.match(
  preparePreviewStateMatch[1],
  /clearPendingChartData\(viewInfo, 'waiting'\)/,
  '首次加载的无数据图表必须进入 loading/waiting，由完整加载态接管显示'
)
assert.ok(prepareDatabaseStateMatch, '数据库后台刷新需要独立的状态准备函数')
assert.match(
  prepareDatabaseStateMatch[1],
  /if \(hasUsableChartSnapshot\(viewInfo\)\) \{[\s\S]*?viewInfo\.status = 'success'[\s\S]*?viewInfo\.dataState = 'ready'[\s\S]*?return/,
  '已有可用快照时后台刷新必须保留 success/ready，不能清空当前图表'
)
assert.ok(refreshChartsMatch, '刷新队列需要存在')
assert.match(
  refreshChartsMatch[0],
  /const allChartEntries = collectNormalizedDashboardCharts\(\)/,
  '刷新队列必须从归一化后的图表集合开始，不能绕过数据源继承'
)
assert.ok(autoRefreshMatch, '自动刷新调度需要存在')
assert.match(
  autoRefreshMatch[0],
  /collectNormalizedDashboardCharts\(\)/,
  '自动刷新必须从归一化后的图表集合筛选可查询图表'
)
assert.ok(loadCanvasMatch, '看板加载入口需要存在')
assert.match(
  loadCanvasMatch[0],
  /prepareDashboardCharts\(canvasDataResult\)/,
  '看板加载后必须通过统一的图表准备入口初始化，不能在调用点分散继承数据源'
)
