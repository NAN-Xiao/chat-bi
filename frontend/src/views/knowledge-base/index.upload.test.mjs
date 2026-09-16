import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import test from 'node:test'
import ts from 'typescript'
import { parse, compileTemplate } from '@vue/compiler-sfc'
import * as Vue from 'vue'
import { cloneDeep } from 'lodash-es'

const source = readFileSync(new URL('./index.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const translations = JSON.parse(readFileSync(new URL('../../i18n/zh-CN.json', import.meta.url), 'utf8'))
const t = key => key.split('.').reduce((value, part) => value?.[part], translations) || key

function setup() {
  const ast = ts.createSourceFile('index.ts', descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true)
  const script = ast.statements.filter(node => !ts.isImportDeclaration(node)).map(node => node.getText(ast)).join('\n')
  const context = vm.createContext({
    ...Vue, cloneDeep, useI18n: () => ({ t }),
    useUserStore: () => ({ tenants: [], isTenantAdminUser: true }), useRoute: () => ({ meta: {} }),
    watch: () => {}, onBeforeUnmount: () => {},
    formatTimestamp: () => '-',
    ElMessage: { success() {}, warning() {} },
  })
  vm.runInContext(ts.transpileModule(`${script}\nglobalThis.state = { form, pendingFile, openCreateCard, openEditCard, beforeKnowledgeUpload, releaseVersionText, t, cardList, filteredCards, formatCardTime, sourceText, sourceClass, releaseVersionClass };`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText, context)
  return context.state
}

test('new document stays enabled after file selection', () => {
  const state = setup()
  state.openCreateCard()
  assert.equal(state.form.value.active, true)
  state.beforeKnowledgeUpload({ name: 'document.md', size: 100 })
  assert.equal(state.form.value.active, true)
  assert.equal(state.form.value.status, 'PENDING')
})

test('replacement file preserves the explicit enabled or disabled setting', () => {
  for (const active of [true, false]) {
    const state = setup()
    state.openEditCard({ id: 1, name: 'document', active, status: 'READY' })
    state.beforeKnowledgeUpload({ name: 'replacement.md', size: 100 })
    assert.equal(state.form.value.active, active)
  }
})

test('enabled documents show processing and failure rather than published before ready', () => {
  const state = setup()
  assert.equal(state.releaseVersionText({ active: true, status: 'PENDING' }), t('knowledge_base.process_pending'))
  assert.equal(state.releaseVersionText({ active: true, status: 'PROCESSING' }), t('knowledge_base.process_processing'))
  assert.equal(state.releaseVersionText({ active: true, status: 'READY' }), t('knowledge_base.published'))
})

test('更新 column renders the upload name and unknown history as a dash', () => {
  const state = setup()
  state.cardList.value = [{ id: 1, name: 'document', active: true, status: 'READY' }]
  const compiled = compileTemplate({ source: descriptor.template.content, filename: 'index.vue', id: 'knowledge-base' })
  assert.deepEqual(compiled.errors, [])
  const exports = {}
  vm.runInNewContext(ts.transpileModule(compiled.code, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { exports, require: () => ({
    ...Vue, resolveComponent: name => ({ name }), resolveDirective: () => ({}),
    withDirectives: vnode => vnode,
  }) })
  const tree = exports.render(Vue.proxyRefs({ ...state, showWorkspaceSelector: false, canManageScope: true }), [])
  function find(node) {
    if (!node || typeof node !== 'object') return null
    if (node.props?.label === '更新') return node
    if (Array.isArray(node.children)) {
      for (const child of node.children) { const found = find(child); if (found) return found }
    } else if (node.children?.default) {
      for (const child of node.children.default({ row: {} })) { const found = find(child); if (found) return found }
    }
    return null
  }
  const column = find(tree)
  assert.ok(column, '更新 column should be visible')
  const text = nodes => nodes.map(node => typeof node.children === 'string' ? node.children : '').join('')
  assert.equal(text(column.children.default({ row: { uploaded_by_name: 'dongjinchao_test' } })), 'dongjinchao_test')
  assert.equal(text(column.children.default({ row: { uploaded_by_name: null } })), '—')
})
