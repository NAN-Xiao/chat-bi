import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const directory = dirname(fileURLToPath(import.meta.url))
const editorSource = readFileSync(join(directory, 'editors/DocumentEditor.vue'), 'utf8')
const frameSource = readFileSync(join(directory, 'editors/KnowledgeContentFrame.vue'), 'utf8')
const panelSource = readFileSync(join(directory, 'KnowledgeBaseV2Panel.vue'), 'utf8')

test('document editor uses a directory with one active block detail', () => {
  assert.match(editorSource, /const activeBlockId = ref\(''\)/)
  assert.match(editorSource, /class="block-directory"/)
  assert.match(editorSource, /v-if="activeBlock && activeBlockIndex >= 0"/)
  assert.doesNotMatch(
    editorSource,
    /v-for="\(block, index\) in modelValue\.blocks"[^>]*class="knowledge-block"/
  )
  assert.doesNotMatch(editorSource, /expandedBlocks/)
})

test('desktop block directory owns long-list scrolling', () => {
  assert.match(editorSource, /\.block-workspace \{[^}]*align-items: start;/)
  assert.match(
    editorSource,
    /\.block-directory \{[^}]*max-height: calc\(100vh - 180px\);[^}]*overflow-y: auto;[^}]*overscroll-behavior: contain;/
  )
})

test('knowledge editing stays focused on block content', () => {
  assert.doesNotMatch(panelSource, /替换源文件/)
  assert.doesNotMatch(panelSource, /下载当前源文件/)
  assert.doesNotMatch(panelSource, /pendingFile/)
  assert.doesNotMatch(editorSource, /KnowledgeReferenceList|KnowledgeStringList|datasource_neutral/)
  const payloadEditorSource = readFileSync(join(directory, 'KnowledgePayloadEditor.vue'), 'utf8')
  assert.doesNotMatch(payloadEditorSource, /label="知识类型"|typeOptions|updateType/)
  assert.doesNotMatch(panelSource, /createForm\.knowledge_type/)
  assert.doesNotMatch(panelSource, /label="知识类型"|label="知识类型"/)
})

test('deleted block conflicts can preserve local content as a new block', () => {
  assert.match(panelSource, /function restoreDeletedConflictBlock\(\)/)
  assert.match(panelSource, /createDocumentBlock\(localBlock\.title, localBlock\.markdown\)/)
  assert.match(panelSource, /draft\.value = \{ \.\.\.draft\.value, payload: serverPayload \}/)
  assert.match(panelSource, /恢复为新知识块/)
})

test('the document editor uses the shared content frame', () => {
  assert.match(editorSource, /import KnowledgeContentFrame from '.\/KnowledgeContentFrame\.vue'/)
  assert.match(editorSource, /<KnowledgeContentFrame/)
  assert.match(frameSource, /class="knowledge-content-frame"/)
  assert.match(frameSource, /class="content-frame-header"/)
  assert.match(frameSource, /class="content-frame-body"/)
  assert.match(frameSource, /border: 1px solid #dfe3e8/)
  assert.doesNotMatch(
    editorSource,
    /class="knowledge-block"|class="block-header"|class="block-body"/
  )
})

test('document editor adds and confirms deletion of draft blocks', () => {
  assert.match(editorSource, /createDocumentBlock\(nextBlockTitle\(\)\)/)
  assert.match(editorSource, /updateBlocks\(\[\.\.\.props\.modelValue\.blocks, block\]\)/)
  assert.match(editorSource, /activeBlockId\.value = block\.id/)
  assert.match(editorSource, /普通文档至少需要保留一个知识块/)
  assert.match(editorSource, /await ElMessageBox\.confirm/)
  assert.match(
    editorSource,
    /activeBlockId\.value = blocks\[Math\.min\(removedIndex, blocks\.length - 1\)\]/
  )
  assert.match(editorSource, /v-if="!readonly" content="新增知识块"/)
  assert.match(editorSource, /v-if="!readonly" #actions/)
  assert.doesNotMatch(editorSource, /copyBlock|moveBlock|renameBlock/)
})

test('document editor keeps the title bar and markdown content', () => {
  assert.doesNotMatch(editorSource, /el-form-item label="标题"/)
  assert.doesNotMatch(editorSource, /el-form-item label="检索状态"/)
  assert.doesNotMatch(editorSource, /<el-switch/)
  assert.doesNotMatch(editorSource, /updateBlock\(activeBlockIndex, \{ enabled:/)
  assert.match(editorSource, /:index="activeBlockIndex \+ 1"/)
  assert.match(editorSource, /:title="activeBlock\.title \|\| '未命名知识块'"/)
  assert.match(editorSource, /el-form-item label="Markdown 正文"/)
  assert.match(editorSource, /class="markdown-editor"/)
  assert.match(editorSource, /updateBlock\(activeBlockIndex, \{ markdown: \$event \}\)/)
  assert.match(
    editorSource,
    /\.markdown-editor :deep\(\.ed-textarea__inner\)[^{]*\{[^}]*box-shadow: none;/
  )
  assert.match(panelSource, /await knowledgeBaseApi\.saveDocumentStructure/)
  assert.match(panelSource, /captureDocumentConflict\(error\)/)
})

test('document editor keeps the mobile directory horizontally scrollable', () => {
  assert.match(editorSource, /@media \(max-width: 680px\)/)
  assert.match(
    editorSource,
    /@media \(max-width: 680px\) \{[\s\S]*?\.block-directory \{[^}]*max-height: none;[^}]*overflow-x: auto;[^}]*overflow-y: hidden;/
  )
  assert.match(panelSource, /class="knowledge-editor-drawer"/)
  assert.match(
    panelSource,
    /:global\(\.knowledge-editor-drawer\) \{ width: 100% !important; max-width: 100%; \}/
  )
})
