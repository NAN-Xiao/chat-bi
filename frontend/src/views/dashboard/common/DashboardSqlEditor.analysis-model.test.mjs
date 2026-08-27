import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const source = readFileSync(
  fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url)),
  'utf8'
)

test('renders the analysis model selector before event metrics', () => {
  const modelIndex = source.indexOf('<span>分析模型</span>')
  const metricIndex = source.indexOf('<span>分析指标</span>')

  assert.ok(modelIndex >= 0, '图表配置卡必须提供分析模型下拉列表')
  assert.ok(metricIndex >= 0, '事件分析必须继续提供分析指标')
  assert.ok(modelIndex < metricIndex, '分析模型必须位于分析指标上方')
  assert.match(source, /事件分析[\s\S]*?留存分析/, '本期只需提供事件分析和留存分析')
  assert.match(source, /class="analysis-model-row"/)
  assert.match(source, /class="retention-heading-row"/)
})

test('loads retention events from the workspace event catalog', () => {
  const schemaLoaderBody = source.match(
    /async function loadSchemaTables\(startViewInfo: any, requestSeq: number\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction ensureBuilderSchemaLoaded/
  )?.[1] || ''

  assert.match(schemaLoaderBody, /trackingConfigApi\.eventCatalog\(\)/)
  assert.match(schemaLoaderBody, /trackingEventCatalog:\s*trackingEventCatalogResult/)
  assert.match(schemaLoaderBody, /hasOwnProperty\.call\(cachedMetadata, 'trackingEventCatalog'\)/)
  assert.doesNotMatch(schemaLoaderBody, /buildTrackingEventCatalogFromConfig/)
})

test('persists and restores retention configuration in the SQL builder', () => {
  const saveBody = source.match(/function builderConfigForSave\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const restoreBody = source.match(
    /function restoreSqlBuilderState\(value: any\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction formulaTokensReferenceMetricIds/
  )?.[1] || ''

  assert.match(saveBody, /analysisModel:\s*sqlBuilder\.analysisModel/)
  assert.match(saveBody, /retention:\s*sqlBuilder\.analysisModel === 'retention'/)
  assert.match(restoreBody, /value\.analysisModel === 'retention' \? 'retention' : 'event'/)
  assert.match(restoreBody, /retention\.entityField/)
  assert.match(restoreBody, /retention\.initialEvent/)
  assert.match(restoreBody, /retention\.returnEvent/)
  assert.match(saveBody, /simultaneous:\s*\{[\s\S]*?enabled:\s*sqlBuilder\.retention\.simultaneous\.enabled/)
  assert.match(saveBody, /relatedProperty:\s*\{[\s\S]*?enabled:\s*sqlBuilder\.retention\.relatedProperty\.enabled/)
  assert.match(saveBody, /simultaneous\.enabled \? sqlBuilder\.retention\.simultaneous\.event : ''/)
  assert.match(saveBody, /relatedProperty\.enabled && sqlBuilder\.retention\.relatedProperty\.asGroup/)
})

test('includes retention in AI context and preview signature', () => {
  const contextBody = source.match(/function collectBuilderAiContext\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const signatureBody = source.match(/function currentPreviewSignature\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''

  assert.match(contextBody, /analysisModel:\s*sqlBuilder\.analysisModel/)
  assert.match(contextBody, /entityField:\s*fieldOptionPayload/)
  assert.match(signatureBody, /analysisModel:\s*sqlBuilder\.analysisModel/)
  assert.match(signatureBody, /retention:\s*sqlBuilder\.analysisModel === 'retention'/)
})

test('model switching clears incompatible state and fixes retention to table', () => {
  const switchBody = source.match(/function handleAnalysisModelChange\(model: AnalysisModel\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''

  assert.match(switchBody, /sqlBuilder\.metricItems = \[\]/)
  assert.match(switchBody, /sqlBuilder\.calculatedMetrics = \[\]/)
  assert.match(switchBody, /form\.chartType = 'table'/)
  assert.match(switchBody, /resetRetentionConfig\(\)/)
})

test('keeps simultaneous and related-property controls while removing the red-box options', () => {
  assert.match(source, />使用同时展示</)
  assert.match(source, />同时展示回访的用户参与</)
  assert.match(source, />使用关联属性</)
  assert.match(source, />关联属性作为分组展示</)
  assert.match(source, /class="retention-event-stack"/)
  assert.match(source, /class="retention-field-block">\s*<span class="retention-config-label">初始事件/)
  assert.match(source, /class="retention-field-block">\s*<span class="retention-config-label">回访事件/)
  assert.doesNotMatch(source, /retention-event-grid/)
  assert.doesNotMatch(source, />留存周期</)
  assert.doesNotMatch(source, />隐藏未完成周期</)
  assert.doesNotMatch(source, /sqlBuilder\.retention\.(?:windowDays|resultMode|displayMode|hideIncomplete)/)
})
