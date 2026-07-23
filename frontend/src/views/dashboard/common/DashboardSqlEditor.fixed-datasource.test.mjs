import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'DashboardSqlEditor.vue')
const source = readFileSync(componentPath, 'utf8')
const coordinatorPath = join(currentDir, 'dashboardSqlApplyCoordinator.ts')
const coordinatorSource = readFileSync(coordinatorPath, 'utf8')

function functionSource(name, nextName) {
  const match = source.match(
    new RegExp(`(?:async )?function ${name}\\([\\s\\S]*?\\r?\\n\\}(?=\\r?\\n\\r?\\n(?:async )?function ${nextName}\\()`)
  )
  assert.ok(match, `需要保留 ${name} 函数`)
  return match[0]
}

assert.match(source, /fixedDatasourceId\?: number \| string \| null/)
assert.match(source, /allowExternalSources\?: boolean/)
assert.match(source, /applyExecutor\?: \(viewInfo: any\) => Promise<boolean>/)
assert.match(source, /const effectiveDatasourceId = computed/)
assert.match(source, /props\.fixedDatasourceId \?\? props\.viewInfo\?\.datasource/)
assert.match(source, /if \(!props\.allowExternalSources\)[\s\S]*sourceTypes[\s\S]*\['sql'\]/)
assert.match(source, /const applied = await props\.applyExecutor\(props\.viewInfo\)/)
assert.match(source, /if \(!applied\) return/)

assert.match(
  source,
  /fixedDatasourceId:\s*null,[\s\S]*allowExternalSources:\s*true,[\s\S]*applyExecutor:\s*undefined,/,
  '新属性必须提供保持普通看板行为不变的默认值'
)

const initEditorMatch = source.match(/function initEditor\(\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nwatch\(/)
assert.ok(initEditorMatch, '需要保留 initEditor 函数')
const initEditorSource = initEditorMatch[0]
assert.match(
  initEditorSource,
  /viewInfo\.datasource = effectiveDatasourceId\.value/,
  '固定模式打开时必须同步 viewInfo.datasource'
)
assert.match(
  initEditorSource,
  /datasource:\s*effectiveDatasourceId\.value/,
  '固定模式打开时必须同步 sourceConfig.sql.datasource'
)
assert.match(
  initEditorSource,
  /if \(!props\.allowExternalSources\)[\s\S]*sourceTypes = \['sql'\]/,
  '禁用外部来源时必须强制初始化为 SQL 单来源'
)

const loadSchemaTablesSource = functionSource('loadSchemaTables', 'ensureBuilderSchemaLoaded')
assert.match(
  loadSchemaTablesSource,
  /const datasourceId = effectiveDatasourceId\.value/,
  'schema 元数据请求必须使用有效数据源'
)
assert.doesNotMatch(
  loadSchemaTablesSource,
  /startViewInfo\?\.datasource|props\.viewInfo\?\.datasource/,
  'schema 元数据请求不能回退读取普通看板数据源'
)

const generateBuilderAiSqlSource = functionSource('generateBuilderAiSql', 'calculateBuilderSql')
assert.match(
  generateBuilderAiSqlSource,
  /datasource:\s*effectiveDatasourceId\.value/,
  '配置 Agent 的 SQL schema 上下文必须使用有效数据源'
)
assert.doesNotMatch(
  generateBuilderAiSqlSource,
  /props\.viewInfo\??\.datasource/,
  '配置 Agent 不能重新读取普通看板数据源'
)

const buildSqlPreviewRequest = functionSource('buildSqlPreviewRequest', 'previewSqlSource')
assert.match(
  buildSqlPreviewRequest,
  /datasource:\s*effectiveDatasourceId\.value/,
  'SQL 预览请求必须使用有效数据源'
)
const previewSqlSource = functionSource('previewSqlSource', 'previewMcpSource')
assert.match(
  previewSqlSource,
  /sqlPreviewExecutor\.value\(buildSqlPreviewRequest\(/g,
  '所有 SQL 预览必须统一通过可注入执行器'
)
assert.doesNotMatch(
  previewSqlSource,
  /props\.viewInfo\??\.datasource/,
  'SQL 预览不能重新读取普通看板数据源'
)
assert.match(
  source,
  /resolveDashboardSqlPreviewExecutor\(props\.previewExecutor,[\s\S]*dashboardApi\.preview_sql/,
  '普通模式必须保留现有 SQL 预览接口作为默认执行器'
)

assert.match(
  source,
  /const eventFieldScope = computed\([\s\S]*datasourceId:\s*effectiveDatasourceId\.value/,
  '事件字段 schema 范围必须使用有效数据源'
)
assert.match(
  source,
  /function currentPreviewSignature\([\s\S]*datasource:\s*effectiveDatasourceId\.value/,
  'SQL 预览签名必须使用有效数据源'
)

const writeEditorStateSource = functionSource('writeEditorStateToViewInfo', 'persistEditorDraftToViewInfo')
assert.match(
  writeEditorStateSource,
  /props\.viewInfo\.datasource = hasSqlSource\.value \? effectiveDatasourceId\.value : null/,
  '保存时 viewInfo.datasource 必须写入有效数据源'
)
assert.match(
  writeEditorStateSource,
  /datasource:\s*effectiveDatasourceId\.value/,
  '保存时 sourceConfig.sql.datasource 必须写入有效数据源'
)

assert.match(source, /v-if="props\.allowExternalSources"[\s\S]*v-model="mcpSourceEnabled"/)
assert.match(source, /v-if="props\.allowExternalSources"[\s\S]*v-model="sqlSourceEnabled"/)

const applyChangeSource = functionSource('applyChange', 'closeDrawer')
assert.match(applyChangeSource, /async function applyChange\(\)/)
assert.match(applyChangeSource, /applying\.value/)
assert.match(
  applyChangeSource,
  /writeEditorStateToViewInfo\(\{[\s\S]*emit:\s*false,[\s\S]*close:\s*false,[\s\S]*notify:\s*false/,
  '异步保存完成前不能发事件、关闭抽屉或提示成功'
)
assert.match(
  applyChangeSource,
  /if \(props\.applyExecutor\)[\s\S]*const applied = await props\.applyExecutor\(props\.viewInfo\)[\s\S]*if \(!applied\) return/,
  '异步保存返回 false 时必须保持抽屉打开且不发 applied'
)
assert.match(
  applyChangeSource,
  /onApplied:\s*\(viewInfo\) => emits\('applied', viewInfo\)[\s\S]*visible\.value = false[\s\S]*ElMessage\.success/,
  '仅保存成功后才能发 applied、关闭抽屉并提示成功'
)
assert.match(applyChangeSource, /return runDashboardSqlApply\(\{/)
assert.match(coordinatorSource, /finally \{[\s\S]*options\.setApplying\(false\)/)
assert.match(source, /<el-button type="primary" :loading="applying" @click="applyChange">/)

console.log('DashboardSqlEditor fixed datasource contracts passed')
