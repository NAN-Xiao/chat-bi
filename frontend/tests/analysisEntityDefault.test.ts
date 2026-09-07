import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { runInNewContext } from 'node:vm'
import ts from 'typescript'
import { preferredBuilderEntityField } from '../src/views/dashboard/common/builderFieldPickerOptions.ts'
import { getEventScopedFields, resolveDashboardBuilderEventScope } from '../src/views/dashboard/common/dashboardBuilderMetadata.ts'

const source = readFileSync(new URL('../src/views/dashboard/common/DashboardSqlEditor.vue', import.meta.url), 'utf8')
const script = source.split('<script setup lang="ts">')[1].split('</script>')[0]
const ast = ts.createSourceFile('editor.ts', script, ts.ScriptTarget.Latest, true)
const functions = new Map(ast.statements.filter(ts.isFunctionDeclaration).map((node) => [node.name!.text, node]))
const helpers = ['preferredAnalysisEntityField', 'sanitizeAnalysisEntityField']
  .map((name) => functions.get(name)!.getText(ast)).join('\n')
const fields = [
  { value: 'activity.account_key', table: 'activity', field: 'account_key', label: 'Account' },
  { value: 'activity.device_key', table: 'activity', field: 'device_key', label: 'Device', fieldRole: 'subject_id' },
]

function editor(configOverrides = {}, datasourceId = 'selected') {
  const config = { enabled: true, datasource_id: 'selected', default_event_table: 'activity', default_subject_field: 'account_key', ...configOverrides }
  const scope = resolveDashboardBuilderEventScope({ config, datasourceId, tableNames: ['activity'] })
  const options = getEventScopedFields(fields, scope)
  const context = {
    preferredBuilderEntityField,
    eventFieldScope: { value: scope },
    trackingConfig: { value: config },
    optionExists: (value: string, candidates: typeof fields) => candidates.some((item) => item.value === value),
  }
  const code = ts.transpileModule(`${helpers}\n({ preferredAnalysisEntityField, sanitizeAnalysisEntityField })`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText
  return { ...runInNewContext(code, context), options }
}

test('metadata arriving after an empty initialization restores the configured subject', () => {
  const { sanitizeAnalysisEntityField, options } = editor()
  const config = { entityField: '' }
  sanitizeAnalysisEntityField(config, [])
  assert.equal(config.entityField, '')
  sanitizeAnalysisEntityField(config, options)
  assert.equal(config.entityField, 'activity.account_key')
})

test('reopening an existing chart preserves the manually selected subject', () => {
  const { sanitizeAnalysisEntityField, options } = editor()
  const config = { entityField: 'activity.device_key' }
  assert.equal(sanitizeAnalysisEntityField(config, options), false)
  assert.equal(config.entityField, 'activity.device_key')
})

test('an invalid saved selection is cleared and reported without substitution', () => {
  const { sanitizeAnalysisEntityField, options } = editor()
  const config = { entityField: 'old.account_key' }
  assert.equal(sanitizeAnalysisEntityField(config, options), true)
  assert.equal(config.entityField, '')
})

test('another datasource cannot use the workspace default or its field roles', () => {
  const { preferredAnalysisEntityField, options } = editor({}, 'other')
  assert.equal(preferredAnalysisEntityField(options), '')
})

test('disabled tracking configuration does not apply its default subject', () => {
  const { preferredAnalysisEntityField, options } = editor({ enabled: false })
  assert.equal(preferredAnalysisEntityField(options), 'activity.device_key')
})

// Execute each model's actual initialization statement to cover every shared entry point.
const initializers = [...functions.values()].filter((node) => (
  node.name?.text.startsWith('reset') && node.body?.statements[0]?.getText(ast).includes('.entityField =')
))
assert.equal(initializers.length, 7)
for (const node of initializers) {
  test(`${node.name!.text} initializes the configured subject on model selection`, () => {
    const { preferredAnalysisEntityField, options } = editor()
    const state = Object.fromEntries(['retention', 'funnel', 'distribution', 'interval', 'revenue', 'attribution', 'ranking'].map((model) => [model, { entityField: '' }]))
    const context = {
      sqlBuilder: state,
      preferredAnalysisEntityField,
      ...Object.fromEntries(Object.keys(state).map((model) => [`${model}EntityFieldOptions`, { value: options }])),
    }
    runInNewContext(node.body!.statements[0].getText(ast), context)
    const model = node.name!.text.slice('reset'.length, -'Config'.length).toLowerCase()
    assert.equal(state[model].entityField, 'activity.account_key')
  })
}
