import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'SQPreviewShow.vue'), 'utf8')

const inheritDatasourceMatch = source.match(
  /function inheritDashboardDatasource\(viewInfo: any\) \{([\s\S]*?)\r?\n\}/
)
const loadCanvasChartsMatch = source.match(
  /collectDashboardCharts\(canvasDataResult\)\.forEach\(\(entry\) => \{([\s\S]*?)\r?\n      \}\)/
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

assert.ok(loadCanvasChartsMatch, '预览页加载看板后需要遍历图表做状态初始化')
assert.match(
  loadCanvasChartsMatch[1],
  /inheritDashboardDatasource\(entry\.viewInfo\)[\s\S]*?canLookupChartCache\(entry\.viewInfo\)/,
  '必须先继承看板 datasource，再判断图表是否可查询；否则会直接显示“没有找到数据”'
)
