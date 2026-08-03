import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const component = readFileSync('src/views/chat/component/ChartComponent.vue', 'utf8')
const dashboardView = readFileSync('src/views/dashboard/components/sq-view/index.vue', 'utf8')
const table = readFileSync('src/views/chat/component/charts/Table.ts', 'utf8')

assert.match(component, /surface\?:\s*ChartSurface/, 'ChartComponent 必须声明调用表面')
assert.match(component, /hasOuterTitle\?:\s*boolean/, '调用方必须能声明外层已有标题')
assert.match(component, /buildChartLayoutContext\(/, '组件必须从自身容器尺寸构建布局上下文')
assert.match(
  component,
  /chartInstance\.layoutContext\s*=\s*currentLayoutContext\.value/,
  '实例初始化前必须收到布局上下文'
)
assert.match(component, /previousDensity:/, '密度切换必须使用前一档做边界稳定')
assert.match(
  component,
  /params\.type\s*!==\s*['"]table['"]/,
  'table 仍由自身 ResizeObserver 原地调整'
)

assert.match(
  table,
  /changeSheetSize\(contentWidth, viewportHeight\)[\s\S]*?render\(false\)/,
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
  /function resolveTableViewportHeight\([\s\S]*?Math\.floor\([\s\S]*?TABLE_DATA_CELL_HEIGHT/,
  'S2 表格高度必须对齐完整数据行，避免卡片底部显示半行'
)
assert.match(
  table,
  /function resolveTableViewportHeight\([\s\S]*Math\.max\(containerHeight, TABLE_HEADER_CELL_HEIGHT\)/,
  '极小高度下 S2 viewport 至少保住表头，内容区由自身滚动处理'
)
assert.doesNotMatch(
  dashboardView,
  /\.chart-loading-info\s*\{[^}]*min-height:\s*140px/s,
  '加载态不得撑破小尺寸抽屉'
)
assert.match(
  table,
  /const viewportHeight = resolveTableViewportHeight\(height\)[\s\S]*?height: viewportHeight[\s\S]*?changeSheetSize\(contentWidth, viewportHeight\)/,
  '容器缩放时必须使用完整行高度更新 S2 画布'
)
assert.match(
  table,
  /const viewportHeight = resolveTableViewportHeight\(containerHeight\)[\s\S]*?height: viewportHeight/,
  'S2 首次渲染必须使用完整行高度'
)
assert.match(
  table,
  /function resolveTableContainerSize\([\s\S]*?clientWidth[\s\S]*?clientHeight/,
  'S2 表格尺寸必须来自自身挂载容器的实际可用宽高'
)
assert.match(
  table,
  /this\.resizeObserver\.observe\(this\.container\)/,
  'S2 表格必须监听自身挂载容器，而不是带内边距的父容器'
)
assert.doesNotMatch(
  table,
  /this\.resizeObserver\.observe\(this\.container\.parentElement\)/,
  'S2 表格不得继续使用父容器尺寸'
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
  /debounce\(\s*async\s*\(width\?: number, height\?: number\)[\s\S]*this\.table\.setOptions\([\s\S]*colCell:[\s\S]*width: columnWidth[\s\S]*dataCell:[\s\S]*width: columnWidth[\s\S]*changeSheetSize\(contentWidth, viewportHeight\)[\s\S]*render\(false\)/,
  '容器变宽后必须原地更新列宽和画布尺寸'
)
assert.match(
  component,
  /new ResizeObserver\([\s\S]*?params\.type\s*!==\s*['"]table['"][\s\S]*?scheduleRenderChart/,
  'ChartComponent 的尺寸监听不得销毁并重建 table 图表'
)
assert.match(
  component,
  /function handlePageRestore\(\)[\s\S]*?params\.type\s*===\s*['"]table['"][\s\S]*?hasRenderedOutput\(\)[\s\S]*?return[\s\S]*?scheduleRenderChart\(120\)/,
  '页面恢复时，已渲染的 table 图表不得销毁并重建'
)
assert.match(
  dashboardView,
  /new ResizeObserver\([\s\S]*?chartType\.value\s*!==\s*['"]table['"][\s\S]*?scheduleRenderChart/,
  '看板外层尺寸监听不得再次销毁并重建 table 图表'
)

console.log('ChartComponent resize tests passed')
