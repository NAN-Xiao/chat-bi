import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'DashboardSqlEditor.vue')
const source = readFileSync(componentPath, 'utf8')

const resetBuilderMatch = source.match(
  /function resetSqlBuilderState\(\) \{([\s\S]*?)\r?\n\}/
)
const initEditorMatch = source.match(
  /function initEditor\(\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nwatch\(\r?\n  \(\) => sqlBuilder\.activeTab/
)

assert.ok(resetBuilderMatch, '需要保留 SQL 编辑器状态重置逻辑')
assert.ok(initEditorMatch, '需要保留 SQL 编辑器初始化逻辑')

assert.match(
  resetBuilderMatch[1],
  /sqlBuilder\.activeTab = 'sql'/,
  '点击“编辑 SQL”默认应进入 SQL 明细，避免先渲染图表配置构建器'
)
assert.doesNotMatch(
  initEditorMatch[1],
  /loadSchemaTables\(\)/,
  '打开 SQL 编辑器时不应立即加载字段/事件元数据，应等用户进入图表配置时再加载'
)
assert.match(
  source,
  /function ensureBuilderSchemaLoaded\(\)/,
  '需要有进入图表配置时按需加载元数据的入口'
)
assert.match(
  source,
  /\(\) => sqlBuilder\.activeTab[\s\S]*if \(activeTab === 'builder'\)[\s\S]*ensureBuilderSchemaLoaded/,
  '切到图表配置时才触发字段/事件元数据加载'
)
assert.match(
  source,
  /<div v-if="sqlBuilder\.activeTab === 'builder'" class="sql-builder-builder-pane">/,
  '图表配置面板必须用 v-if 懒挂载，不能隐藏状态下参与首屏渲染'
)
assert.match(
  source,
  /<div v-if="sqlBuilder\.activeTab === 'sql'" class="sql-detail-pane">/,
  'SQL 明细面板应只在当前 tab 挂载'
)
assert.doesNotMatch(
  source,
  /<div v-show="sqlBuilder\.activeTab === '(builder|sql)'"/,
  '不能用 v-show 同时挂载 SQL 明细和图表配置两个重面板'
)
