import assert from 'node:assert/strict'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import esbuild from 'esbuild'

const currentDir = dirname(fileURLToPath(import.meta.url))
const configPath = join(currentDir, 'roiChartConfig.ts')
const previewRunnerPath = join(currentDir, 'roiChartPreviewRunner.ts')
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
  replaceRoiChartForm,
  roiChartFormSignature,
  serializeRoiChartForm,
} = await import(moduleUrl)

const chart = {
  id: 'chart-1',
  title: '渠道 ROI',
  sql: ' SELECT channel, day, cost, revenue FROM roi_detail ',
  chart_type: 'line',
  chart_config: {
    showLabel: true,
    future_config: { mode: 'dense', nested: { threshold: 9 } },
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

{
  const explicitWins = serializeRoiChartForm({
    ...form,
    extraChartConfig: {
      ...form.extraChartConfig,
      x: 'stale_x',
      pivot: { enabled: false, time_field: 'stale_time' },
    },
  })
  assert.equal(explicitWins.chart_config.x, form.x)
  assert.deepEqual(explicitWins.chart_config.pivot, form.pivot)
}

{
  const unsafe = hydrateRoiChartForm({
    ...chart,
    chart_config: {
      ...chart.chart_config,
      datasource_id: 10,
      tenant_id: 20,
      external_mcp: { token: 'secret' },
      mcpServerId: 'server-secret',
      future_config: { ...chart.chart_config.future_config, mcpTool: 'tool-secret' },
    },
  })
  const serialized = JSON.stringify(serializeRoiChartForm(unsafe))
  for (const forbidden of [
    'datasource_id',
    'tenant_id',
    'external_mcp',
    'mcpServerId',
    'mcpTool',
  ]) {
    assert.equal(serialized.includes(forbidden), false, `${forbidden} 不得进入 payload`)
  }
}

{
  const state = hydrateRoiChartForm(chart)
  replaceRoiChartForm(state, null)
  assert.equal(state.version, undefined, 'edit→create 必须显式清除旧 version')
  assert.equal('version' in serializeRoiChartForm(state), false)
  replaceRoiChartForm(state, chart)
  assert.equal(state.version, 7, 'create→edit 必须恢复服务端数值 version')
  assert.equal(serializeRoiChartForm(state).version, 7)
}

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
  { ...form, pivot: { ...form.pivot, metric_fields: ['revenue'] } },
  { ...form, pivot: { ...form.pivot, group_enabled: true } },
  { ...form, insightEnabled: false },
  { ...form, insight: { ...form.insight, aggregate: { enabled: false, metrics: [] } } },
  { ...form, layoutSpan: 'full' },
  { ...form, extraChartConfig: { ...form.extraChartConfig, showLabel: false } },
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

const runnerBuild = await esbuild.build({
  entryPoints: [previewRunnerPath],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
})
const runnerUrl = `data:text/javascript;base64,${Buffer.from(runnerBuild.outputFiles[0].text).toString('base64')}`
const { createRoiChartPreviewRunner, ROI_CHART_PREVIEW_ERROR_MESSAGE } = await import(runnerUrl)

const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

{
  const guard = createRoiEditorRequestGuard()
  guard.beginSession()
  let signatureValue = 'A'
  const requests = [deferred(), deferred()]
  const results = []
  const errors = []
  const loading = []
  let requestIndex = 0
  const runner = createRoiChartPreviewRunner({
    guard,
    request: () => requests[requestIndex++].promise,
    getCurrentSignature: () => signatureValue,
    onSuccess: (result) => results.push(result),
    onError: (message) => errors.push(message),
    onLoading: (value) => loading.push(value),
  })

  const runA = runner.run({ sql: 'A' }, 'A')
  signatureValue = 'B'
  const runB = runner.run({ sql: 'B' }, 'B')
  requests[0].resolve({
    status: 'success',
    fields: ['old_secret'],
    data: [{ old_secret: 'password=leak' }],
    message: 'postgres://root:secret@host/db',
  })
  await runA
  assert.deepEqual(results, [], 'A 旧成功不能写 fields/data')
  assert.deepEqual(errors, [])
  assert.deepEqual(loading, [true], 'A finally 不能清除 B loading')

  requests[1].resolve({
    status: 'success',
    fields: ['current'],
    data: [{ current: 2 }],
    message: 'driver=postgres://root:secret@host/db',
  })
  await runB
  assert.deepEqual(
    results.map((item) => item.fields),
    [['current']]
  )
  assert.equal(results[0].message, '', '成功响应的驱动 message 也不得进入编辑器状态')
  assert.deepEqual(loading, [true, false])
  assert.equal(guard.canSave('B'), true)
}

{
  const guard = createRoiEditorRequestGuard()
  guard.beginSession()
  let signatureValue = 'A'
  const requests = [deferred(), deferred()]
  const events = []
  let requestIndex = 0
  const runner = createRoiChartPreviewRunner({
    guard,
    request: () => requests[requestIndex++].promise,
    getCurrentSignature: () => signatureValue,
    onSuccess: (result) => events.push(`success:${result.fields[0]}`),
    onError: (message) => events.push(`error:${message}`),
    onLoading: (value) => events.push(`loading:${value}`),
  })
  const runA = runner.run({}, 'A')
  signatureValue = 'B'
  const runB = runner.run({}, 'B')
  requests[0].reject(new Error('SQL and password leaked by old request'))
  await runA
  assert.deepEqual(events, ['loading:true'], 'A 旧 error/finally 不能污染 B')
  requests[1].resolve({ status: 'success', fields: ['B'], data: [{ B: 1 }], message: '' })
  await runB
  assert.deepEqual(events, ['loading:true', 'success:B', 'loading:false'])
}

for (const failure of [
  {
    kind: 'result',
    value: { status: 'failed', fields: [], data: [], message: 'SQL: DROP; password=x' },
  },
  { kind: 'throw', value: { response: { data: { detail: 'postgres://root:secret@host/db' } } } },
]) {
  const guard = createRoiEditorRequestGuard()
  guard.beginSession()
  const errors = []
  const runner = createRoiChartPreviewRunner({
    guard,
    request: async () => {
      if (failure.kind === 'throw') throw failure.value
      return failure.value
    },
    getCurrentSignature: () => 'current',
    onSuccess: () => assert.fail('失败预览不得发布成功结果'),
    onError: (message) => errors.push(message),
    onLoading: () => {},
  })
  await runner.run({}, 'current')
  assert.deepEqual(errors, [ROI_CHART_PREVIEW_ERROR_MESSAGE])
  assert.equal(errors[0].includes('secret') || errors[0].includes('DROP'), false)
}

{
  const guard = createRoiEditorRequestGuard()
  guard.beginSession()
  const request = deferred()
  const events = []
  const runner = createRoiChartPreviewRunner({
    guard,
    request: () => request.promise,
    getCurrentSignature: () => 'same',
    onSuccess: () => events.push('success'),
    onError: () => events.push('error'),
    onLoading: (value) => events.push(`loading:${value}`),
  })
  const pending = runner.run({}, 'same')
  runner.invalidate()
  request.reject(new Error('old driver failure'))
  await pending
  assert.deepEqual(events, ['loading:true', 'loading:false'], '关闭或切换后旧失败不得污染新会话')
}
assert.equal(
  getRoiChartSaveErrorMessage({ response: { status: 500, data: { detail: 'Traceback' } } }),
  '保存 ROI 图表失败，请稍后重试'
)

console.log('ROI chart config tests passed')
