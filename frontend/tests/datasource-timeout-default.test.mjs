import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')

const datasourceFormFiles = [
  'src/views/ds/form.vue',
  'src/views/ds/DatasourceForm.vue',
]

for (const relativePath of datasourceFormFiles) {
  const source = fs.readFileSync(path.join(root, relativePath), 'utf8')

  assert.match(source, /timeout:\s*90/, `${relativePath} 应默认使用 90 秒超时`)
  assert.doesNotMatch(
    source,
    /configuration\.timeout\s*\?\s*configuration\.timeout\s*:\s*30/,
    `${relativePath} 缺省回填不应退回 30 秒`
  )
}
