import assert from 'node:assert/strict'
import fs from 'node:fs'

const source = fs.readFileSync(
  new URL('./DashboardSqlEditor.vue', import.meta.url),
  'utf8'
)

assert.match(
  source,
  /const trackingConfig = ref<any>\(null\)/,
  '编辑器需要保留工作空间原始埋点配置'
)
assert.match(
  source,
  /const eventFieldScope = computed\(\(\) =>/,
  '编辑器需要根据当前数据源、Schema 和埋点配置计算事件范围'
)
assert.match(
  source,
  /const eventScopedSchemaFieldOptions = computed\(\(\) =>/,
  '五类字段候选需要共享默认事件表范围'
)
assert.match(
  source,
  /getEventScopedFields\(schemaFieldOptions\.value, eventFieldScope\.value\)/,
  '事件范围候选必须调用独立纯函数'
)
assert.match(
  source,
  /eventFieldScope\.value\.status === 'active'/,
  '事件目录只能在有效事件范围中启用'
)
assert.match(
  source,
  /function builderEventScopeIssues\(\)/,
  '旧跨表配置必须产生确定性本地错误'
)
assert.match(
  source,
  /当前事件模式不允许使用表/,
  '跨表错误需要明确说明事件模式范围'
)
assert.doesNotMatch(
  source,
  /const prunedInvalidSelections = pruneInvalidBuilderSelections\(\)/,
  '加载旧配置时不能静默清理并持久化字段'
)
assert.match(
  source,
  /metadata\.trackingConfig/,
  'metadata 缓存结果需要返回原始埋点配置'
)
assert.match(
  source,
  /event-scope-alert/,
  '事件配置失效时需要在配置器中显示明确状态'
)

const applyValidation = source.match(
  /function validateBeforeApply\(\) \{([\s\S]*?)\n\}/
)
assert.ok(applyValidation, '编辑器需要保留应用前校验')
assert.doesNotMatch(
  applyValidation[1],
  /builderEventScopeIssues\(\)/,
  '已预览的 SQL 图表应用到画布时不应被事件配置状态拦截'
)

console.log('dashboard SQL editor event table scope tests passed')
