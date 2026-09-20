import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const policySource = readFileSync(new URL('./analysisModelChartTypes.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(policySource, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText
const { analysisModelChartTypes, supportsAnalysisChartType } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const source = readFileSync(new URL('./DashboardSqlEditor.vue', import.meta.url), 'utf8')
const script = source.slice(source.indexOf('>') + 1, source.indexOf('</script>'))
const ast = ts.createSourceFile('editor.ts', script, ts.ScriptTarget.Latest, true)
const declarations = ast.statements.filter((node) => ts.isVariableStatement(node) && node.declarationList.declarations.some(
  (declaration) => ['chartTypes', 'availableChartTypes'].includes(declaration.name.getText(ast))
)).map((node) => node.getText(ast)).join('\n')

function options(model, { sql = true, tab = 'builder', saved = false } = {}) {
  const form = { chartType: 'table' }
  const context = vm.createContext({
    computed: (getter) => ({ get value() { return getter() } }),
    props: { viewInfo: {} }, form,
    sqlBuilder: { analysisModel: model, activeTab: tab },
    hasSqlSource: { value: sql }, supportsAnalysisChartType,
    chartSourceConfig: () => saved ? { sql: { builder: { analysisModel: model } } } : {},
  })
  vm.runInContext(ts.transpileModule(declarations, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context)
  const values = vm.runInContext('availableChartTypes.value.map(item => item.value)', context)
  assert.equal(form.chartType, 'table')
  return Array.from(values)
}

test('dropdown filters every model using local chart capabilities', () => {
  for (const [model, expected] of Object.entries(analysisModelChartTypes)) {
    assert.deepEqual(options(model).sort(), [...expected].sort(), model)
  }
  const defaults = { event: 'table', property: 'table', retention: 'table', funnel: 'funnel', distribution: 'table', interval: 'table', path: 'sankey', revenue: 'table', attribution: 'table', ranking: 'table', heatmap: 'heatmap' }
  for (const [model, chartType] of Object.entries(defaults)) assert.ok(options(model).includes(chartType))
})

test('distribution offers table, column, stacked area and pie', () => {
  assert.deepEqual(options('distribution'), ['table', 'column', 'area', 'pie'])
  assert.ok(source.includes("isDistributionAnalysis && item.value === 'area' ? '堆叠面积图'"))
  assert.ok(source.includes('v-for="item in availableChartTypes"'))
})

test('interval offers table, column and boxplot in builder and saved SQL views', () => {
  assert.deepEqual(options('interval'), ['table', 'column', 'boxplot'])
  assert.deepEqual(options('interval', { tab: 'sql', saved: true }), ['table', 'column', 'boxplot'])
})

test('saved model keeps its dropdown restriction in SQL tab', () => {
  assert.deepEqual(options('distribution', { tab: 'sql', saved: true }), ['table', 'column', 'area', 'pie'])
  assert.deepEqual(options('ranking', { tab: 'sql', saved: true }), ['table', 'bar'])
})

test('SQL-only and external source charts retain generic chart choices', () => {
  assert.ok(options('event', { tab: 'sql' }).includes('scatter'))
  assert.ok(options('distribution', { sql: false }).includes('sankey'))
  assert.equal(supportsAnalysisChartType('constructor', 'table'), false)
})
