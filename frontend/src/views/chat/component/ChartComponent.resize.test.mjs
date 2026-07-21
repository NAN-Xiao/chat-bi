import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const component = readFileSync('src/views/chat/component/ChartComponent.vue', 'utf8')
const dashboardView = readFileSync('src/views/dashboard/components/sq-view/index.vue', 'utf8')
const table = readFileSync('src/views/chat/component/charts/Table.ts', 'utf8')

assert.match(
  table,
  /changeSheetSize\(contentWidth, height\)[\s\S]*?render\(false\)/,
  'AntV S2 表格必须继续使用原地尺寸调整'
)
assert.match(table, /lastResizeWidth/, 'S2 表格必须记录上一次容器宽度')
assert.match(table, /lastResizeHeight/, 'S2 表格必须记录上一次容器高度')
assert.match(
  table,
  /interaction:\s*\{[\s\S]*?scrollbarPosition:\s*['"]content['"]/,
  'S2 表格滚动条必须位于内容边缘，避免底部滚动条遮挡最后一行'
)
assert.match(
  table,
  /width === this\.lastResizeWidth && height === this\.lastResizeHeight[\s\S]*?return/,
  '容器宽高没有变化时不得再次触发 S2 render'
)
assert.match(
  table,
  /function resolveTableColumnWidth\(\s*containerWidth:\s*number,\s*visibleColumnCount:\s*number\s*\)[\s\S]*Math\.max\([\s\S]*TABLE_MIN_COLUMN_WIDTH,[\s\S]*Math\.floor\(containerWidth \/ Math\.max\(visibleColumnCount, 1\)\)/,
  'S2 表格必须按当前容器宽度和可见字段数计算最小 92px 的列宽'
)
assert.match(
  table,
  /debounce\(\s*async\s*\(width\?: number, height\?: number\)[\s\S]*this\.table\.setOptions\([\s\S]*colCell:[\s\S]*width: columnWidth[\s\S]*dataCell:[\s\S]*width: columnWidth[\s\S]*changeSheetSize\(contentWidth, height\)[\s\S]*render\(false\)/,
  '容器变宽后必须原地更新列宽和画布尺寸'
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
