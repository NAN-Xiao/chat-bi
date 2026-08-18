import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const directory = dirname(fileURLToPath(import.meta.url))
const panelSource = readFileSync(join(directory, 'KnowledgeBaseV2Panel.vue'), 'utf8')

function functionSource(name, nextName) {
  const start = panelSource.indexOf(`async function ${name}`)
  const end = panelSource.indexOf(`\n${nextName}`, start)
  assert.notEqual(start, -1, `${name} should exist`)
  assert.notEqual(end, -1, `${name} should have a stable boundary`)
  return panelSource.slice(start, end)
}

test('row actions render edit, upload, download, and archive in order', () => {
  assert.match(
    panelSource,
    /class="row-actions"[\s\S]*openEditor\(row\)[\s\S]*>上传<\/el-button>[\s\S]*downloadRowSource\(row\)[\s\S]*>下载<\/el-button>[\s\S]*archiveKnowledge\(row\)/
  )
  assert.match(
    panelSource,
    /v-if="!row\.archived && row\.can_manage"/
  )
  assert.match(panelSource, /:icon="UploadFilled"[\s\S]*aria-label="上传源文件"/)
  assert.match(panelSource, /:icon="Download"[\s\S]*aria-label="下载源文件"/)
  assert.match(
    panelSource,
    /row\.archived && row\.can_manage[\s\S]*restoreKnowledge\(row\)[\s\S]*permanentlyDeleteKnowledge\(row\)/
  )
})

test('permanent delete is limited to archived manageable rows and requires exact-name confirmation', () => {
  const source = functionSource('permanentlyDeleteKnowledge', 'async function saveDraft')
  assert.match(source, /if \(!row\.archived \|\| !row\.can_manage \|\| rowBusyState\(row\)\) return/)
  assert.match(source, /ElMessageBox\.prompt/)
  assert.match(source, /inputValidator: \(value\) => value === row\.name \|\| '知识库名称不匹配'/)
  assert.match(source, /knowledgeBaseApi\.permanentDelete\(row\.id\)/)
  assert.match(source, /result\.file_cleanup\.failed > 0/)
})

test('archive action distinguishes archive from unpublished hard delete cleanup', () => {
  const source = functionSource('archiveKnowledge', 'async function restoreKnowledge')
  assert.match(source, /const result = await knowledgeBaseApi\.delete\(row\.id\)/)
  assert.match(source, /result\.file_cleanup\.failed > 0/)
  assert.match(source, /result\.archived \? '知识库已归档' : '未发布知识库已删除'/)
})

test('row upload validates the Markdown document contract and 50 MB limit', () => {
  assert.match(panelSource, /accept="\.md,\.markdown"/)
  assert.match(panelSource, /await parseKnowledgeMarkdownFile\(file\)/)
  assert.match(panelSource, /file\.size > 50 \* 1024 \* 1024/)
  assert.doesNotMatch(panelSource, /\.docx|\.xlsx/)
})

test('row upload uses a row-local exact draft and does not open or mutate editor state', () => {
  const source = functionSource('uploadRowSource', 'function rowSourceChangeHandler')
  assert.match(source, /knowledgeBaseApi\.version\(row\.id, row\.draft_version_id\)/)
  assert.match(source, /knowledgeBaseApi\.rollback\(row\.id, row\.current_version_id\)/)
  assert.match(source, /knowledgeBaseApi\.createDraft\(row\.id, defaultKnowledgePayload\(\)\)/)
  assert.ok(
    source.indexOf('await validateSourceFile(file)') < source.indexOf('knowledgeBaseApi.createDraft'),
    'format validation must finish before draft creation'
  )
  assert.match(source, /version_id: rowDraft\.id,[\s\S]*revision: rowDraft\.revision/)
  assert.doesNotMatch(source, /knowledgeBaseApi\.versions|\.find\(/)
  assert.doesNotMatch(
    source,
    /selected\.value|draft\.value|payload\.value|editorVisible\.value|openEditor/
  )
})

test('row upload callback consumes rejected async uploads', () => {
  assert.match(
    panelSource,
    /uploadRowSource\(row, uploadFile\.raw as UploadRawFile\)\.catch\(\(error\) => \{[\s\S]*console\.error\(error\)/
  )
})

test('row download checks the explicit draft before the explicit published version', () => {
  const source = functionSource('downloadRowSource', 'function downloadMarkdownTemplate')
  assert.match(source, /knowledgeBaseApi\.version\(row\.id, row\.draft_version_id\)/)
  assert.match(
    source,
    /if \(!sourceVersion\?\.file_name && row\.current_version_id != null && !row\.archived\)/
  )
  assert.match(source, /knowledgeBaseApi\.version\(row\.id, row\.current_version_id\)/)
  assert.match(source, /knowledgeBaseApi\.download\(row\.id, sourceVersion\.id\)/)
})

test('blob downloads remove their anchors and defer object URL cleanup', () => {
  assert.match(
    panelSource,
    /try \{[\s\S]*anchor\.click\(\)[\s\S]*\} finally \{\s*anchor\.remove\(\)\s*window\.setTimeout\(\(\) => URL\.revokeObjectURL\(url\), 0\)/
  )
  assert.doesNotMatch(panelSource, /anchor\.click\(\)\s*\n\s*URL\.revokeObjectURL\(url\)/)
  assert.match(
    panelSource,
    /downloadBlob\(blob, version\.file_name \|\| `knowledge-\$\{version\.version_number\}`\)/
  )
  assert.match(panelSource, /downloadBlob\(blob, sourceVersion\.file_name\)/)
})
