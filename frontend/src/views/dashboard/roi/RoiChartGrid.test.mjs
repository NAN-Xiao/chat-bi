import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import esbuild from 'esbuild'

const gridPath = 'src/views/dashboard/roi/RoiChartGrid.vue'
const cardPath = 'src/views/dashboard/roi/RoiChartCard.vue'
const behaviorPath = 'src/views/dashboard/roi/roiChartGridBehavior.ts'
const panelPath = 'src/views/dashboard/roi/RoiDashboardPanel.vue'

assert.equal(existsSync(gridPath), true, '必须提供 ROI 固定网格')
assert.equal(existsSync(cardPath), true, '必须提供 ROI 图表卡片')
assert.equal(existsSync(behaviorPath), true, '必须提供可独立验证的网格行为')

const grid = readFileSync(gridPath, 'utf8')
const card = readFileSync(cardPath, 'utf8')
const panel = readFileSync(panelPath, 'utf8')
assert.match(grid, /grid-template-columns:\s*repeat\(6,\s*minmax\(0,\s*1fr\)\)/)
assert.match(grid, /grid-auto-rows:\s*320px/, 'ROI 网格必须使用稳定的固定行高')
assert.doesNotMatch(
  grid,
  /grid-auto-rows:\s*minmax\(320px,\s*auto\)/,
  'ROI 网格不得再被表格内容持续撑高'
)
assert.match(grid, /\.roi-chart-grid__item\s*\{[\s\S]*?height:\s*320px/, '网格项必须锁定为一行高度')
assert.match(grid, /layout_span[\s\S]*full[\s\S]*half[\s\S]*third/)
assert.doesNotMatch(grid, /canvasData|component_data|canvas_view_info/)
assert.match(card, /当前账号无此数据源权限/)
assert.match(card, /v-if="chart\.can_execute/)
assert.match(card, /RefreshRight/, 'ROI 图表卡片必须提供刷新图标')
assert.match(card, /重新执行 SQL/, '刷新按钮必须明确说明会重新执行 SQL')
assert.match(card, /refresh:\s*\[chart:\s*RoiChart\]/, '卡片必须向上发出单图刷新事件')
assert.match(card, /:loading="refreshing"/, '单图刷新期间按钮必须展示加载状态')
assert.match(grid, /refresh:\s*\[chart:\s*RoiChart\]/, '网格必须转发单图刷新事件')
assert.match(grid, /@refresh="emit\('refresh', \$event\)"/, '网格必须把卡片刷新事件交给面板')
assert.match(card, /<el-date-picker/, 'ROI 图表卡片必须提供日期范围选择器')
assert.match(card, /type="daterange"/)
assert.match(card, /value-format="YYYY-MM-DD"/)
assert.match(card, /:disabled="!dateRangeEnabled \|\| refreshing"/)
assert.match(
  card,
  /['\"]?date-range-change['\"]?:\s*\[chart:\s*RoiChart,\s*dateRange:\s*RoiDateRange\]/
)
assert.match(
  grid,
  /['\"]?date-range-change['\"]?:\s*\[chart:\s*RoiChart,\s*dateRange:\s*RoiDateRange\]/
)
assert.match(
  grid,
  /@date-range-change="\(item, dateRange\) => emit\('date-range-change', item, dateRange\)"/
)
assert.match(panel, /const chartDateRanges = ref<Record<string, RoiDateRange>>/)
assert.match(panel, /buildRoiChartPreviewRequest\([\s\S]*chart,[\s\S]*dateRange/)
assert.match(
  panel,
  /async function changeChartDateRange\(chart: RoiChart, dateRange: RoiDateRange\)/
)
assert.match(panel, /@date-range-change="changeChartDateRange"/)
assert.match(panel, /async function refreshCurrentCharts\(\)/)
assert.match(panel, /@click="refreshCurrentCharts\(\)"/)
assert.match(
  card,
  /\.roi-chart-card__body\s*\{[\s\S]*?display:\s*flex/,
  '图表内容区必须为图表挂载容器提供可用高度'
)
assert.match(
  card,
  /<el-dropdown[\s\S]*?<el-button[^>]*aria-label="设置宽度"[^>]*title="设置宽度"/,
  '宽度下拉必须直接使用带原生提示的按钮，避免 Tooltip role 警告或嵌套按钮'
)
assert.doesNotMatch(card, /useDashboardStore|dashboardStoreWithOut|document\.getElementById/)

const build = await esbuild.build({
  entryPoints: [behaviorPath],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const {
  buildRoiChartOrderItems,
  canManageRoiChart,
  mergeReorderedRoiCharts,
  moveRoiChart,
  buildRoiChartPreviewRequest,
  defaultRoiDateRange,
  hasRoiDateRangePlaceholders,
  replaceRoiChartPreviewResult,
  roiLayoutSpanColumns,
} = await import(moduleUrl)

assert.deepEqual(roiLayoutSpanColumns, { full: 6, half: 3, third: 2 })
assert.deepEqual(defaultRoiDateRange(new Date(2026, 6, 17)), ['2026-07-10', '2026-07-16'])
assert.equal(
  hasRoiDateRangePlaceholders(
    'SELECT * FROM t WHERE dt >= {{start_date_yyyymmdd}} AND dt <= {{end_date_yyyymmdd}}'
  ),
  true
)
assert.equal(
  hasRoiDateRangePlaceholders(
    'SELECT * FROM t WHERE created_at >= {{start_date}} AND created_at <= {{end_date}}'
  ),
  true
)
assert.equal(
  hasRoiDateRangePlaceholders('SELECT * FROM t WHERE dt >= {{start_date_yyyymmdd}}'),
  false
)
assert.equal(hasRoiDateRangePlaceholders('SELECT 1'), false)

const charts = [
  { id: '901', layout_span: 'full', sort: 10, version: 2, can_execute: true, can_edit: true },
  { id: '902', layout_span: 'half', sort: 20, version: 4, can_execute: true, can_edit: true },
  { id: '903', layout_span: 'third', sort: 30, version: 7, can_execute: true, can_edit: true },
]
const reordered = moveRoiChart(charts, 2, 0)
assert.deepEqual(
  reordered.map((chart) => chart.id),
  ['903', '901', '902']
)
assert.deepEqual(
  charts.map((chart) => chart.id),
  ['901', '902', '903'],
  '排序不得修改输入数组'
)

const payload = buildRoiChartOrderItems(reordered)
assert.deepEqual(payload, [
  { id: '903', sort: 1, layout_span: 'third', version: 7 },
  { id: '901', sort: 2, layout_span: 'full', version: 2 },
  { id: '902', sort: 3, layout_span: 'half', version: 4 },
])
for (const item of payload) {
  assert.deepEqual(Object.keys(item).sort(), ['id', 'layout_span', 'sort', 'version'])
  assert.equal(
    'x' in item || 'y' in item || 'component_data' in item || 'canvas_view_info' in item,
    false
  )
}

assert.equal(canManageRoiChart(charts[0], true), true)
assert.equal(canManageRoiChart({ ...charts[0], can_execute: false }, true), false)
assert.equal(canManageRoiChart({ ...charts[0], can_edit: false }, true), false)
assert.equal(canManageRoiChart(charts[0], false), false)

{
  const chart = {
    ...charts[0],
    title: 'ROI 明细',
    sql: 'select 1',
    chart_type: 'table',
    chart_config: { columns: ['value'] },
  }
  assert.deepEqual(buildRoiChartPreviewRequest(chart), {
    title: 'ROI 明细',
    sql: 'select 1',
    chart_type: 'table',
    chart_config: { columns: ['value'] },
    layout_span: 'full',
  })
}

{
  const result = { status: 'success', fields: ['value'], data: [{ value: 9 }], message: '' }
  const current = [
    {
      ...charts[0],
      query_result: { status: 'success', fields: ['value'], data: [{ value: 1 }], message: '' },
    },
    { ...charts[1], query_result: null },
  ]
  const updated = replaceRoiChartPreviewResult(current, '901', result)
  assert.deepEqual(updated[0].query_result, result)
  assert.equal(updated[0].error, null)
  assert.equal(updated[1], current[1], '单图刷新不得替换其他图表对象')
  assert.notEqual(updated, current, '单图刷新不得原地修改输入数组')
}

{
  const current = [
    {
      ...charts[0],
      query_result: { status: 'success', fields: ['value'], data: [{ value: 7 }], message: '' },
      error: null,
    },
  ]
  const response = [
    {
      ...charts[0],
      sort: 2,
      version: 3,
      layout_span: 'half',
      status: 0,
      can_execute: false,
      can_edit: false,
      error: '最新权限错误',
      query_result: null,
    },
  ]
  const merged = mergeReorderedRoiCharts(current, response)
  assert.equal(merged[0].sort, 2)
  assert.equal(merged[0].version, 3)
  assert.equal(merged[0].layout_span, 'half')
  assert.equal(merged[0].status, 0)
  assert.equal(merged[0].can_execute, false)
  assert.equal(merged[0].can_edit, false)
  assert.equal(merged[0].error, '最新权限错误')
  assert.deepEqual(merged[0].query_result, current[0].query_result, '排序响应不得清空已渲染结果')
}

{
  const oldResult = { status: 'success', fields: ['value'], data: [{ value: 1 }], message: '' }
  const newResult = { status: 'success', fields: ['value'], data: [{ value: 2 }], message: '' }
  const merged = mergeReorderedRoiCharts(
    [{ ...charts[0], query_result: oldResult }],
    [{ ...charts[0], query_result: newResult }]
  )
  assert.deepEqual(merged[0].query_result, newResult, '服务端返回非空结果时必须以服务端为准')
}

console.log('ROI chart grid tests passed')
