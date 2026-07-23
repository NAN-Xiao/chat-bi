/** 验证 SQL 图表编辑器使用受控的空间执行数据源。 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const editor = readFileSync(join(currentDir, 'DashboardSqlEditor.vue'), 'utf8')
const api = readFileSync(join(currentDir, '../../../api/dashboard.ts'), 'utf8')

assert.match(
  api,
  /execution_datasources:\s*\(\)\s*=>\s*request\.get\('\/dashboard\/execution-datasources'\)/,
  '看板 API 必须提供当前空间的图表执行数据源候选接口'
)
assert.match(editor, /selectedExecutionDatasourceId/, '编辑器必须保存当前选择的数据源 ID')
assert.match(editor, /dashboardApi\.execution_datasources\(\)/, '编辑器必须从受控接口加载候选数据源')
assert.match(editor, /function resetExecutionDatasourceDependentState\(\)/, '切换数据源必须清空旧配置')
assert.match(
  editor,
  /datasource:\s*selectedExecutionDatasourceId\.value/,
  'SQL 预览必须使用当前选择的数据源'
)
assert.match(
  editor,
  /viewInfo\.datasource\s*=\s*selectedExecutionDatasourceId\.value/,
  '保存图表必须持久化当前选择的数据源'
)
assert.match(editor, /label="执行数据源"/, '图表配置必须展示执行数据源选择器')
