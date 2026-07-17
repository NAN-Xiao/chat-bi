import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import esbuild from 'esbuild'

const gridPath = 'src/views/dashboard/roi/RoiChartGrid.vue'
const cardPath = 'src/views/dashboard/roi/RoiChartCard.vue'
const behaviorPath = 'src/views/dashboard/roi/roiChartGridBehavior.ts'

assert.equal(existsSync(gridPath), true, '必须提供 ROI 固定网格')
assert.equal(existsSync(cardPath), true, '必须提供 ROI 图表卡片')
assert.equal(existsSync(behaviorPath), true, '必须提供可独立验证的网格行为')

const grid = readFileSync(gridPath, 'utf8')
const card = readFileSync(cardPath, 'utf8')
assert.match(grid, /grid-template-columns:\s*repeat\(6,\s*minmax\(0,\s*1fr\)\)/)
assert.match(grid, /layout_span[\s\S]*full[\s\S]*half[\s\S]*third/)
assert.doesNotMatch(grid, /canvasData|component_data|canvas_view_info/)
assert.match(card, /当前账号无此数据源权限/)
assert.match(card, /v-if="chart\.can_execute/)
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
  roiLayoutSpanColumns,
} = await import(moduleUrl)

assert.deepEqual(roiLayoutSpanColumns, { full: 6, half: 3, third: 2 })

const charts = [
  { id: '901', layout_span: 'full', sort: 10, version: 2, can_execute: true, can_edit: true },
  { id: '902', layout_span: 'half', sort: 20, version: 4, can_execute: true, can_edit: true },
  { id: '903', layout_span: 'third', sort: 30, version: 7, can_execute: true, can_edit: true },
]
const reordered = moveRoiChart(charts, 2, 0)
assert.deepEqual(reordered.map((chart) => chart.id), ['903', '901', '902'])
assert.deepEqual(charts.map((chart) => chart.id), ['901', '902', '903'], '排序不得修改输入数组')

const payload = buildRoiChartOrderItems(reordered)
assert.deepEqual(payload, [
  { id: '903', sort: 1, layout_span: 'third', version: 7 },
  { id: '901', sort: 2, layout_span: 'full', version: 2 },
  { id: '902', sort: 3, layout_span: 'half', version: 4 },
])
for (const item of payload) {
  assert.deepEqual(Object.keys(item).sort(), ['id', 'layout_span', 'sort', 'version'])
  assert.equal('x' in item || 'y' in item || 'component_data' in item || 'canvas_view_info' in item, false)
}

assert.equal(canManageRoiChart(charts[0], true), true)
assert.equal(canManageRoiChart({ ...charts[0], can_execute: false }, true), false)
assert.equal(canManageRoiChart({ ...charts[0], can_edit: false }, true), false)
assert.equal(canManageRoiChart(charts[0], false), false)

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
