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

function setup(extra = {}) {
  const ast = ts.createSourceFile('index.ts', descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true)
  const script = ast.statements.filter(node => !ts.isImportDeclaration(node)).map(node => node.getText(ast)).join('\n')
  const context = vm.createContext({
    ...Vue, cloneDeep, useI18n: () => ({ t }),
    useUserStore: () => ({ tenants: [], isTenantAdminUser: true }), useRoute: () => ({ meta: {} }),
    watch: () => {}, onBeforeUnmount: () => {},
    formatTimestamp: () => '-',
    ElMessage: { success() {}, warning() {} },
    ...extra,
  })
  vm.runInContext(ts.transpileModule(`${script}\nglobalThis.state = { form, formRef, saving, drawerVisible, saveCard, pendingFile, openCreateCard, openEditCard, beforeKnowledgeUpload, releaseVersionText, t, cardList, filteredCards, formatCardTime, sourceText, sourceClass, releaseVersionClass, downloadCard, canDownloadCard };`, {
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

for (const result of [
  { status: 'READY', active: true, error_message: null },
  { status: 'FAILED', active: false, error_message: '文档正文为空，无法处理。' },
  { status: 'READY', active: false, error_message: '知识库上下文超过容量限制。' },
]) {
  test(`save reports the final inline parsing result: ${result.status} ${result.error_message || 'success'}`, async () => {
    const messages = []
    let finishValidation
    let finishSave
    const state = setup({
      knowledgeBaseApi: {
        save: () => new Promise(resolve => { finishSave = resolve }),
        list: async () => [],
      },
      ElMessage: {
        success: message => messages.push(['success', message]),
        error: message => messages.push(['error', message]),
        warning() {},
      },
    })
    state.openCreateCard()
    state.beforeKnowledgeUpload({ name: 'document.md', size: 100 })
    messages.length = 0
    state.formRef.value = { validate: callback => { finishValidation = callback(true) } }
    state.saveCard()
    assert.equal(state.saving.value, true)
    assert.equal(state.drawerVisible.value, true)
    assert.deepEqual(messages, [])
    finishSave(result)
    await finishValidation
    assert.deepEqual(messages, result.error_message
      ? [['error', result.error_message]]
      : [['success', t('common.save_success')]])
    assert.equal(state.saving.value, false)
    assert.equal(state.drawerVisible.value, false)
  })
}

test('body-only document downloads the filename provided by the server', async () => {
  const link = { href: '', download: '', click() {}, remove() {} }
  const blob = new Blob(['恢复正文'], { type: 'text/markdown' })
  const state = setup({
    Blob,
    knowledgeBaseApi: {
      download: async () => ({ blob, filename: '业务术语_正文.md', recovered: true }),
      list: async () => [],
    },
    document: { createElement: () => link, body: { appendChild() {} } },
    URL: { createObjectURL: () => 'blob:recovered', revokeObjectURL() {} },
  })
  await state.downloadCard({ id: 1, name: '术语', file_id: null, file_name: '业务术语.docx',
    file_ext: '.docx', content: '恢复正文', status: 'READY' })
  assert.equal(link.href, 'blob:recovered')
  assert.equal(link.download, '业务术语_正文.md')
})

test('download is enabled for completed body-only records but not unfinished or empty records', () => {
  const state = setup()
  assert.equal(state.canDownloadCard({ file_id: null, content: '正文', status: 'READY' }), true)
  assert.equal(state.canDownloadCard({ file_id: null, content: '正文', status: 'PROCESSING' }), false)
  assert.equal(state.canDownloadCard({ file_id: null, content: ' \n ', status: 'READY' }), false)
  assert.equal(state.canDownloadCard({ file_id: 'source.md', content: null, status: 'PENDING' }), true)
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
