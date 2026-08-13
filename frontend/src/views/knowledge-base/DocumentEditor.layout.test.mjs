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

test('document editor removes block structure management actions', () => {
  assert.doesNotMatch(editorSource, /新增知识块|编辑标题|检索状态|上移|下移|复制|删除知识块/)
  assert.doesNotMatch(editorSource, /addBlock|copyBlock|moveBlock|renameBlock|removeBlock/)
  assert.doesNotMatch(editorSource, /ArrowDown|ArrowUp|CopyDocument|Delete|EditPen|Plus/)
  assert.doesNotMatch(editorSource, /class="block-actions"|class="directory-edit"/)
})

test('document editor keeps the title bar and markdown content', () => {
  assert.doesNotMatch(editorSource, /el-form-item label="标题"/)
  assert.doesNotMatch(editorSource, /el-form-item label="检索状态"/)
  assert.doesNotMatch(editorSource, /<el-switch/)
  assert.doesNotMatch(editorSource, /updateBlock\(activeBlockIndex, \{ enabled:/)
  assert.match(editorSource, /class="block-header"/)
  assert.match(editorSource, /class="block-index">\{\{ activeBlockIndex \+ 1 \}\}/)
  assert.match(editorSource, /class="block-title">\{\{ activeBlock\.title \|\| '未命名知识块' \}\}/)
  assert.match(editorSource, /el-form-item label="Markdown 正文"/)
  assert.match(editorSource, /class="markdown-editor"/)
  assert.match(editorSource, /updateBlock\(activeBlockIndex, \{ markdown: \$event \}\)/)
  assert.match(editorSource, /\.markdown-editor :deep\(\.ed-textarea__inner\)[^{]*\{[^}]*box-shadow: none;/)
})

test('document editor keeps the mobile directory horizontally scrollable', () => {
  assert.match(editorSource, /@media \(max-width: 680px\)/)
  assert.match(editorSource, /\.block-directory \{[\s\S]*?overflow-x: auto/)
  assert.match(panelSource, /class="knowledge-editor-drawer"/)
  assert.match(panelSource, /:global\(\.knowledge-editor-drawer\) \{ width: 100% !important; max-width: 100%; \}/)
})
