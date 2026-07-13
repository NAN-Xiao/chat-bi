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
const loadSchemaTablesMatch = source.match(
  /async function loadSchemaTables\(([\s\S]*?)\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction ensureBuilderSchemaLoaded/
)
const ensureBuilderSchemaLoadedMatch = source.match(
  /function ensureBuilderSchemaLoaded\(\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction chartSupportsExplicitSeries/
)

assert.ok(resetBuilderMatch, '需要保留 SQL 编辑器状态重置逻辑')
assert.ok(initEditorMatch, '需要保留 SQL 编辑器初始化逻辑')
assert.ok(loadSchemaTablesMatch, '需要保留图表配置元数据加载入口')
assert.ok(ensureBuilderSchemaLoadedMatch, '需要保留进入图表配置时按需加载元数据的入口')

assert.match(
  source,
  /const sqlBuilder = reactive\(\{\s*activeTab: 'builder'/,
  '编辑图表首次打开时应默认进入图表配置'
)
assert.match(
  resetBuilderMatch[1],
  /sqlBuilder\.activeTab = 'builder'/,
  '每次打开编辑图表都应重置到图表配置'
)
assert.match(
  initEditorMatch[1],
  /restoreSqlBuilderState\([\s\S]*ensureBuilderSchemaLoaded\(\)/,
  '编辑器恢复当前图表状态后应主动请求图表配置元数据，保证关闭后重开仍会加载'
)
assert.doesNotMatch(
  initEditorMatch[1],
  /loadSchemaTables\(\)/,
  '编辑器初始化应复用图表配置元数据加载入口，不应绕过请求有效性校验'
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
  /const startViewInfo = props\.viewInfo/,
  '按需加载图表配置元数据时应记录触发时的图表对象'
)
assert.match(
  source,
  /const requestSeq = \+\+builderSchemaLoadSeq/,
  '每次进入图表配置加载元数据时应生成请求序号，避免旧请求覆盖新状态'
)
assert.match(
  ensureBuilderSchemaLoadedMatch[1],
  /loadSchemaTables\(startViewInfo,\s*requestSeq\)/,
  '图表配置元数据加载应使用触发时的图表对象和请求序号'
)
assert.match(
  loadSchemaTablesMatch[1],
  /startViewInfo: any,\s*requestSeq: number/,
  'loadSchemaTables 应接收触发时的图表对象和请求序号'
)
assert.match(
  loadSchemaTablesMatch[2],
  /function isCurrentSchemaLoad\(\)[\s\S]*requestSeq === builderSchemaLoadSeq[\s\S]*visible\.value[\s\S]*props\.viewInfo === startViewInfo[\s\S]*sqlBuilder\.activeTab === 'builder'/,
  'loadSchemaTables 内部应能判断当前异步请求是否仍有效'
)
assert.match(
  loadSchemaTablesMatch[2],
  /if \(!isCurrentSchemaLoad\(\)\) \{[\s\S]*?return[\s\S]*?\}[\s\S]*datasourceInfo\.value = metadata\.datasource/,
  'loadSchemaTables 必须在写入 datasource/schema 响应式状态前拦截旧请求'
)
assert.match(
  ensureBuilderSchemaLoadedMatch[1],
  /if \(!isCurrentBuilderSchemaLoad\(startViewInfo,\s*requestSeq\)\)/,
  '元数据异步加载完成后应确认抽屉仍打开且仍是同一个图表，避免取消后写回草稿'
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
