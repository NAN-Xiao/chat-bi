import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import test from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('./knowledgeBase.ts', import.meta.url), 'utf8')

function apiFor(response) {
  const ast = ts.createSourceFile('knowledgeBase.ts', source, ts.ScriptTarget.Latest, true)
  const script = ast.statements.filter(node => !ts.isImportDeclaration(node))
    .map(node => node.getText(ast)).join('\n')
  const exports = {}
  vm.runInNewContext(ts.transpileModule(script, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText, { exports, request: {
    get: async () => response,
    download: async () => response.data,
  } })
  return exports.knowledgeBaseApi
}

test('download respects the restored UTF-8 Markdown filename from the response', async () => {
  const blob = new Blob(['正文'], { type: 'text/markdown' })
  const api = apiFor({ data: blob, headers: {
    'content-disposition': "attachment; filename*=utf-8''%E4%B8%9A%E5%8A%A1%E6%9C%AF%E8%AF%AD_%E6%AD%A3%E6%96%87.md",
    'x-knowledge-document-recovered': 'true',
  } })
  const result = await api.download(1, 23)
  assert.equal(result.filename, '业务术语_正文.md')
  assert.equal(result.blob, blob)
  assert.equal(result.recovered, true)
})

test('an intact source keeps its original filename and bytes', async () => {
  const blob = new Blob(['source bytes'])
  const result = await apiFor({ data: blob, headers: {
    'content-disposition': 'attachment; filename="original.docx"',
    'x-knowledge-document-recovered': 'false',
  } }).download(1)
  assert.equal(result.filename, 'original.docx')
  assert.equal(result.blob, blob)
  assert.equal(result.recovered, false)
})

test('a response without a filename cannot silently use a stale source extension', async () => {
  await assert.rejects(apiFor({ data: new Blob(['body']), headers: {} }).download(1))
})
