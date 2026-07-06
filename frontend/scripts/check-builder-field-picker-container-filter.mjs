import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import assert from 'node:assert/strict'
import ts from 'typescript'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const helperPath = resolve(root, 'src/views/dashboard/common/builderFieldPickerOptions.ts')
const editorPath = resolve(root, 'src/views/dashboard/common/DashboardSqlEditor.vue')

assert.equal(existsSync(helperPath), true, 'field picker option helper should exist')
assert.equal(existsSync(editorPath), true, 'dashboard SQL editor should exist')

const source = readFileSync(helperPath, 'utf8')
const editorSource = readFileSync(editorPath, 'utf8')

assert.match(
  editorSource,
  /excludeContainerFields:\s*true/,
  'dashboard SQL editor should request fieldList options without top-level container fields'
)
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText

const tempDir = resolve(tmpdir(), 'chat-bi-field-picker-check')
mkdirSync(tempDir, { recursive: true })
const tempModulePath = resolve(tempDir, `builderFieldPickerOptions-${Date.now()}.mjs`)
writeFileSync(tempModulePath, compiled, 'utf8')

const { isSelectableFieldOption } = await import(pathToFileURL(tempModulePath).href)

const baseOption = {
  label: '字段',
  value: 'event.some_field',
  table: 'event',
  field: 'some_field',
}

assert.equal(
  isSelectableFieldOption({ ...baseOption, type: '对象组' }),
  false,
  '对象组容器字段不应展示在字段下拉列表'
)
assert.equal(
  isSelectableFieldOption({ ...baseOption, type: 'jsonb' }),
  false,
  'json/jsonb 容器字段不应展示在字段下拉列表'
)
assert.equal(
  isSelectableFieldOption({ ...baseOption, type: 'varchar', semanticType: 'json' }),
  false,
  'semantic_type=json 的容器字段不应展示在字段下拉列表'
)
assert.equal(
  isSelectableFieldOption({ ...baseOption, type: 'varchar', semanticType: '对象组' }),
  false,
  'semantic_type=对象组 的容器字段不应展示在字段下拉列表'
)
assert.equal(
  isSelectableFieldOption({ ...baseOption, type: 'object_array' }),
  false,
  'object array 容器字段不应展示在字段下拉列表'
)
assert.equal(
  isSelectableFieldOption({
    ...baseOption,
    field: 'profile._appVersion',
    value: 'event.profile._appVersion',
    type: '文本',
    sourceField: 'profile',
    jsonPath: '$._appVersion',
    isJsonSubfield: true,
  }),
  true,
  'JSON 子字段应继续展示'
)
assert.equal(
  isSelectableFieldOption({ ...baseOption, type: '文本' }),
  true,
  '普通叶子字段应继续展示'
)
