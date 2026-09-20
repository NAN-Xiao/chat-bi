import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('./DashboardSqlEditor.vue', import.meta.url), 'utf8')
const script = source.slice(source.indexOf('>') + 1, source.indexOf('</script>'))
const ast = ts.createSourceFile('editor.ts', script, ts.ScriptTarget.Latest, true)
const formulaSource = readFileSync(new URL('./formulaMetricUtils.ts', import.meta.url), 'utf8')
const formula = await import(`data:text/javascript;base64,${Buffer.from(ts.transpileModule(formulaSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText).toString('base64')}`)
const names = new Set(['collectBuilderAiContext', 'metricTitle', 'metricOutputAlias', 'sqlAlias',
  'fieldOptionPayload', 'analysisResultFieldLabel', 'toAxis', 'toAxes', 'buildChart',
  'persistedAnalysisResultDisplayNames', 'normalizeAnalysisResultDisplayNames', 'toFieldOptions',
  'serializeEventBuilderConfig', 'restoreEventBuilderConfig', 'emptyMetricItem', 'emptyCalculatedMetricItem',
  'serializePropertyMetric', 'restorePropertyMetric'])
const declarations = ast.statements.filter((node) => ts.isFunctionDeclaration(node) && names.has(node.name?.text))
  .map((node) => node.getText(ast)).join('\n')
const plain = (value) => JSON.parse(JSON.stringify(value))

function editor(model = 'event') {
  const field = { value: 'event:active', field: 'event_name', table: 'events', kind: 'tracking-event',
    eventName: 'active', displayName: '当日活跃', label: '当日活跃', comment: '业务事件' }
  let nextId = 0
  const context = vm.createContext({
    ...formula,
    sqlBuilder: { analysisModel: model, metricItems: [], calculatedMetrics: [], groups: [], globalFilters: [],
      property: { groupMode: 'property', groupSettings: {}, audiences: [] }, timeField: 'dt',
      interval: { startEvent: field.value, endEvent: field.value, startEventAlias: 'select', endEventAlias: 'order',
        startEventFilters: [], endEventFilters: [], relatedProperty: { enabled: false }, limitSeconds: 3600 },
      ranking: { metric: { alias: 'order', aggregation: 'count' }, simultaneousMetrics: [], simultaneousProperties: [] },
    },
    nodeId: () => `fixture-${++nextId}`,
    fieldOptionIndex: { value: { find: (value) => value === field.value ? field : undefined } },
    fieldOptionByValue: (value) => value === field.value ? field : undefined,
    schemaFieldOptions: { value: [] },
    builderAggregationOptions: [{ value: 'count', label: '总次数' }, { value: 'count_distinct', label: '去重数' }],
    builderMetricOptions: { value: [] },
    selectedBuilderFieldValues: () => [], filterContext: (value) => value,
    metricMeasureField: (item) => item.field, shouldUseDashboardDateParameters: () => false,
    datasourceInfo: { value: null }, selectedExecutionDatasourceId: { value: 1 },
    EVENT_ANALYSIS_CONTEXT_CONTENT: '', clampIntervalLimitSeconds: (value) => value,
    form: { chartType: 'table', columns: [], title: '' }, props: { viewInfo: {} },
    analysisResultDisplayNames: { value: {} }, sourcePreview: { fields: [], data: [] },
    supportsInsightConfig: { value: false }, supportsForecastConfig: { value: false },
    sanitizeSeriesSelection: () => {}, unique: (value) => [...new Set(value)], t: (key) => key,
    builderLogic: (value) => value === 'or' ? 'or' : 'and',
    compactBuilderFilters: (value) => structuredClone(value), restoreBuilderFilters: (value) => structuredClone(value || []),
  })
  vm.runInContext(ts.transpileModule(declarations, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context)
  context.sqlBuilder.metricItems = [{ id: 'm1', field: field.value, metric: field.value, aggregation: 'count', alias: 'ac', filters: [], filterLogic: 'and' }]
  return context
}

for (const model of ['event', 'property']) {
  test(`${model} sends the exact display name separately from the SQL alias`, () => {
    const context = editor(model)
    context.sqlBuilder.metricItems[0].alias = 'order / 用户'
    const payload = context.collectBuilderAiContext().metrics[0]
    assert.equal(payload.displayName, 'order / 用户')
    assert.equal(payload.alias, 'order_用户')
    assert.equal(payload.field.eventName, 'active')
    context.sqlBuilder.metricItems[0].alias = ''
    assert.equal(context.collectBuilderAiContext().metrics[0].displayName, '当日活跃.总次数')
  })
}

test('formula and ranking names are passed without changing punctuation', () => {
  const context = editor()
  context.sqlBuilder.calculatedMetrics = [{ id: 'f1', alias: 'count / select', decimalPlaces: 2, tokens: [{ type: 'number', value: '2' }] }]
  const payload = context.collectBuilderAiContext()
  assert.equal(payload.formulaMetrics[0].displayName, 'count / select')
  assert.equal(payload.calculatedMetrics[0].displayName, 'count / select')
  context.sqlBuilder.analysisModel = 'ranking'
  assert.equal(context.collectBuilderAiContext().ranking.metric.displayName, 'order')
})

test('interval request carries event aliases independently of real event names', () => {
  const payload = editor('interval').collectBuilderAiContext().interval
  assert.equal(payload.startEventAlias, 'select')
  assert.equal(payload.endEventAlias, 'order')
  assert.equal(payload.startEvent.eventName, 'active')
})

test('display labels survive chart saving and reopening without changing result keys', () => {
  const context = editor()
  context.analysisResultDisplayNames.value = { ac: 'order / 用户', reg: 'reg' }
  context.form.columns = ['ac', 'reg']
  const saved = plain(context.buildChart())
  assert.deepEqual(saved.columns, [{ value: 'ac', name: 'order / 用户' }, { value: 'reg' }])
  context.analysisResultDisplayNames.value = context.persistedAnalysisResultDisplayNames(saved)
  assert.equal(context.analysisResultFieldLabel('ac'), 'order / 用户')
  assert.equal(context.toFieldOptions(['ac'])[0].label, 'order / 用户')
})

test('event configuration preserves names, formula references and filters on reopening', () => {
  const context = editor()
  context.sqlBuilder.calculatedMetrics = [{ ...context.emptyCalculatedMetricItem(), id: 'f1', alias: '比率 / rate',
    tokens: [{ type: 'metric', metricId: 'm1' }, { type: 'operator', value: '/' }, { type: 'number', value: '2' }] }]
  const saved = plain(context.serializeEventBuilderConfig())
  context.sqlBuilder.metricItems = []
  context.sqlBuilder.calculatedMetrics = []
  context.restoreEventBuilderConfig(saved)
  assert.equal(context.sqlBuilder.metricItems[0].alias, 'ac')
  assert.equal(context.sqlBuilder.calculatedMetrics[0].alias, '比率 / rate')
  assert.equal(context.sqlBuilder.calculatedMetrics[0].tokens[0].metricId, 'm1')
  assert.equal(context.collectBuilderAiContext().metrics[0].displayName, 'ac')
})
