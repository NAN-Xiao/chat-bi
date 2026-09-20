import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('./DashboardSqlEditor.vue', import.meta.url), 'utf8')
const script = source.slice(source.indexOf('>') + 1, source.indexOf('</script>'))
const ast = ts.createSourceFile('editor.ts', script, ts.ScriptTarget.Latest, true)
const names = new Set([
  'currentPreviewSignature', 'buildPivotConfig', 'previewPivotPayload',
  'currentPivotQuerySettingsSignature', 'rememberPreviewPivotConfig',
  'normalizeSeriesField', 'sanitizeSeriesSelection', 'handleChartTypeChange',
  'applyChange', 'validateBeforeApply', 'writeEditorStateToViewInfo', 'hasCurrentPreviewData',
  'reusablePreviewPivotConfig', 'syncPivotGroupValues', 'collectPivotGroupValueCounts',
  'collectPivotGroupSourceValues', 'normalizePivotSelections', 'sanitizePivotTimeField',
  'initPivotConfig', 'normalizePivotGranularity',
])
const variables = new Set([
  'supportsPivotConfig', 'effectiveSeriesField', 'activePivotGroupValueField',
  'lastPreviewPivotConfig', 'lastPreviewPivotSettingsSignature',
  'previewHasPivotGroupField', 'sourceHasPivotGroupValues', 'pivotGroupValueOptions', 'previewDisplayData',
])
const declarations = ast.statements.filter((node) =>
  ts.isFunctionDeclaration(node) && names.has(node.name?.text)
  || ts.isVariableStatement(node) && node.declarationList.declarations.some((d) => variables.has(d.name.getText(ast)))
).map((node) => node.getText(ast)).join('\n')
const watchers = ast.statements.filter((node) => ts.isExpressionStatement(node)
  && ts.isCallExpression(node.expression) && node.expression.expression.getText(ast) === 'watch'
  && (node.getText(ast).includes('() => activePivotGroupValueField.value')
    || node.getText(ast).includes('selectedMetricIsRatioOrAverage.value'))
).map((node) => node.getText(ast)).join('\n')

function editor({ pivot = true, chartType = 'line', series = 'segment' } = {}) {
  const context = vm.createContext({
    computed: (getter) => ({ get value() { return getter() } }), ref: (value) => ({ value }),
    form: {
      chartType, title: 'Fixture', columns: ['day', 'segment', 'amount'],
      sql: 'SELECT day, segment, amount FROM fixture', sourceTypes: ['sql'],
      x: 'day', y: ['amount'], series, pivotEnabled: pivot,
      pivotTimeField: 'day', pivotGroupField: series, pivotGranularity: 'day',
      pivotRangeEnabled: true, pivotRange: 'source', pivotCustomStart: '', pivotCustomEnd: '',
      pivotGroupEnabled: true, pivotGroupValues: [series === 'day' ? '2026-09-01' : 'A'], pivotGroupValueMode: 'custom',
    },
    sqlBuilder: { analysisModel: 'event', timeField: 'day', timeRange: 'expression', timeGrain: 'day',
      timeCustomRange: [], timeExpression: { type: 'relative', days: 7 } },
    hasSqlSource: { value: true }, hasMcpSource: { value: false }, isDistributionAnalysis: { value: false },
    selectedExecutionDatasourceId: { value: '1' }, props: { viewInfo: { id: 'fixture' } },
    sourcePreview: { fields: ['day', 'segment', 'amount'], data: [{ day: '2026-09-01', segment: 'A', amount: 10 }] },
    initializedPivotGroupValueField: { value: series },
    supportsForecastConfig: { value: false }, selectedMetricIsRatioOrAverage: { value: false },
    trendTimeGranularity: { value: 'day' }, normalizeInsightSelections: () => {},
    visiblePreviewFields: (fields, rows) => fields.filter((field) => rows.some((row) => field in row)),
    donutSeriesFields: { value: [] },
    unique: (items) => [...new Set(items)], normalizePivotGroupValue: String,
    SQL_EDITOR_DATE_PARAMETER_TYPE: 'yyyymmdd_number', dateExpressionEnabled: { value: false },
    dateExpressionConfigError: { value: '' }, defaultPivotGranularity: () => 'day',
    normalizePivotGroupValueMode: (pivot) => pivot?.group_value_mode || 'all',
    chartSupportsExplicitSeries: (type) => !['table', 'metric', 'funnel', 'scatter'].includes(type),
    isRadialPartitionChartType: (type) => ['pie', 'donut', 'treemap'].includes(type),
    toAxes: (fields) => fields.map((value) => ({ value })),
    resolvePivotMetricAggregations: () => ({ amount: 'sum' }), defaultPivotAggregation: () => 'sum',
    inferredPivotDimensions: () => [{ field: 'segment', label: 'segment' }],
    buildPersistedPivotGroupValueSelection: (mode, values) => ({ group_value_mode: mode, group_values: mode === 'all' ? [] : values }),
    titleOnlyChange: { value: false }, canUseSqlEditor: { value: true },
    sqlEditorPermissionMessage: 'SQL permission required',
    executionDatasourceError: { value: '' }, blockMissingFixedTimeField: () => false,
    dateExpressionValidationError: () => '', dashboardDateParameterValidationErrorKey: () => '',
    validateDonutFieldMapping: () => true, mcpChangedAfterPreview: { value: false }, mixedChangedAfterPreview: { value: false },
    showPivotGroupValueConfig: { value: false }, pivotTimeFieldOptions: { value: [{ value: 'day' }] },
    preview: { fields: ['day', 'segment', 'amount'], data: [{ day: '2026-09-01', segment: 'A', amount: 10 }], status: 'success' },
    warnings: [], applied: [], t: (key) => key, visible: { value: true },
    isExternalSnapshot: { value: false }, isMixedSource: { value: false },
    currentMcpArgumentsForSave: () => ({}), chartSourceConfig: () => ({}), builderConfigForSave: () => ({}),
    completeDashboardChartResultState: (view) => { view.status = 'success' },
    normalizeDashboardChartConfig: (value) => value, dashboardDateFilterConfigForWrite: () => ({}),
    previewVersion: { value: 0 }, showDismissibleSuccess: () => {},
    dashboardApi: { preview_sql: () => { throw new Error('Display changes must not execute SQL') } },
    runPreview: () => { throw new Error('Display changes must not run a preview') },
  })
  context.ElMessage = { warning: (value) => context.warnings.push(value) }
  context.emits = (event, value) => { if (event === 'applied') context.applied.push(JSON.parse(JSON.stringify(value))) }
  context.buildChart = () => ({ type: context.form.chartType, title: context.form.title })
  context.sourceResultForSave = () => ({ fields: context.preview.fields, data: context.preview.data })
  context.dashboardDateFilterRequestPayload = () => ({ expression: context.sqlBuilder.timeExpression })
  vm.runInContext(ts.transpileModule(declarations, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText, context)
  // The editor records a query only after restoring or executing it.
  context.executedPivot = context.buildPivotConfig()
  if (context.rememberPreviewPivotConfig) context.rememberPreviewPivotConfig(context.executedPivot)
  context.lastPreviewSignature = { value: context.currentPreviewSignature() }
  context.sqlChangedAfterPreview = { get value() { return context.currentPreviewSignature() !== context.lastPreviewSignature.value } }
  const callbacks = []
  context.watch = (getter, callback) => callbacks.push({ getter, callback, previous: getter() })
  vm.runInContext(ts.transpileModule(watchers, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context)
  context.flushWatchers = () => {
    for (let turn = 0; turn < 5; turn++) {
      for (const item of callbacks) {
        const next = item.getter()
        if (JSON.stringify(next) !== JSON.stringify(item.previous)) {
          const previous = item.previous
          item.previous = next
          item.callback(next, previous)
        }
      }
    }
  }
  return context
}

for (const pivot of [false, true]) {
  test(`chart type changes preserve query validity and the executed pivot (pivot=${pivot})`, () => {
    const c = editor({ pivot })
    const before = c.currentPreviewSignature()
    const executed = JSON.stringify(c.previewPivotPayload())
    for (const type of ['table', 'metric', 'line', 'pie', 'donut', 'column', 'table']) {
      c.form.chartType = type
      c.handleChartTypeChange(type)
      c.sanitizeSeriesSelection()
      c.flushWatchers()
      assert.equal(c.currentPreviewSignature(), before, `${type} must reuse the completed query`)
      assert.equal(JSON.stringify(c.previewPivotPayload()), executed, `${type} must retain the result's query semantics`)
    }
  })
}

test('switching a table to a chart does not turn a dormant pivot into a new query', () => {
  const c = editor({ chartType: 'table' })
  const before = c.currentPreviewSignature()
  c.form.chartType = 'line'
  assert.equal(c.currentPreviewSignature(), before)
  assert.equal(c.buildPivotConfig().enabled, false)
})

test('SQL, execution datasource, dates and explicit pivot edits still invalidate the result', () => {
  for (const change of [
    (c) => { c.form.sql += ' WHERE amount > 0' },
    (c) => { c.selectedExecutionDatasourceId.value = '2' },
    (c) => { c.sqlBuilder.timeExpression.days = 14 },
    (c) => { c.form.pivotGranularity = 'month' },
    (c) => { c.form.pivotEnabled = false },
    (c) => { c.form.pivotGroupField = 'other' },
  ]) {
    const c = editor()
    const before = c.currentPreviewSignature()
    change(c)
    assert.notEqual(c.currentPreviewSignature(), before)
  }
})

test('group value display filters remain saveable without changing the SQL request', () => {
  const c = editor()
  const before = c.currentPreviewSignature()
  c.form.pivotGroupValues = ['B']
  assert.equal(c.currentPreviewSignature(), before)
  assert.deepEqual(Array.from(c.buildPivotConfig().group_values), ['B'])
})

for (const pivot of [false, true]) {
  test(`applying another chart type writes the same rows and SQL without querying (pivot=${pivot})`, () => {
    const c = editor({ pivot })
    const rows = JSON.stringify(c.preview.data)
    for (const type of ['table', 'line', 'pie', 'column']) {
      c.form.chartType = type
      c.handleChartTypeChange(type)
      c.sanitizeSeriesSelection()
      c.flushWatchers()
      c.applyChange()
      assert.equal(c.warnings.length, 0)
      const applied = c.applied.at(-1)
      assert.equal(applied.chart.type, type)
      assert.equal(applied.sql, c.form.sql)
      assert.equal(JSON.stringify(applied.data.data), rows)
      assert.equal(applied.pivot.enabled, pivot)
      if (pivot) assert.equal(JSON.stringify(applied.data.source_data), JSON.stringify(c.sourcePreview.data))
    }
    assert.equal(c.applied.length, 4)
  })
}

test('display changes do not bypass failed results, permission checks or changed execution inputs', () => {
  for (const change of [
    (c) => { c.preview.status = 'failed' },
    (c) => { c.preview.fields = []; c.preview.data = [] },
    (c) => { c.canUseSqlEditor.value = false },
    (c) => { c.selectedExecutionDatasourceId.value = '2' },
    (c) => { c.sqlBuilder.timeExpression.days = 14 },
  ]) {
    const c = editor()
    c.form.chartType = 'table'
    change(c)
    c.applyChange()
    assert.equal(c.applied.length, 0)
    assert.equal(c.warnings.length, 1)
  }
})

test('a remembered pivot cannot cross into mixed-source or distribution queries', () => {
  for (const flag of ['hasMcpSource', 'isDistributionAnalysis']) {
    const c = editor()
    c[flag].value = true
    assert.equal(c.previewPivotPayload(), undefined)
  }
})

test('chart watchers preserve custom group selections and displayed rows through table round trips', () => {
  const c = editor()
  c.sourcePreview.data.push({ day: '2026-09-02', segment: 'B', amount: 20 })
  c.preview.data.push({ day: '2026-09-02', segment: 'B', amount: 20 })
  for (const type of ['table', 'line', 'pie', 'table']) {
    c.form.chartType = type
    c.flushWatchers()
    assert.equal(c.form.pivotGroupValueMode, 'custom')
    assert.deepEqual(Array.from(c.form.pivotGroupValues), ['A'])
    assert.equal(vm.runInContext('previewDisplayData.value.length', c), 1)
    c.applyChange()
    assert.deepEqual(c.applied.at(-1).pivot.group_values, ['A'])
  }
})

test('pie using its x field as the category can become a line without invalidating SQL', () => {
  const c = editor({ chartType: 'pie', series: 'day' })
  const before = c.currentPreviewSignature()
  c.form.chartType = 'line'
  c.flushWatchers()
  c.applyChange()
  assert.equal(c.currentPreviewSignature(), before)
  assert.equal(c.applied.length, 1)
})

test('reopening a saved pivot table restores its custom groups before chart watchers run', () => {
  const c = editor()
  c.sourcePreview.data.push({ day: '2026-09-02', segment: 'B', amount: 20 })
  c.form.chartType = 'table'
  c.flushWatchers()
  const saved = JSON.parse(JSON.stringify(c.buildPivotConfig()))
  c.form.series = '' // Saved table charts have no displayed series axis.
  vm.runInContext("lastPreviewPivotConfig.value = null; lastPreviewPivotSettingsSignature.value = ''", c)
  c.initPivotConfig(saved)
  c.flushWatchers()
  assert.equal(c.form.pivotGroupValueMode, 'custom')
  assert.deepEqual(Array.from(c.form.pivotGroupValues), ['A'])
  assert.equal(c.buildPivotConfig().group_field, 'segment')
})

test('restoring an invalid pivot does not re-enable a configuration cleared by field validation', () => {
  const c = editor()
  const saved = JSON.parse(JSON.stringify(c.buildPivotConfig()))
  c.pivotTimeFieldOptions.value = []
  vm.runInContext("lastPreviewPivotConfig.value = null; lastPreviewPivotSettingsSignature.value = ''", c)
  c.initPivotConfig(saved)
  assert.equal(c.form.pivotEnabled, false)
  assert.equal(c.buildPivotConfig().enabled, false)
})
