import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('./DashboardSqlEditor.vue', import.meta.url), 'utf8')
const script = source.slice(source.indexOf('>') + 1, source.indexOf('</script>'))
const ast = ts.createSourceFile('editor.ts', script, ts.ScriptTarget.Latest, true)
const names = new Set(['generateBuilderAiSql', 'generateAndPreviewBuilderSql', 'beginEditorExecution',
  'finishEditorExecution', 'cancelBuilderSqlGeneration', 'clearBuilderLoading', 'closeDrawer', 'generatedSqlMatchesBuilderMetrics'])
const previewNames = ['previewAndPersistBuilderDraft', 'previewSqlSource', 'previewMcpSource', 'runPreview',
  'applyPreviewSnapshot', 'updatePreviewResult', 'updateSourcePreviewResult', 'previewResultSnapshot',
  'getPreviewResultFields', 'setSourceResult', 'persistEditorDraftToViewInfo', 'writeEditorStateToViewInfo',
  'sourceResultForSave']
const declarations = (realPreview) => ast.statements.filter((node) =>
  (ts.isFunctionDeclaration(node) && (names.has(node.name?.text) || realPreview && previewNames.includes(node.name?.text))) ||
  (ts.isVariableStatement(node) && node.declarationList.declarations.some((declaration) =>
    ['builderGenerationController', 'builderGenerationActive', 'visible'].includes(declaration.name.getText(ast))
  )) ||
  (ts.isExpressionStatement(node) && ts.isCallExpression(node.expression) &&
    node.expression.expression.getText(ast) === 'onBeforeUnmount')
).map((node) => node.getText(ast)).join('\n')

function editor({ realPreview = false, pivot = false, mixed = false } = {}) {
  const pending = []
  const pendingPreviews = []
  const applied = []
  const unmountCallbacks = []
  const warnings = []
  let previews = 0
  const context = vm.createContext({
    AbortController,
    props: { modelValue: true, viewInfo: {} },
    computed: (definition) => ({ get value() { return definition.get() }, set value(value) { definition.set(value) } }),
    emits: (event, value) => { if (event === 'applied') applied.push(value); else context.props.modelValue = value },
    onBeforeUnmount: (callback) => { unmountCallbacks.push(callback) },
    ref: (value) => ({ value }),
    canUseSqlEditor: { value: true }, selectedExecutionDatasourceId: { value: 7 },
    builderLoading: { value: false }, loadingText: { value: '' }, loading: { value: false },
    blockMissingFixedTimeField: () => false, shouldUseDashboardDateParameters: () => false,
    sqlBuilder: { analysisModel: 'event', activeTab: 'builder', metricItems: [] },
    form: { sql: 'previous SQL', title: 'existing', chartType: 'table', sourceTypes: ['sql'], pivotEnabled: pivot, mcpTool: 'fixture' },
    setLoadingPhase: async () => { context.builderLoading.value = true },
    showLocalBuilderAgentAdvice: () => {}, collectBuilderAiContext: () => ({}),
    dashboardApi: {
      generate_ai_sql: (_payload, options) => new Promise((resolve, reject) => {
        pending.push({ options, resolve, reject })
      }),
      preview_sql: (_payload, options) => new Promise((resolve, reject) => {
        pendingPreviews.push({ options, resolve, reject, kind: 'sql' })
      }),
    },
    chineseErrorMessage: () => 'failed', collectLocalBuilderConfigIssues: () => ({ suggestions: [] }),
    setBuilderAgentAdvice: (value) => { warnings.push(value) }, inferBuilderIntentText: () => '',
    builderSqlGenerationFailureMessage: 'failed',
    ElMessage: { success: () => {}, warning: (value) => { warnings.push(value) }, error: (value) => { warnings.push(value) } },
    updateBuilderAgentAdviceFromResult: () => {}, builderAgentBlockingIssues: () => [],
    generatedSqlMatchesBuilderMetrics: () => true,
    stopBuilderExecutionWithAdvice: () => {}, resultAdviceItems: () => [],
    analysisResultDisplayNames: { value: {} }, normalizeAnalysisResultDisplayNames: () => ({}),
    syncDashboardDateParameterUsage: () => {},
    previewAndPersistBuilderDraft: async () => { previews++ },
    unique: (items) => [...new Set(items)],
    hasSqlSource: { value: true }, hasMcpSource: { value: mixed }, isMixedSource: { value: mixed },
    isExternalSnapshot: { value: false }, supportsPivotConfig: { value: pivot },
    dateExpressionValidationError: () => '', dashboardDateParameterValidationErrorKey: () => '',
    sourcePreviewPivotPayload: () => undefined, previewPivotPayload: () => undefined, dashboardDateFilterRequestPayload: () => undefined,
    shapeDistributionTableResult: (value) => value,
    sourceResults: { sql: {}, external_mcp: {} }, sourcePreview: { fields: [], data: [] }, preview: { fields: [], data: [], status: 'success' },
    resetFieldSelections: () => {}, normalizePivotSelections: () => {}, syncPivotGroupValues: () => {}, alignSeriesAndPivotGroupFields: () => false,
    clearMergeState: () => {}, setMergeState: () => {}, mergeState: { joinFields: [], fieldMap: { sql: {}, external_mcp: {} } },
    mergePreviewResults: (sql) => ({ ...sql, joinFields: [], fieldMap: {} }),
    lastPreviewSql: { value: '' }, lastPreviewSignature: { value: '' }, previewVersion: { value: 0 }, currentPreviewSignature: () => 'signature',
    nextTick: async () => {}, t: (key) => key,
    validateDonutFieldMapping: () => true, currentMcpArgumentsForSave: () => ({}), chartSourceConfig: () => ({}),
    completeDashboardChartResultState: (view) => { view.status = 'success' },
    normalizeDashboardChartConfig: (value) => value, buildPivotConfig: () => ({}), dashboardDateFilterConfigForWrite: () => ({}),
    buildChart: () => ({ title: context.form.title }), builderConfigForSave: () => ({}),
    currentExternalMcpServerId: { value: 8 }, currentExternalMcpTenantId: { value: 9 }, currentDashboardId: { value: 10 },
    cleanMcpArguments: (value) => value, parseJsonObject: () => ({}),
    previewMcpTool: (_payload, options) => new Promise((resolve, reject) => {
      pendingPreviews.push({ options, resolve, reject, kind: 'mcp' })
    }),
  })
  for (const name of ['builderBlockingScopeIssues', 'retentionBlockingIssues', 'funnelBlockingIssues',
    'distributionBlockingIssues', 'intervalBlockingIssues', 'pathBlockingIssues', 'attributionBlockingIssues',
    'rankingBlockingIssues', 'heatmapBlockingIssues', 'invalidFormulaMetricItems']) context[name] = () => []
  vm.runInContext(ts.transpileModule(declarations(realPreview), { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context)
  return { context, pending, pendingPreviews, applied, warnings, unmountCallbacks, previews: () => previews }
}

async function start(editor) {
  const promise = editor.context.generateBuilderAiSql()
  for (let turn = 0; turn < 10 && !editor.pending.length; turn++) await Promise.resolve()
  assert.ok(editor.pending.length)
  return { promise, request: editor.pending.at(-1) }
}

test('backend-approved conditional SUM count reaches preview', async () => {
  const e = editor()
  e.context.sqlBuilder.metricItems = [{ aggregation: 'count' }]
  const { promise, request } = await start(e)
  request.resolve({ success: true, sql: "SELECT SUM(CASE WHEN action='Open' THEN 1 ELSE 0 END) AS count FROM activity" })
  await promise
  assert.equal(e.previews(), 1)
})

test('backend validation failure never reaches preview even when SQL is returned', async () => {
  const e = editor()
  const { promise, request } = await start(e)
  request.resolve({ success: false, sql: 'SELECT COUNT(*) FROM activity', issues: ['metric mismatch'] })
  await promise
  assert.equal(e.previews(), 0)
})

for (const ending of ['close', 'unmount']) {
  test(`${ending} cancels the transport and refuses a late SQL response`, async () => {
    const instance = editor()
    const { promise, request } = await start(instance)
    if (ending === 'close') instance.context.closeDrawer()
    else {
      assert.ok(instance.unmountCallbacks.length, 'unmount must cancel generation')
      instance.unmountCallbacks.forEach((callback) => callback())
    }
    assert.equal(request.options.signal?.aborted, true)
    request.resolve({ success: true, sql: 'SELECT 1' })
    assert.equal(await promise, false)
    assert.equal(instance.context.form.sql, 'previous SQL')
    assert.equal(instance.previews(), 0)
    assert.equal(instance.warnings.length, 0)
  })
}

test('a replaced generation cannot clear the newer request loading state or apply stale SQL', async () => {
  const instance = editor()
  const first = await start(instance)
  instance.pending.length = 0
  const second = await start(instance)
  assert.equal(first.request.options.signal?.aborted, true)
  first.request.resolve({ success: true, sql: 'stale SQL' })
  assert.equal(await first.promise, false)
  assert.equal(instance.context.builderLoading.value, true)
  second.request.resolve({ success: true, sql: 'SELECT 2' })
  assert.equal(await second.promise, true)
  assert.equal(instance.context.form.sql, 'SELECT 2')
  assert.equal(instance.previews(), 1)
})

test('closing before an error arrives suppresses cancellation warnings', async () => {
  const instance = editor()
  const { promise, request } = await start(instance)
  instance.context.closeDrawer()
  request.reject(new Error('cancelled'))
  assert.equal(await promise, false)
  assert.equal(instance.warnings.length, 0)
})

async function waitForPreview(instance, index) {
  for (let turn = 0; turn < 30 && !instance.pendingPreviews[index]; turn++) await Promise.resolve()
  assert.ok(instance.pendingPreviews[index], `preview ${index} must start`)
  return instance.pendingPreviews[index]
}

for (const scenario of ['plain SQL', 'pivot source', 'pivot result', 'mixed MCP', 'standalone SQL']) {
  test(`${scenario}: closing and reopening another chart rejects the late preview before mutation or persistence`, async () => {
    const instance = editor({ realPreview: true, pivot: scenario.startsWith('pivot'), mixed: scenario === 'mixed MCP' })
    let promise
    if (scenario === 'standalone SQL') promise = instance.context.previewAndPersistBuilderDraft()
    else {
      const generation = await start(instance)
      generation.request.resolve({ success: true, sql: 'SELECT old' })
      promise = generation.promise
    }
    let previewRequest = await waitForPreview(instance, 0)
    if (scenario === 'pivot result' || scenario === 'mixed MCP') {
      previewRequest.resolve({ status: 'success', fields: ['old'], data: [{ old: 1 }] })
      previewRequest = await waitForPreview(instance, 1)
    }
    instance.context.closeDrawer()
    const nextChart = { sql: 'SELECT new', data: { fields: ['new'], data: [{ new: 2 }] } }
    instance.context.props.viewInfo = nextChart
    instance.context.props.modelValue = true
    instance.context.form.sql = 'SELECT new'
    instance.context.sourcePreview.fields = ['new']
    instance.context.sourcePreview.data = [{ new: 2 }]
    instance.context.preview.fields = ['new']
    instance.context.preview.data = [{ new: 2 }]
    const lateResponse = { status: 'success', fields: ['old'], data: [{ old: 1 }], mcp: { old: true } }
    previewRequest.resolve(lateResponse)
    // Also release an incorrectly started second pivot query, so the broken implementation can finish.
    for (let turn = 0; turn < 30; turn++) {
      await Promise.resolve()
      instance.pendingPreviews.forEach((request) => request.resolve(lateResponse))
    }
    await promise
    assert.deepEqual(instance.context.preview.data, [{ new: 2 }])
    assert.deepEqual(instance.context.sourcePreview.data, [{ new: 2 }])
    assert.deepEqual(nextChart, { sql: 'SELECT new', data: { fields: ['new'], data: [{ new: 2 }] } })
    assert.equal(instance.applied.length, 0)
    assert.equal(previewRequest.options?.signal?.aborted, true)
    assert.equal(instance.warnings.length, 0)
  })
}

for (const scenario of ['plain', 'pivot', 'mixed']) {
  test(`${scenario} preview keeps its execution alive through successful persistence`, async () => {
    const instance = editor({ realPreview: true, pivot: scenario === 'pivot', mixed: scenario === 'mixed' })
    const generation = await start(instance)
    generation.request.resolve({ success: true, sql: 'SELECT answer' })
    const response = { status: 'success', fields: ['answer'], data: [{ answer: 42 }] }
    const first = await waitForPreview(instance, 0)
    assert.equal(first.options.signal, generation.request.options.signal)
    first.resolve(response)
    if (scenario !== 'plain') {
      const second = await waitForPreview(instance, 1)
      assert.equal(second.options.signal, generation.request.options.signal)
      second.resolve(response)
    }
    assert.equal(await generation.promise, true)
    assert.equal(instance.context.props.viewInfo.sql, 'SELECT answer')
    assert.equal(instance.context.props.viewInfo.data.data[0].answer, 42)
    assert.equal(instance.applied.length, 1)
    assert.equal(instance.context.builderLoading.value, false)
  })
}

test('closing during the execution loading phase prevents the preview request', async () => {
  const instance = editor({ realPreview: true })
  let releaseLoading
  instance.context.setLoadingPhase = async (phase) => {
    instance.context.builderLoading.value = true
    if (phase === '正在执行') await new Promise((resolve) => { releaseLoading = resolve })
  }
  const generation = await start(instance)
  generation.request.resolve({ success: true, sql: 'SELECT old' })
  for (let turn = 0; turn < 20 && !releaseLoading; turn++) await Promise.resolve()
  assert.ok(releaseLoading)
  instance.context.closeDrawer()
  releaseLoading()
  assert.equal(await generation.promise, false)
  assert.equal(instance.pendingPreviews.length, 0)
  assert.equal(instance.applied.length, 0)
})

test('an old preview rejection cannot persist an error or clear a newer generation loading state', async () => {
  const instance = editor({ realPreview: true })
  const first = await start(instance)
  first.request.resolve({ success: true, sql: 'SELECT old' })
  const oldPreview = await waitForPreview(instance, 0)
  instance.context.closeDrawer()
  instance.context.props.viewInfo = { sql: 'SELECT new' }
  instance.context.props.modelValue = true
  instance.pending.length = 0
  const second = await start(instance)
  oldPreview.reject(new Error('old preview failed'))
  assert.equal(await first.promise, false)
  assert.equal(instance.context.builderLoading.value, true)
  assert.equal(instance.warnings.length, 0)
  assert.equal(instance.applied.length, 0)
  instance.context.closeDrawer()
  second.request.reject(new Error('cancelled'))
  assert.equal(await second.promise, false)
})
