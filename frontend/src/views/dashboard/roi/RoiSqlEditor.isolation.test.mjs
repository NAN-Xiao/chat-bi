import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import esbuild from 'esbuild'

const currentDir = dirname(fileURLToPath(import.meta.url))
const editorPath = join(currentDir, 'RoiSqlEditor.vue')
const panelPath = join(currentDir, 'RoiDashboardPanel.vue')

assert.equal(existsSync(editorPath), true, '必须提供 ROI SQL 编辑器适配器')

const source = readFileSync(editorPath, 'utf8')
const panel = readFileSync(panelPath, 'utf8')

assert.match(
  source,
  /import DashboardSqlEditor from '@\/views\/dashboard\/common\/DashboardSqlEditor\.vue'/
)
assert.match(source, /:fixed-datasource-id="config\?\.datasource_id"/)
assert.match(source, /:allow-external-sources="false"/)
assert.match(source, /:apply-executor="persistRoiChart"/)
assert.match(source, /:preview-executor="previewRoiChart"/)
assert.match(source, /:strict-field-mapping="true"/)
assert.match(source, /@applied="handleApplied"/)
assert.match(source, /createRoiDashboardViewInfo/)
assert.match(source, /roiChartToDashboardViewInfo/)
assert.match(source, /dashboardViewInfoToRoiPayload/)
assert.match(source, /roiDashboardApi\.createChart/)
assert.match(source, /roiDashboardApi\.updateChart/)
assert.match(source, /roiDashboardApi\.previewChart/)
assert.doesNotMatch(source, /<el-drawer|<el-tabs|<el-form|<el-date-picker/)
assert.doesNotMatch(source, /chartTypes|insightComparisonOptions|roi-sql-editor__/)
assert.doesNotMatch(source, /useDashboardStore|canvasData|canvasViewInfo/)

const persistModuleMatch = source.match(/<script lang="ts">\s*([\s\S]*?)<\/script>/)
assert.ok(persistModuleMatch, '必须提供可独立测试的 ROI 保存协调器')
const transformed = await esbuild.transform(persistModuleMatch[1], {
  loader: 'ts',
  format: 'esm',
  target: 'es2022',
})
const persistModuleUrl = `data:text/javascript;base64,${Buffer.from(transformed.code).toString('base64')}`
const { createPersistRoiChart, createRoiChartPreviewExecutor } = await import(persistModuleUrl)

{
  const previewCalls = []
  const previewRoiChart = createRoiChartPreviewExecutor({
    getDashboardId: () => 'dashboard-1',
    getLayoutSpan: () => 'half',
    previewChart: async (dashboardId, payload) => {
      previewCalls.push({ dashboardId, payload })
      return {
        status: 'success',
        fields: ['period'],
        data: [{ period: '2026-07-01' }],
        message: '',
      }
    },
  })
  const result = await previewRoiChart({
    datasource: 8,
    sql: 'SELECT DATE_ADD(dt, period) AS period FROM roi_events',
    title: 'ROI 趋势',
    chartType: 'line',
    chartConfig: { xAxis: [{ value: 'period' }] },
  })

  assert.deepEqual(previewCalls, [
    {
      dashboardId: 'dashboard-1',
      payload: {
        title: 'ROI 趋势',
        sql: 'SELECT DATE_ADD(dt, period) AS period FROM roi_events',
        chart_type: 'line',
        chart_config: { xAxis: [{ value: 'period' }] },
        layout_span: 'half',
      },
    },
  ])
  assert.deepEqual(result, {
    status: 'success',
    fields: ['period'],
    data: [{ period: '2026-07-01' }],
    message: '',
  })
}

let currentChart = null
const calls = []
const savedCharts = []
const errors = []
const persistRoiChart = createPersistRoiChart({
  getDashboardId: () => 'dashboard-1',
  getChart: () => currentChart,
  toPayload: (viewInfo, options) => ({ marker: viewInfo.marker, ...options }),
  createChart: async (dashboardId, payload) => {
    calls.push({ kind: 'create', dashboardId, payload })
    return { id: 'created', version: 1 }
  },
  updateChart: async (dashboardId, chartId, payload) => {
    calls.push({ kind: 'update', dashboardId, chartId, payload })
    return { id: chartId, version: payload.version + 1 }
  },
  onSaved: (chart) => savedCharts.push(chart),
  onError: (error) => errors.push(error),
})

assert.equal(await persistRoiChart({ marker: 'new' }), true)
assert.deepEqual(calls[0], {
  kind: 'create',
  dashboardId: 'dashboard-1',
  payload: { marker: 'new', layoutSpan: 'full' },
})
assert.deepEqual(savedCharts, [{ id: 'created', version: 1 }])

currentChart = { id: 'chart-9', version: 7, layout_span: 'half' }
assert.equal(await persistRoiChart({ marker: 'edit' }), true)
assert.deepEqual(calls[1], {
  kind: 'update',
  dashboardId: 'dashboard-1',
  chartId: 'chart-9',
  payload: { marker: 'edit', version: 7, layoutSpan: 'half' },
})
assert.deepEqual(savedCharts.at(-1), { id: 'chart-9', version: 8 })

const savedCountBeforeFailure = savedCharts.length
const failed = createPersistRoiChart({
  getDashboardId: () => 'dashboard-1',
  getChart: () => null,
  toPayload: () => ({ layout_span: 'full' }),
  createChart: async () => {
    throw new Error('create failed')
  },
  updateChart: async () => assert.fail('新建失败不得调用 updateChart'),
  onSaved: (chart) => savedCharts.push(chart),
  onError: (error) => errors.push(error),
})
assert.equal(await failed({}), false)
assert.equal(savedCharts.length, savedCountBeforeFailure, 'API 失败不得发布 saved')
assert.equal(errors.at(-1)?.message, 'create failed')

assert.match(panel, /<RoiSqlEditor/)
assert.match(panel, /:dashboard-id="editorState\.dashboardId"/)
assert.match(panel, /@saved="handleChartSaved"/)
assert.doesNotMatch(panel, /DashboardSqlEditor\.vue|useDashboardStore|canvasData|canvasViewInfo/)

console.log('ROI SQL editor shared drawer tests passed')
