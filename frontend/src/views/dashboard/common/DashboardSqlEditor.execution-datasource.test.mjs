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
const sourceConfigSaveStart = editor.indexOf('props.viewInfo.sourceConfig = {')
const sourceConfigSaveEnd = editor.indexOf('props.viewInfo.primarySource', sourceConfigSaveStart)
const sourceConfigSave = editor.slice(sourceConfigSaveStart, sourceConfigSaveEnd)
assert.ok(sourceConfigSaveStart >= 0 && sourceConfigSaveEnd > sourceConfigSaveStart)
assert.doesNotMatch(
  sourceConfigSave,
  /datasource:\s*selectedExecutionDatasourceId\.value/,
  'sourceConfig.sql 不得继续保存重复的数据源字段'
)
assert.match(editor, /图表执行数据源配置冲突/, '历史内外数据源冲突必须明确提示')
assert.match(editor, /图表只有旧版执行数据源配置/, '历史内层独有数据源必须进入迁移提示')
assert.match(editor, /图表未配置执行数据源/, '已有 SQL 缺少数据源时不得静默预选绑定源')
assert.match(
  editor,
  /:disabled="executionDatasourceOptions\.length <= 1 && !executionDatasourceError"/,
  '历史配置错误时即使只有一个候选也必须允许用户重新选择'
)
assert.match(editor, /label="执行数据源"/, '图表配置必须展示执行数据源选择器')
