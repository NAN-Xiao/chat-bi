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
  assert.match(source, /事件分析[\s\S]*?留存分析[\s\S]*?漏斗分析/, '分析模型需要提供事件、留存和漏斗分析')
  assert.match(source, /class="analysis-model-row"/)
  assert.match(source, /class="retention-heading-row"/)
  assert.match(
    source,
    /\.retention-heading-row\s*\{[\s\S]*?display:\s*flex;[\s\S]*?align-items:\s*center;[\s\S]*?gap:\s*20px;/,
    '留存分析标题和分析主体必须在同一行展示'
  )
  assert.match(
    source,
    /\.retention-subject-line\s*\{[\s\S]*?width:\s*auto;[\s\S]*?grid-template-columns:\s*auto minmax\(160px, 280px\) auto;/,
    '分析主体选择器必须使用紧凑宽度'
  )
  assert.match(
    source,
    /\.retention-event-editor\s*\{[\s\S]*?padding:\s*5px 24px 7px 0;/,
    '事件选择器必须与留存开关左对齐'
  )
  assert.match(
    source,
    /\.retention-config-label\s*\{[\s\S]*?padding:\s*0;/,
    '事件标签必须与留存开关左对齐'
  )
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
  assert.match(restoreBody, /value\.analysisModel === 'retention' \|\| value\.analysisModel === 'funnel'/)
  assert.match(restoreBody, /retention\.entityField/)
  assert.match(restoreBody, /retention\.initialEvent/)
  assert.match(restoreBody, /retention\.returnEvent/)
  assert.match(saveBody, /initialEventAlias:\s*sqlBuilder\.retention\.initialEventAlias\.trim\(\)/)
  assert.match(saveBody, /initialEventFilters:\s*\{[\s\S]*?compactBuilderFilters\(sqlBuilder\.retention\.initialEventFilters\)/)
  assert.match(saveBody, /returnEventAlias:\s*sqlBuilder\.retention\.returnEventAlias\.trim\(\)/)
  assert.match(saveBody, /returnEventFilters:\s*\{[\s\S]*?compactBuilderFilters\(sqlBuilder\.retention\.returnEventFilters\)/)
  assert.match(restoreBody, /restoreBuilderFilters\(retention\.initialEventFilters\?\.rules\)/)
  assert.match(restoreBody, /restoreBuilderFilters\(retention\.returnEventFilters\?\.rules\)/)
  assert.match(saveBody, /simultaneous:\s*\{[\s\S]*?enabled:\s*sqlBuilder\.retention\.simultaneous\.enabled/)
  assert.match(saveBody, /metricField:\s*sqlBuilder\.retention\.simultaneous\.enabled[\s\S]*?sqlBuilder\.retention\.simultaneous\.metricField/)
  assert.match(restoreBody, /simultaneous\.metricField/)
  assert.match(saveBody, /relatedProperty:\s*\{[\s\S]*?enabled:\s*sqlBuilder\.retention\.relatedProperty\.enabled/)
  assert.match(saveBody, /simultaneous\.enabled \? sqlBuilder\.retention\.simultaneous\.event : ''/)
  assert.match(saveBody, /relatedProperty\.enabled && sqlBuilder\.retention\.relatedProperty\.asGroup/)
  assert.match(saveBody, /funnel:\s*sqlBuilder\.analysisModel === 'funnel'/)
  assert.match(saveBody, /sqlBuilder\.funnel\.steps\.map/)
  assert.match(restoreBody, /sqlBuilder\.funnel\.windowDays/)
})

test('includes retention in AI context and preview signature', () => {
  const contextBody = source.match(/function collectBuilderAiContext\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const signatureBody = source.match(/function currentPreviewSignature\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''

  assert.match(contextBody, /analysisModel:\s*sqlBuilder\.analysisModel/)
  assert.match(contextBody, /content:\s*RETENTION_ANALYSIS_CONTEXT_CONTENT/)
  assert.match(
    source,
    /RETENTION_ANALYSIS_CONTEXT_CONTENT\s*=\s*'以某段时间做过初始事件的用户为样本，查看在指定日期后用户进行回访事件的留存情况'/
  )
  assert.match(contextBody, /entityField:\s*fieldOptionPayload/)
  assert.match(contextBody, /initialEventAlias:\s*sqlBuilder\.retention\.initialEventAlias\.trim\(\)/)
  assert.match(contextBody, /initialEventFilters:\s*\{[\s\S]*?filterContext\(sqlBuilder\.retention\.initialEventFilters\)/)
  assert.match(contextBody, /returnEventAlias:\s*sqlBuilder\.retention\.returnEventAlias\.trim\(\)/)
  assert.match(contextBody, /returnEventFilters:\s*\{[\s\S]*?filterContext\(sqlBuilder\.retention\.returnEventFilters\)/)
  assert.match(contextBody, /metricField:\s*sqlBuilder\.retention\.simultaneous\.enabled[\s\S]*?fieldOptionPayload\(sqlBuilder\.retention\.simultaneous\.metricField\)/)
  assert.match(signatureBody, /analysisModel:\s*sqlBuilder\.analysisModel/)
  assert.match(signatureBody, /retention:\s*sqlBuilder\.analysisModel === 'retention'/)
  assert.match(contextBody, /funnel:\s*sqlBuilder\.analysisModel === 'funnel'/)
  assert.match(signatureBody, /funnel:\s*sqlBuilder\.analysisModel === 'funnel'/)
})

test('model switching clears incompatible state and fixes retention to table', () => {
  const switchBody = source.match(/function handleAnalysisModelChange\(model: AnalysisModel\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''

  assert.match(switchBody, /sqlBuilder\.metricItems = \[\]/)
  assert.match(switchBody, /sqlBuilder\.calculatedMetrics = \[\]/)
  assert.match(switchBody, /form\.chartType = 'table'/)
  assert.match(switchBody, /resetRetentionConfig\(\)/)
  assert.match(switchBody, /form\.chartType = 'funnel'/)
  assert.match(switchBody, /resetFunnelConfig\(\)/)
})

test('allows the same event for initial and return retention roles', () => {
  const validationBody = source.match(/function retentionBlockingIssues\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''

  assert.doesNotMatch(validationBody, /initialEvent\s*===\s*sqlBuilder\.retention\.returnEvent/)
  assert.doesNotMatch(validationBody, /初始事件和回访事件不能相同/)
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

test('reuses event metric aggregation behavior for simultaneous retention metrics', () => {
  const simultaneousTemplate = source.match(
    /<div\s+class="retention-option-flow"[\s\S]*?<\/div>\s*<\/template>/
  )?.[0] || ''
  const aggregationOptions = source.match(
    /const builderAggregationOptions[\s\S]*?\n\]/
  )?.[0] || ''

  assert.match(aggregationOptions, /总次数[\s\S]*?求和[\s\S]*?平均值[\s\S]*?最大值[\s\S]*?最小值[\s\S]*?去重数/)
  assert.match(simultaneousTemplate, /v-for="option in builderAggregationOptions"/)
  assert.match(simultaneousTemplate, /v-if="sqlBuilder\.retention\.simultaneous\.aggregation !== 'count'"/)
  assert.match(simultaneousTemplate, /v-model="sqlBuilder\.retention\.simultaneous\.metricField"/)
  assert.match(simultaneousTemplate, /:options="retentionSimultaneousMetricFieldOptions\(\)"/)
  assert.match(source, /function retentionSimultaneousMetricFieldOptions\(\)[\s\S]*?return metricMeasureFieldOptions\(/)
  assert.doesNotMatch(source, /retentionSimultaneousAggregationOptions/)
})

test('adds rename and reused event-filter controls to both retention events', () => {
  assert.match(source, /aria-label="重命名初始事件"/)
  assert.match(source, /aria-label="筛选初始事件"/)
  assert.match(source, /aria-label="重命名回访事件"/)
  assert.match(source, /aria-label="筛选回访事件"/)
  assert.match(source, /class="retention-event-alias-row"[\s\S]*?class="retention-event-alias-input"/)
  assert.match(source, /v-model="retentionAliasDraft\.initial"[\s\S]*?:model-value="sqlBuilder\.retention\.initialEvent"/)
  assert.match(source, /v-model="retentionAliasDraft\.return"[\s\S]*?:model-value="sqlBuilder\.retention\.returnEvent"/)
  assert.equal((source.match(/title="重命名初始事件"/g) || []).length, 1, '初始事件需要铅笔重命名入口')
  assert.equal((source.match(/title="重命名回访事件"/g) || []).length, 1, '回访事件需要铅笔重命名入口')
  assert.match(source, /function beginRetentionEventRename\(target: RetentionEventTarget\)/)
  assert.match(source, /function finishRetentionEventRename\(target: RetentionEventTarget\)/)
  assert.match(source, /@keydown\.esc\.prevent="cancelRetentionEventRename\('initial'\)"/)
  assert.match(source, /\.retention-event-editor:hover[\s\S]*?background:\s*#f7f8fa/)
  assert.match(source, /\.retention-event-editor:hover \.retention-event-actions[\s\S]*?opacity:\s*1/)
  assert.match(source, /:nodes="sqlBuilder\.retention\.initialEventFilters"[\s\S]*?picker-mode="filter-property"/)
  assert.match(source, /:nodes="sqlBuilder\.retention\.returnEventFilters"[\s\S]*?picker-mode="filter-property"/)
  assert.match(source, /empty-text="暂无初始事件筛选"[\s\S]*?@empty="retentionFilterExpanded\.initial = false"/)
  assert.match(source, /empty-text="暂无回访事件筛选"[\s\S]*?@empty="retentionFilterExpanded\.return = false"/)
  assert.match(source, /function eventFilterFieldOptions\(eventValue: string\)/)
  assert.match(source, /return eventFilterFieldOptions\(item\.field\)/, '事件指标和留存事件必须复用同一筛选字段逻辑')
  assert.doesNotMatch(source, /eventTable !== 'event'/, '筛选范围不能写死业务事件表名')
})

test('provides ordered funnel steps with window and related-property controls', () => {
  assert.match(source, /class="funnel-heading-row"/)
  assert.match(source, /class="funnel-step-list"/)
  assert.match(source, /v-for="\(step, index\) in sqlBuilder\.funnel\.steps"/)
  assert.match(source, /sqlBuilder\.funnel\.windowDays/)
  assert.match(source, /sqlBuilder\.funnel\.relatedPropertyEnabled/)
  assert.match(source, /function addFunnelStep\(\)/)
  assert.match(source, /function removeFunnelStep\(index: number\)/)
  assert.match(source, /function funnelBlockingIssues\(\)/)
  assert.match(source, /step_field\s*\|\| resultConfig\.stepField \|\| 'step_name'/)
})
