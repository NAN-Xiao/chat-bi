import assert from 'node:assert/strict'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import esbuild from 'esbuild'

const currentDir = dirname(fileURLToPath(import.meta.url))
const configPath = join(currentDir, 'roiChartConfig.ts')
const build = await esbuild.build({
  entryPoints: [configPath],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const {
  createRoiEditorRequestGuard,
  getRoiChartSaveErrorMessage,
  hydrateRoiChartForm,
  roiChartFormSignature,
  serializeRoiChartForm,
} = await import(moduleUrl)

const chart = {
  id: 'chart-1',
  title: '渠道 ROI',
  sql: ' SELECT channel, day, cost, revenue FROM roi_detail ',
  chart_type: 'line',
  chart_config: {
    x: 'day',
    y: ['cost', 'revenue'],
    series: 'channel',
    columns: ['day', 'channel', 'cost', 'revenue'],
    pivot: {
      enabled: true,
      time_field: 'day',
      metric_fields: ['cost', 'revenue'],
      group_field: 'channel',
      granularity: 'day',
    },
    insight: {
      enabled: true,
      comparison: { enabled: true, metrics: ['change', 'changeRate'] },
      aggregate: { enabled: true, metrics: ['sum', 'avg'] },
    },
  },
  layout_span: 'half',
  version: 7,
}

const form = hydrateRoiChartForm(chart)
const payload = serializeRoiChartForm(form)
assert.deepEqual(payload, {
  title: '渠道 ROI',
  sql: 'SELECT channel, day, cost, revenue FROM roi_detail',
  chart_type: 'line',
  chart_config: chart.chart_config,
  layout_span: 'half',
  version: 7,
})
assert.equal('datasource_id' in payload, false)
assert.equal('tenant_id' in payload, false)
assert.equal(JSON.stringify(payload).includes('mcp'), false)

const createPayload = serializeRoiChartForm({ ...form, version: undefined })
assert.equal('version' in createPayload, false, 'create DTO 不得包含 version')
assert.equal(createPayload.chart_config.pivot.enabled, true)
assert.equal(createPayload.chart_config.insight.enabled, true)

const signature = roiChartFormSignature(form)
assert.equal(
  roiChartFormSignature(hydrateRoiChartForm(chart)),
  signature,
  '相同业务配置签名必须稳定'
)
for (const changed of [
  { ...form, sql: `${form.sql} WHERE cost > 0` },
  { ...form, title: '新标题' },
  { ...form, chartType: 'bar' },
  { ...form, columns: [...form.columns, 'profit'] },
  { ...form, x: 'channel' },
  { ...form, y: ['revenue'] },
  { ...form, series: '' },
  { ...form, pivotEnabled: false },
  { ...form, pivot: { ...form.pivot, granularity: 'month' } },
  { ...form, insightEnabled: false },
  { ...form, insight: { ...form.insight, aggregate: { enabled: false, metrics: [] } } },
  { ...form, layoutSpan: 'full' },
]) {
  assert.notEqual(roiChartFormSignature(changed), signature, '任一业务字段变化都必须使预览失效')
}

{
  const guard = createRoiEditorRequestGuard()
  guard.beginSession()
  const oldPreview = guard.beginPreview(signature)
  const newSignature = roiChartFormSignature({ ...form, title: '更新后标题' })
  const newPreview = guard.beginPreview(newSignature)
  assert.equal(
    guard.markPreviewSucceeded(oldPreview, signature),
    false,
    '旧 preview 响应不得授权保存'
  )
  assert.equal(guard.markPreviewSucceeded(newPreview, newSignature), true)
  assert.equal(guard.canSave(newSignature), true)
  assert.equal(guard.canSave(signature), false)
}

{
  const guard = createRoiEditorRequestGuard()
  guard.beginSession()
  const preview = guard.beginPreview(signature)
  assert.equal(guard.markPreviewSucceeded(preview, signature), true)
  const oldSave = guard.beginSave(signature)
  assert.notEqual(oldSave, null)
  guard.closeSession()
  guard.beginSession()
  assert.equal(guard.markSaved(oldSave), false, '旧保存响应不得关闭或完成新会话')
}

{
  const guard = createRoiEditorRequestGuard()
  guard.beginSession()
  const preview = guard.beginPreview(signature)
  assert.equal(guard.markPreviewSucceeded(preview, signature), true)
  const save = guard.beginSave(signature)
  guard.invalidateRequests()
  assert.equal(guard.isActivePreview(preview), false)
  assert.equal(guard.markSaved(save), false, '动态撤权必须使在途保存失效')
  assert.equal(guard.markPreviewSucceeded(preview, signature), false, '动态撤权必须使旧预览失效')
  assert.equal(guard.canSave(signature), false)
}

assert.equal(
  getRoiChartSaveErrorMessage({ response: { status: 409, data: { detail: 'password=secret' } } }),
  '数据已被其他人修改，请刷新后重试'
)
assert.equal(
  getRoiChartSaveErrorMessage({ response: { status: 500, data: { detail: 'Traceback' } } }),
  '保存 ROI 图表失败，请稍后重试'
)

console.log('ROI chart config tests passed')
