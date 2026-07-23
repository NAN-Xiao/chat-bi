import assert from 'node:assert/strict'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import esbuild from 'esbuild'

const currentDir = dirname(fileURLToPath(import.meta.url))
const adapterPath = join(currentDir, 'roiDashboardViewAdapter.ts')
const build = await esbuild.build({
  entryPoints: [adapterPath],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const {
  createRoiDashboardViewInfo,
  dashboardViewInfoToRoiPayload,
  roiChartToComponentItem,
  roiChartToDashboardViewInfo,
  roiChartsToCanvasViewInfo,
} = await import(moduleUrl)

const config = {
  datasource_id: 8,
  datasource_name: 'ROI DS',
  can_execute: true,
  can_edit: true,
}
const chart = {
  id: '901',
  title: '收入 ROI',
  sql: 'select dt, roi from t',
  chart_type: 'line',
  chart_config: {
    xAxis: [{ value: 'dt' }],
    yAxis: [{ value: 'roi' }],
    series: [],
    sourceConfig: {
      sql: { builder: { timeField: 'dt' }, datasource: 99 },
      mcp: { token: 'secret' },
    },
  },
  layout_span: 'full',
  sort: 1,
  version: 3,
  query_result: {
    status: 'success',
    fields: ['dt', 'roi'],
    data: [{ dt: '2026-07-22', roi: 1.2 }],
    message: '',
  },
}

const viewInfo = roiChartToDashboardViewInfo(chart, config)
assert.equal(viewInfo.datasource, 8)
assert.equal(viewInfo.sourceConfig.sql.datasource, 8)
assert.deepEqual(viewInfo.chart.xAxis, [{ value: 'dt' }])
assert.deepEqual(viewInfo.chart.yAxis, [{ value: 'roi' }])
assert.deepEqual(viewInfo.data.data, chart.query_result.data)
assert.deepEqual(viewInfo.data.fields, chart.query_result.fields)
assert.equal(viewInfo.sourceConfig.sources.includes('external_mcp'), false)
assert.equal(viewInfo.sourceConfig.mcp, null)

const payload = dashboardViewInfoToRoiPayload(viewInfo, { version: 3, layoutSpan: 'full' })
assert.equal(payload.title, '收入 ROI')
assert.equal(payload.chart_type, 'line')
assert.equal(payload.version, 3)
assert.equal(JSON.stringify(payload.chart_config).includes('"datasource":8'), false)
assert.equal(chart.chart_config.sourceConfig.sql.datasource, 99, '转换不得修改原图表')

const legacyViewInfo = roiChartToDashboardViewInfo(
  {
    ...chart,
    chart_config: { x: 'legacy_dt', y: ['legacy_roi'], series: 'channel' },
  },
  config
)
assert.deepEqual(legacyViewInfo.chart.xAxis, [{ value: 'legacy_dt' }])
assert.deepEqual(legacyViewInfo.chart.yAxis, [{ value: 'legacy_roi' }])
assert.deepEqual(legacyViewInfo.chart.series, [{ value: 'channel' }])

const noAxisViewInfo = roiChartToDashboardViewInfo(
  { ...chart, chart_config: { columns: ['dt', 'roi'] } },
  config
)
assert.deepEqual(noAxisViewInfo.chart.xAxis, [], '缺少历史轴配置时不得自动选择字段')
assert.deepEqual(noAxisViewInfo.chart.yAxis, [], '缺少历史轴配置时不得自动选择字段')
assert.deepEqual(noAxisViewInfo.chart.series, [], '缺少历史轴配置时不得自动选择字段')

const created = createRoiDashboardViewInfo(config)
assert.equal(created.datasource, 8)
assert.deepEqual(created.sourceConfig.sources, ['sql'])
assert.equal(created.sourceConfig.primarySource, 'sql')
assert.equal(created.sourceConfig.mcp, null)
assert.equal(created.sourceConfig.sql.datasource, 8)
assert.equal(created.chart.type, 'table')
assert.deepEqual(created.chart.xAxis, [])
assert.deepEqual(created.chart.yAxis, [])

const componentItem = roiChartToComponentItem(chart)
assert.deepEqual(componentItem, {
  id: '901',
  component: 'SQView',
  label: '收入 ROI',
  propValue: '',
  x: 1,
  y: 1,
  sizeX: 12,
  sizeY: 6,
})

const canvasViewInfo = roiChartsToCanvasViewInfo([chart], config)
assert.deepEqual(Object.keys(canvasViewInfo), ['901'])
assert.equal(canvasViewInfo['901'].datasource, 8)
assert.equal(chart.chart_config.sourceConfig.sql.datasource, 99, '批量转换不得修改原图表')

console.log('ROI dashboard view adapter tests passed')
