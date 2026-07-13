import assert from 'node:assert/strict'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import ts from 'typescript'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const helperPath = resolve(root, 'src/views/system/permission/permissionFieldEntries.ts')

assert.equal(existsSync(helperPath), true, 'permission field entry helper should exist')

const source = readFileSync(helperPath, 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText
const tempDir = resolve(tmpdir(), 'chat-bi-permission-field-check')
mkdirSync(tempDir, { recursive: true })
const tempModulePath = resolve(tempDir, `permissionFieldEntries-${Date.now()}.mjs`)
writeFileSync(tempModulePath, compiled, 'utf8')

const { fieldOptionsToPermissionEntries } = await import(pathToFileURL(tempModulePath).href)
const options = [{
  id: 'tracking:event:personal.money',
  field_name: 'personal.money',
  field_comment: '充值金额',
  source_field: 'personal',
  json_path: '$.money',
  is_json_subfield: true,
}]

assert.deepEqual(fieldOptionsToPermissionEntries(options, [{
  field_id: 'tracking:event:personal.money',
  enable: false,
}]), [{
  field_id: 'tracking:event:personal.money',
  field_name: 'personal.money',
  field_comment: '充值金额',
  source_field: 'personal',
  json_path: '$.money',
  is_json_subfield: true,
  enable: false,
}])

assert.deepEqual(fieldOptionsToPermissionEntries([{
  id: 101,
  field_name: 'uid',
  field_comment: '用户 ID',
}], []), [{
  field_id: 101,
  field_name: 'uid',
  field_comment: '用户 ID',
  enable: true,
}])

assert.equal(
  fieldOptionsToPermissionEntries(options, [{
    field_id: 'tracking:event:personal.money.other',
    enable: false,
  }])[0].enable,
  true,
  'tracking 字段 ID 必须精确匹配，不能做数字转换或前缀匹配'
)
