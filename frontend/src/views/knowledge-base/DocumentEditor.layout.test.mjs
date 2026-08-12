import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const directory = dirname(fileURLToPath(import.meta.url))
const editorSource = readFileSync(join(directory, 'editors/DocumentEditor.vue'), 'utf8')
const panelSource = readFileSync(join(directory, 'KnowledgeBaseV2Panel.vue'), 'utf8')

test('document editor uses a directory with one active block detail', () => {
  assert.match(editorSource, /const activeBlockId = ref\(''\)/)
  assert.match(editorSource, /class="block-directory"/)
  assert.match(editorSource, /v-if="activeBlock && activeBlockIndex >= 0"/)
  assert.doesNotMatch(editorSource, /v-for="\(block, index\) in modelValue\.blocks"[^>]*class="knowledge-block"/)
  assert.doesNotMatch(editorSource, /expandedBlocks/)
})

test('knowledge editing stays focused on block content', () => {
  assert.doesNotMatch(panelSource, /替换源文件/)
  assert.doesNotMatch(panelSource, /下载当前源文件/)
  assert.doesNotMatch(panelSource, /pendingFile/)
  assert.doesNotMatch(editorSource, /KnowledgeReferenceList|KnowledgeStringList|datasource_neutral/)
  const payloadEditorSource = readFileSync(join(directory, 'KnowledgePayloadEditor.vue'), 'utf8')
  assert.doesNotMatch(payloadEditorSource, /label="知识类型"|typeOptions|updateType/)
  assert.match(panelSource, /createForm\.knowledge_type/)
  assert.match(panelSource, /label="知识类型"/)
})

test('deleted block conflicts can preserve local content as a new block', () => {
  assert.match(panelSource, /function restoreDeletedConflictBlock\(\)/)
  assert.match(panelSource, /createDocumentBlock\(localBlock\.title, localBlock\.markdown\)/)
  assert.match(panelSource, /draft\.value = \{ \.\.\.draft\.value, payload: serverPayload \}/)
  assert.match(panelSource, /恢复为新知识块/)
})

test('document editor keeps selection stable across structure operations', () => {
  assert.match(editorSource, /activeBlockId\.value = block\.id[\s\S]*updateBlocks\(blocks\)/)
  assert.match(editorSource, /activeBlockId\.value = copy\.id[\s\S]*updateBlocks\(blocks\)/)
  assert.match(editorSource, /removedBlock\.id === activeBlockId\.value/)
  assert.match(editorSource, /blocks\[Math\.min\(index, blocks\.length - 1\)\]\?\.id/)
  assert.match(editorSource, /const \[block\] = blocks\.splice\(index, 1\)[\s\S]*blocks\.splice\(target, 0, block\)[\s\S]*updateBlocks\(blocks\)/)
})

test('document editor edits titles from the directory and keeps detail focused on content', () => {
  assert.match(editorSource, /class="directory-edit" text :icon="EditPen"[^>]*aria-label="编辑标题"/)
  assert.match(editorSource, /ElMessageBox\.prompt\('请输入知识块标题', '编辑知识块标题'/)
  assert.match(editorSource, /updateBlock\(index, \{ title: value\.trim\(\) \}\)/)
  assert.doesNotMatch(editorSource, /el-form-item label="标题"/)
  assert.doesNotMatch(editorSource, /el-form-item label="检索状态"/)
  assert.match(editorSource, /aria-label="检索状态"/)
  assert.match(editorSource, /el-form-item label="Markdown 正文"/)
  assert.match(editorSource, /class="markdown-editor"/)
  assert.match(editorSource, /\.markdown-editor :deep\(\.ed-textarea__inner\)[^{]*\{[^}]*box-shadow: none;/)
})

test('document editor uses compact project-style icon actions', () => {
  assert.doesNotMatch(editorSource, /<el-button[^>]*\bcircle\b/)
  assert.match(editorSource, /class="block-action" text :icon="ArrowUp"/)
  assert.match(editorSource, /class="block-action is-danger" text :icon="Delete"/)
  assert.match(editorSource, /\.directory-edit, \.block-action \{ width: 28px; height: 28px;/)
  assert.match(editorSource, /\.block-action\.is-danger:hover \{ color: #f04438; background: #fff1f0;/)
})

test('document editor keeps the mobile directory horizontally scrollable', () => {
  assert.match(editorSource, /@media \(max-width: 680px\)/)
  assert.match(editorSource, /\.block-directory \{[\s\S]*?overflow-x: auto/)
  assert.match(panelSource, /class="knowledge-editor-drawer"/)
  assert.match(panelSource, /:global\(\.knowledge-editor-drawer\) \{ width: 100% !important; max-width: 100%; \}/)
})
