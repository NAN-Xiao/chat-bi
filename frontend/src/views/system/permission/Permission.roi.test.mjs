import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const view = readFileSync(join(currentDir, 'index.vue'), 'utf8')
const api = readFileSync(join(currentDir, '../../../api/permissions.ts'), 'utf8')

assert.match(api, /getPermissionDatasources/)
assert.match(api, /\/ds_permission\/datasources/)
assert.match(api, /getPermissionDatasourceTables/)
assert.match(view, /getPermissionDatasources\(columnForm\.type\)/)
assert.match(view, /getPermissionDatasourceTables\(val\.id, columnForm\.type\)/)
assert.match(view, /columnForm\.type === 'table' && dsListOptions\.length > 1/)
assert.match(view, /const datasource = dsListOptions\.value\.find/)
assert.match(view, /permission\.datasource_not_available/)
assert.doesNotMatch(view, /const datasource = dsListOptions\.value\[0\][\s\S]*if \(row\)/)
