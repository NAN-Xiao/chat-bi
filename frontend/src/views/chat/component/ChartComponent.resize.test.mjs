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
