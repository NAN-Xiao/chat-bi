import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const directory = dirname(fileURLToPath(import.meta.url))
const pageSource = readFileSync(join(directory, 'index.vue'), 'utf8')
const panelSource = readFileSync(join(directory, 'KnowledgeBaseV2Panel.vue'), 'utf8').replace(
  /\r\n/g,
  '\n'
)
const knowledgeApiSource = readFileSync(join(directory, '../../api/knowledgeBase.ts'), 'utf8')
const routerSource = readFileSync(join(directory, '../../router/index.ts'), 'utf8')
const menuItemSource = readFileSync(join(directory, '../../components/layout/MenuItem.vue'), 'utf8')
const editorSource = readFileSync(join(directory, 'KnowledgePayloadEditor.vue'), 'utf8')
const layoutSource = readFileSync(join(directory, '../../components/layout/LayoutDsl.vue'), 'utf8')

test('knowledge page exposes only the document editor behind one orchestration layer', () => {
  assert.match(pageSource, /KnowledgeBaseV2Panel/)
  assert.match(editorSource, /DocumentEditor/)
  assert.doesNotMatch(editorSource, /BusinessKnowledgeEditor|EventKnowledgeEditor|JsonFieldKnowledgeEditor/)
})

test('knowledge management expands to platform and workspace child menus', () => {
  assert.match(routerSource, /path:\s*'data-skills'/)
  assert.match(routerSource, /path:\s*'knowledge-base'/)
  assert.match(routerSource, /redirect:\s*'\/system\/knowledge-base\/platform'/)
  assert.match(
    routerSource,
    /path:\s*'platform'[\s\S]*title:\s*t\('knowledge_base\.platform_knowledge_base'\)/
  )
  assert.match(
    routerSource,
    /path:\s*'workspace'[\s\S]*title:\s*t\('knowledge_base\.workspace_knowledge_base'\)/
  )
  assert.match(routerSource, /path:\s*'knowledge-base'[\s\S]*hidePopupTitle:\s*true/)
  assert.match(menuItemSource, /if \(children\?\.length\)/)
  assert.match(menuItemSource, /ElSubMenu/)
  assert.match(menuItemSource, /children\.map/)
})

test('knowledge page keeps capability and list failures separate from legacy and empty states', () => {
  assert.match(pageSource, /pageMode\.value = 'CAPABILITIES_UNAVAILABLE'/)
  assert.match(pageSource, /listError\.value = true/)
  assert.match(pageSource, /v-if="listError"/)
  assert.match(pageSource, /v-else-if="!visibleCards\.length"/)
  assert.doesNotMatch(pageSource, /catch[\s\S]{0,180}pageMode\.value = 'LEGACY'/)
})

test('knowledge page exposes platform knowledge as read-only to non-managers', () => {
  assert.match(pageSource, /<el-option label="平台知识库" value="PLATFORM_PUBLIC"/)
  assert.match(pageSource, /<el-option label="工作空间知识库" value="ADMIN_PUBLIC"/)
  assert.match(pageSource, /v-if="canCreateKnowledge"/)
  assert.match(pageSource, /if \(!row\.can_manage\) return/)
})

test('workspace knowledge creation reuses the top workspace filter', () => {
  assert.doesNotMatch(
    panelSource,
    /<el-form-item v-if="createForm\.visibility_scope === 'ADMIN_PUBLIC'" label="工作空间"/
  )
  assert.match(
    panelSource,
    /createForm\.value\.visibility_scope === 'ADMIN_PUBLIC' && !workspaceFilter\.value/
  )
  assert.match(
    panelSource,
    /tenant_id: createForm\.value\.visibility_scope === 'ADMIN_PUBLIC'\s*\n\s*\? workspaceFilter\.value\s*\n\s*: undefined/
  )
})

test('knowledge management exposes archived records as restorable or permanently deletable', () => {
  assert.match(panelSource, /const archiveFilter = ref<'current' \| 'archived'>\('current'\)/)
  assert.match(panelSource, /archived: isArchivedView\.value/)
  assert.match(panelSource, /<el-radio-button value="current">当前知识<\/el-radio-button>/)
  assert.match(panelSource, /<el-radio-button value="archived">已归档<\/el-radio-button>/)
  assert.match(panelSource, /const canCreateKnowledgeInScope = computed\(/)
  assert.match(panelSource, /canCreateKnowledgeInScope\.value && !isArchivedView\.value/)
  assert.match(
    panelSource,
    /const canEdit = computed\(\(\) => !!selected\.value\?\.can_manage && !selected\.value\.archived\)/
  )
  assert.match(panelSource, /version\.status === 'ARCHIVED' && Boolean\(version\.publish_time\)/)
  assert.match(panelSource, /knowledgeBaseApi\.restore\(row\.id\)/)
  assert.match(panelSource, /恢复知识库/)
  assert.match(panelSource, /class="panel-action-slot" :class="\{ 'is-placeholder': isArchivedView \}"/)
  assert.match(panelSource, /class="template-download panel-action-slot"/)
  assert.match(panelSource, /v-if="canCreateKnowledgeInScope"/)
  assert.match(panelSource, /class="panel-action-slot"[\s\S]*?is-placeholder': !canCreateKnowledge/)
  assert.match(panelSource, /knowledgeBaseApi\.permanentDelete\(row\.id\)/)
  assert.match(panelSource, /永久删除知识库/)
  assert.match(panelSource, /inputValidator: \(value\) => value === row\.name/)
  assert.doesNotMatch(panelSource, /knowledgeBaseApi\.setActive/)
  assert.doesNotMatch(panelSource, /class="knowledge-active-toggle"/)
  assert.doesNotMatch(knowledgeApiSource, /setActive\s*:/)
  assert.match(panelSource, /已发布版本将重新参与检索/)
})

test('knowledge archive switching keeps a stable header and table layout', () => {
  assert.doesNotMatch(panelSource, /class="panel-heading"/)
  assert.doesNotMatch(panelSource, /class="panel-title"/)
  assert.doesNotMatch(panelSource, /class="panel-subtitle"/)
  assert.match(panelSource, /<div class="panel-header">\s*<div class="panel-actions">/)
  assert.doesNotMatch(panelSource, /<el-table-column label="参与检索"/)
  assert.match(panelSource, /\.panel-action-slot\.is-placeholder \{ visibility: hidden; pointer-events: none; \}/)
  assert.match(panelSource, /\.panel-header \{ display: flex; width: 100%; margin-bottom: 18px; \}/)
})

test('knowledge lifecycle actions stay in the knowledge-base header before the payload editor', () => {
  const headerIndex = panelSource.indexOf('<div class="knowledge-editor-header">')
  const actionIndex = panelSource.indexOf('class="knowledge-lifecycle-actions"', headerIndex)
  const sourceUploadIndex = panelSource.indexOf(
    '<div v-if="canEdit && draft" class="source-upload-row">',
    headerIndex
  )
  const editorIndex = panelSource.indexOf('<KnowledgePayloadEditor', headerIndex)

  assert.ok(headerIndex >= 0, 'knowledge-base header should exist')
  assert.ok(actionIndex > headerIndex, 'lifecycle actions should be grouped inside the header')
  assert.ok(sourceUploadIndex > actionIndex, 'lifecycle actions should precede source upload content')
  assert.ok(
    editorIndex > sourceUploadIndex,
    'the payload editor should appear after source upload content'
  )
  assert.equal(panelSource.match(/class="knowledge-lifecycle-actions"/g)?.length, 2)
  assert.match(
    panelSource,
    /v-if="selected\.archived && selected\.can_manage" class="knowledge-lifecycle-actions"/
  )
  assert.match(panelSource, /@click="permanentlyDeleteKnowledge\(selected\)">永久删除/)
  assert.match(panelSource, /v-else-if="!selected\.archived" class="knowledge-lifecycle-actions"/)
  assert.match(
    panelSource,
    /:loading="saving" :disabled="!actionState\.save" @click="saveDraft">保存草稿/
  )
  assert.match(
    panelSource,
    /:loading="saving" :disabled="!actionState\.validate" @click="validateDraft">校验/
  )
  assert.match(
    panelSource,
    /:loading="publishing" :disabled="!actionState\.publish" @click="publishDraft">发布/
  )
  assert.match(
    panelSource,
    /@media \(max-width: 680px\)[\s\S]*?\.knowledge-editor-header \{ flex-direction: column; \}/
  )
  assert.match(
    panelSource,
    /\.knowledge-lifecycle-actions \{ display: grid; width: 100%; grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/
  )
  assert.match(
    panelSource,
    /\.knowledge-lifecycle-actions :deep\(\.ed-button\) \{ width: 100%; min-width: 0;/
  )
})

test('saving a document draft always persists and resynchronizes its server status', () => {
  const saveDocumentStart = panelSource.indexOf('async function saveDocumentDraft')
  const saveDocumentEnd = panelSource.indexOf('\n}\n\nasync function createEditingDraft', saveDocumentStart)
  const saveDocumentSource = panelSource.slice(saveDocumentStart, saveDocumentEnd)
  const saveDraftStart = panelSource.indexOf('async function saveDraft')
  const saveDraftEnd = panelSource.indexOf('\n}\n\nfunction isSupportedSourceFile', saveDraftStart)
  const saveDraftSource = panelSource.slice(saveDraftStart, saveDraftEnd)

  assert.ok(saveDocumentStart >= 0, 'document save function should exist')
  assert.match(saveDocumentSource, /let persisted = false/)
  assert.match(saveDocumentSource, /if \(!persisted\) \{[\s\S]*knowledgeBaseApi\.saveDraft\(/)
  assert.match(saveDraftSource, /if \(!saved\) return false[\s\S]*await loadVersions\(\)/)
})

test('saving a document draft always persists and resynchronizes its server status', () => {
  const saveDocumentStart = panelSource.indexOf('async function saveDocumentDraft')
  const saveDocumentEnd = panelSource.indexOf('\n}\n\nasync function createEditingDraft', saveDocumentStart)
  const saveDocumentSource = panelSource.slice(saveDocumentStart, saveDocumentEnd)
  const saveDraftStart = panelSource.indexOf('async function saveDraft')
  const saveDraftEnd = panelSource.indexOf('\n}\n\nfunction isSupportedSourceFile', saveDraftStart)
  const saveDraftSource = panelSource.slice(saveDraftStart, saveDraftEnd)

  assert.ok(saveDocumentStart >= 0, 'document save function should exist')
  assert.match(saveDocumentSource, /let persisted = false/)
  assert.match(saveDocumentSource, /if \(!persisted\) \{[\s\S]*knowledgeBaseApi\.saveDraft\(/)
  assert.match(saveDraftSource, /if \(!saved\) return false[\s\S]*await loadVersions\(\)/)
})

test('workspace management keeps a usable content width on mobile', () => {
  assert.match(layoutSource, /@media \(max-width: 680px\)/)
  assert.match(layoutSource, /\.workspace-admin-sidebar \{[\s\S]*?flex-basis: 64px/)
  assert.match(
    layoutSource,
    /\.workspace-admin-sidebar :deep\(\.menu-title-text\)[\s\S]*?display: none/
  )
  assert.match(
    layoutSource,
    /\.workspace-admin-content \.content-main \{[\s\S]*?padding: 14px 12px/
  )
})
