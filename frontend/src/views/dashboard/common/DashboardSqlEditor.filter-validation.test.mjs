import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('./DashboardSqlEditor.vue', import.meta.url), 'utf8')
const script = source.slice(source.indexOf('>') + 1, source.indexOf('</script>'))
const ast = ts.createSourceFile('editor.ts', script, ts.ScriptTarget.Latest, true)
const names = ['builderConfiguredFilterIssues', 'cloneBuilderFilterForSave', 'restoreBuilderFilter',
  'isEffectiveBuilderFilter', 'filterContext', 'filterRuleNodes', 'appendEventScopeFilterIssues']
const code = ast.statements.filter(n => ts.isFunctionDeclaration(n) && names.includes(n.name?.text)).map(n => n.getText(ast)).join('\n')
const rule = (value = '', field = 'events.uid', operator = 'eq') => ({ id: 'r', type: 'rule', field, operator, value, logic: 'and', children: [] })
function harness(model = 'funnel') {
  const context = vm.createContext({
    sqlBuilder: { analysisModel: model, globalFilters: [], metricItems: [], calculatedMetrics: [],
      funnel: { steps: [{ filters: [] }] }, retention: { initialEventFilters: [], returnEventFilters: [] },
      property: { audiences: [] }, interval: { startEventFilters: [], endEventFilters: [] } },
    builderFilterOperatorOptions: ['eq','ne','gt','lt','contains','between','is_null','is_not_null'].map(value => ({ value })),
    builderLogic: v => v === 'or' ? 'or' : 'and', nodeId: () => 'fixture',
    builderFilterRuleHasValue: r => ['is_null','is_not_null'].includes(r.operator) || String(r.value ?? '').trim() !== '',
    isEffectiveBuilderFilter: r => !!r.field && (['is_null','is_not_null'].includes(r.operator) || String(r.value ?? '').trim() !== ''),
    fieldOptionPayload: v => ({ table: 'events', field: v.split('.').at(-1) }),
    appendEventScopeFieldIssue: (value, path, issues) => { if (value === 'forbidden.uid') issues.push(path + ': forbidden') },
  })
  vm.runInContext(ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context)
  return context
}

for (const model of ['funnel', 'retention', 'property', 'interval', 'event']) test(`${model}: selected global field with empty value is blocking`, () => {
  const c = harness(model); c.sqlBuilder.globalFilters = [rule('   ')]
  assert.equal(typeof c.builderConfiguredFilterIssues, 'function')
  assert.match(c.builderConfiguredFilterIssues().join(' '), /全局筛选.*筛选值/)
})

test('step, retention and nested OR conditions are validated without treating rule children as groups', () => {
  const c = harness(); c.sqlBuilder.funnel.steps[0].filters = [{ type: 'group', logic: 'or', children: [rule('ok'), rule('')] }]
  assert.match(c.builderConfiguredFilterIssues().join(' '), /funnel.*筛选值/)
  c.sqlBuilder.analysisModel = 'retention'; c.sqlBuilder.retention.returnEventFilters = [rule('')]
  assert.match(c.builderConfiguredFilterIssues().join(' '), /returnEventFilters.*筛选值/)
  c.sqlBuilder.retention.returnEventFilters = []
  assert.deepEqual(Array.from(c.builderConfiguredFilterIssues()), [], 'inactive funnel draft must not block retention')
})

test('zero, false and explicit null operators remain valid', () => {
  const c = harness(); c.sqlBuilder.globalFilters = [rule('0'), rule('false'), rule('', 'events.uid', 'is_null'), rule('', 'events.uid', 'is_not_null')]
  assert.deepEqual(Array.from(c.builderConfiguredFilterIssues()), [])
})

test('partial conditions survive save and restore so reopening cannot remove their meaning', () => {
  const c = harness()
  for (const original of [rule(''), rule('entered', ''), { type: 'group', logic: 'or', children: [] }]) {
    const saved = c.cloneBuilderFilterForSave(original)
    assert.ok(saved, 'partial filter must not be dropped when saving draft')
    const restored = c.restoreBuilderFilter(saved)
    assert.ok(restored, 'partial filter must not be dropped when reopening')
    c.sqlBuilder.globalFilters = [restored]
    assert.ok(c.builderConfiguredFilterIssues().length)
  }
})

test('valid restored rules with empty children retain their predicate and permission checks', () => {
  const c = harness()
  const restored = c.restoreBuilderFilter(c.cloneBuilderFilterForSave(rule('Organic', 'events.channel')))
  assert.equal(c.isEffectiveBuilderFilter(restored), true)
  const payload = c.filterContext([restored])
  assert.equal(payload.length, 1)
  assert.equal(payload[0].value, 'Organic')
  assert.equal(c.filterRuleNodes([restored]).length, 1)
  const errors = []
  c.appendEventScopeFilterIssues([rule('x','forbidden.uid')], 'global', errors)
  assert.equal(errors.length, 1, 'rule permission checks must not be skipped because children is []')
})

test('nested OR group retains valid leaf predicates after save and restore', () => {
  const c = harness()
  const group = { id:'g',type:'group',logic:'or',children:[rule('A'),rule('B')] }
  const restored = c.restoreBuilderFilter(c.cloneBuilderFilterForSave(group))
  const payload = c.filterContext([restored])
  assert.equal(payload.length, 1)
  assert.equal(payload[0].logic, 'or')
  assert.equal(payload[0].children.length, 2)
})

test('filter tree renders typed leaf nodes as fields, not empty groups', () => {
  const text = readFileSync(new URL('./BuilderFilterTree.vue', import.meta.url), 'utf8')
  const body = text.match(/function isGroup\([\s\S]*?\n\}/)[0]
  const c = vm.createContext({})
  vm.runInContext(ts.transpileModule(body, {compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText,c)
  assert.equal(c.isGroup(rule('value')), false)
  assert.equal(c.isGroup({type:'group',children:[rule('value')]}), true)
})
