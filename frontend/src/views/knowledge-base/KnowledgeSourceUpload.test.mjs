import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const panelSource = readFileSync(new URL('./KnowledgeBaseV2Panel.vue', import.meta.url), 'utf8')
const legacySource = readFileSync(new URL('./index.vue', import.meta.url), 'utf8')
const localeFiles = ['en', 'ko-KR', 'zh-CN', 'zh-TW'].map((locale) => ({
  locale,
  messages: JSON.parse(readFileSync(new URL(`../../i18n/${locale}.json`, import.meta.url), 'utf8')),
}))

function asyncFunctionSource(name, nextName) {
  const start = panelSource.indexOf(`async function ${name}`)
  const end = panelSource.indexOf(`\nasync function ${nextName}`, start)
  assert.notEqual(start, -1, `${name} should exist`)
  assert.notEqual(end, -1, `${name} should have a stable boundary`)
  return panelSource.slice(start, end)
}

test('V2 create and edit flows expose the source upload control', () => {
  assert.match(panelSource, /label="文档内容"/)
  assert.match(panelSource, /拖拽或点击上传源文件/)
  assert.match(panelSource, /knowledgeBaseApi\.replaceDraftFile/)
  assert.match(panelSource, /accept="\.md,\.markdown"/)
  assert.match(panelSource, /parseKnowledgeMarkdownFile\(file\)/)
  assert.doesNotMatch(panelSource, /\.docx|\.xlsx|Word|Excel/)
})

test('legacy and V2 upload selectors use the same strict Markdown contract', () => {
  assert.match(legacySource, /accept="\.md,\.markdown"/)
  assert.match(legacySource, /parseKnowledgeMarkdownFile\(rawFile\)/)
  assert.doesNotMatch(legacySource, /\.docx|\.xlsx/)
})

test('all knowledge upload locales describe only the strict Markdown format', () => {
  for (const { locale, messages } of localeFiles) {
    const knowledgeMessages = messages.knowledge_base
    for (const key of ['upload_tip', 'upload_invalid_type', 'file_required']) {
      const message = String(knowledgeMessages[key])
      assert.match(message, /Markdown|\.md/, `${locale}.${key} must name Markdown`)
      assert.doesNotMatch(message, /Word|Excel|\.docx|\.xlsx/i, `${locale}.${key} must not advertise Office files`)
    }
  }
})

test('create flow snapshots the file and awaits upload after opening a current draft', () => {
  const source = asyncFunctionSource('createKnowledge', 'openEditor')
  const fileSnapshot = source.indexOf('const sourceFile = createSourceFile.value')
  const dialogClose = source.indexOf('createVisible.value = false')
  const editorOpen = source.indexOf('await openEditor(item)')
  const draftCreate = source.indexOf('await knowledgeBaseApi.createDraft(')
  const draftReload = source.indexOf('await loadVersions()', draftCreate)
  const sourceUpload = source.indexOf('await replaceDraftSource(sourceFile)')

  for (const [label, position] of Object.entries({
    fileSnapshot,
    dialogClose,
    editorOpen,
    draftCreate,
    draftReload,
    sourceUpload,
  })) {
    assert.notEqual(position, -1, `${label} marker should exist in createKnowledge`)
  }
  assert.ok(fileSnapshot < dialogClose, 'selected File must be captured before the dialog is destroyed')
  assert.ok(dialogClose < editorOpen, 'the created knowledge base must be opened before draft handling')
  assert.ok(editorOpen < draftCreate, 'draft creation must use the opened knowledge-base context')
  assert.ok(draftCreate < draftReload, 'a newly created draft must be loaded into editor state')
  assert.ok(draftReload < sourceUpload, 'source upload must wait for the current draft snapshot')
  assert.doesNotMatch(
    source.slice(dialogClose),
    /createSourceFile\.value/,
    'the destroyed dialog state must not be read during the async upload sequence',
  )
})

test('platform admin skips workspace datasource applicability before source upload', () => {
  const source = asyncFunctionSource('loadApplicability', 'loadVersions')
  const scopeGuard = source.indexOf("selected.value.visibility_scope !== 'PLATFORM_PUBLIC'")
  const platformAdminGuard = source.indexOf('if (isPlatformAdmin.value) return')
  const datasourceLoad = source.indexOf('await datasourceContext.loadDatasources()')

  assert.notEqual(scopeGuard, -1, 'platform knowledge scope guard should exist')
  assert.notEqual(platformAdminGuard, -1, 'pure platform administrators must skip workspace applicability')
  assert.notEqual(datasourceLoad, -1, 'workspace users should still load datasource applicability')
  assert.ok(scopeGuard < platformAdminGuard, 'scope should be checked before platform-admin handling')
  assert.ok(platformAdminGuard < datasourceLoad, 'platform administrators must return before datasource access')
})
