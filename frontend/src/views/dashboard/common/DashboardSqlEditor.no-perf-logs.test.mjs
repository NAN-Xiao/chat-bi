import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'DashboardSqlEditor.vue')
const perfHelperPath = join(currentDir, 'sqlEditorPerf.ts')
const perfHelperTestPath = join(currentDir, 'sqlEditorPerf.test.mjs')
const source = readFileSync(componentPath, 'utf8')

assert.doesNotMatch(
  source,
  /sqlEditorPerf/,
  'SQL 编辑器不应保留临时性能打点调用'
)
assert.doesNotMatch(
  source,
  /sql-editor-perf/,
  'SQL 编辑器不应输出临时性能打点日志标签'
)
assert.equal(
  existsSync(perfHelperPath),
  false,
  '临时性能打点工具文件应删除'
)
assert.equal(
  existsSync(perfHelperTestPath),
  false,
  '临时性能打点工具测试应删除'
)

console.log('dashboard SQL editor no perf logs tests passed')
