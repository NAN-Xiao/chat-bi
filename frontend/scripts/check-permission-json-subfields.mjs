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

const { fieldOptionsToPermissionEntries, permissionRulesToSaveEntries } = await import(pathToFileURL(tempModulePath).href)
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

const sourceEntries = [{
  id: 34,
  type: 'column',
  permissions: [{ field_id: 101, field_name: 'uid', field_comment: '', enable: true }],
  expression_tree: {},
}, {
  id: 35,
  type: 'row',
  permissions: [{ field_id: 101, field_name: 'uid', field_comment: '', enable: true }],
  expression_tree: { logic: 'and', items: [] },
}, {
  id: 36,
  type: 'table',
  permissions: [{ field_id: 101, field_name: 'uid', field_comment: '', enable: true }],
  expression_tree: { stale: true },
}]

const saveEntries = permissionRulesToSaveEntries(sourceEntries)
assert.equal(Array.isArray(saveEntries[0].permissions), true)
assert.deepEqual(saveEntries[0].permissions, sourceEntries[0].permissions)
assert.deepEqual(saveEntries[0].expression_tree, {})
assert.deepEqual(saveEntries[1].permissions, [])
assert.deepEqual(saveEntries[1].expression_tree, sourceEntries[1].expression_tree)
assert.deepEqual(saveEntries[2].permissions, [])
assert.deepEqual(saveEntries[2].expression_tree, {})
assert.deepEqual(saveEntries.map((entry) => entry.permission_list), [[], [], []])

const permissionSaveConsumers = [
  'src/views/system/permission/index.vue',
  'src/views/system/user/User.vue',
  'src/views/system/tenant-access/TenantAccess.vue',
]
permissionSaveConsumers.forEach((relativePath) => {
  const consumerSource = readFileSync(resolve(root, relativePath), 'utf8')
  assert.match(
    consumerSource,
    /permissionRulesToSaveEntries\(/,
    `${relativePath} 必须复用结构化权限保存转换`
  )
  assert.doesNotMatch(
    consumerSource,
    /JSON\.stringify\((?:item|ele)\.permissions/,
    `${relativePath} 不能把字段权限数组转换成字符串`
  )
})
