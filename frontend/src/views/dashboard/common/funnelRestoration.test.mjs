import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('./DashboardSqlEditor.vue', import.meta.url), 'utf8').match(/<script setup[^>]*>([\s\S]*?)<\/script>/)[1]
const ast = ts.createSourceFile('editor.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
const functionSource = ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'restoreFunnelRelatedProperty').getText(ast)
const ctx = vm.createContext({})
vm.runInContext(ts.transpileModule(functionSource, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, ctx)

test('an explicitly missing root related property does not restore a legacy substitute', () => {
  const legacy = [{ relatedProperty: 'events.category' }, { relatedProperty: 'events.category' }]
  assert.equal(ctx.restoreFunnelRelatedProperty({}, legacy), 'events.category')
  for (const value of [null, '', {}, 1]) {
    assert.equal(ctx.restoreFunnelRelatedProperty({ relatedProperty: value }, legacy), '')
  }
})

test('partial legacy related mappings cannot silently supply missing steps', () => {
  assert.equal(ctx.restoreFunnelRelatedProperty({}, [{ relatedProperty: 'events.category' }, {}]), '')
})

test('invalid saved related toggle is reported instead of silently disabling matching', () => {
  const restore = ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'restoreFunnelRelatedToggle')
  assert.ok(restore, 'restoration must preserve invalid toggle as a blocking issue')
  vm.runInContext(ts.transpileModule(restore.getText(ast), { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, ctx)
  for (const invalid of ['true', 'false', 1, null, {}]) {
    assert.ok(ctx.restoreFunnelRelatedToggle(invalid).issue)
  }
  for (const valid of [true, false, undefined]) assert.equal(ctx.restoreFunnelRelatedToggle(valid).issue, null)
})
