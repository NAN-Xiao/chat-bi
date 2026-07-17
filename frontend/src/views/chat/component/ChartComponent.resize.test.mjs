import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const component = readFileSync('src/views/chat/component/ChartComponent.vue', 'utf8')
const dashboardView = readFileSync('src/views/dashboard/components/sq-view/index.vue', 'utf8')
const table = readFileSync('src/views/chat/component/charts/Table.ts', 'utf8')

assert.match(
  table,
  /changeSheetSize\(width, height\)[\s\S]*?render\(false\)/,
  'AntV S2 表格必须继续使用原地尺寸调整'
)
assert.match(table, /lastResizeWidth/, 'S2 表格必须记录上一次容器宽度')
assert.match(table, /lastResizeHeight/, 'S2 表格必须记录上一次容器高度')
assert.match(
  table,
  /width === this\.lastResizeWidth && height === this\.lastResizeHeight[\s\S]*?return/,
  '容器宽高没有变化时不得再次触发 S2 render'
)
assert.match(
  component,
  /new ResizeObserver\([\s\S]*?params\.type\s*!==\s*['"]table['"][\s\S]*?scheduleRenderChart/,
  'ChartComponent 的尺寸监听不得销毁并重建 table 图表'
)
assert.match(
  dashboardView,
  /new ResizeObserver\([\s\S]*?chartType\.value\s*!==\s*['"]table['"][\s\S]*?scheduleRenderChart/,
  '看板外层尺寸监听不得再次销毁并重建 table 图表'
)

console.log('ChartComponent resize tests passed')
