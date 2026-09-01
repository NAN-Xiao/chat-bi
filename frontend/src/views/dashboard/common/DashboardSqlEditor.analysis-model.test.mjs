import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const source = readFileSync(
  fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url)),
  'utf8'
)
const distributionMetricPickerSource = readFileSync(
  fileURLToPath(new URL('./DistributionMetricPicker.vue', import.meta.url)),
  'utf8'
)
const distributionIntervalSettingsSource = readFileSync(
  fileURLToPath(new URL('./DistributionIntervalSettings.vue', import.meta.url)),
  'utf8'
)
const funnelWindowPickerSource = readFileSync(
  fileURLToPath(new URL('./FunnelWindowPicker.vue', import.meta.url)),
  'utf8'
)
const intervalLimitPickerSource = readFileSync(
  fileURLToPath(new URL('./IntervalLimitPicker.vue', import.meta.url)),
  'utf8'
)
const pathEventListSource = readFileSync(
  fileURLToPath(new URL('./PathEventList.vue', import.meta.url)),
  'utf8'
)
const pathSessionGapPickerSource = readFileSync(
  fileURLToPath(new URL('./PathSessionGapPicker.vue', import.meta.url)),
  'utf8'
)
const attributionWindowPickerSource = readFileSync(
  fileURLToPath(new URL('./AttributionWindowPicker.vue', import.meta.url)),
  'utf8'
)

test('renders the analysis model selector before event metrics', () => {
  const modelIndex = source.indexOf('<span>分析模型</span>')
  const metricIndex = source.indexOf('<span>分析指标</span>')

  assert.ok(modelIndex >= 0, '图表配置卡必须提供分析模型下拉列表')
  assert.ok(metricIndex >= 0, '事件分析必须继续提供分析指标')
  assert.ok(modelIndex < metricIndex, '分析模型必须位于分析指标上方')
  assert.match(source, /事件分析[\s\S]*?留存分析[\s\S]*?漏斗分析[\s\S]*?分布分析/, '分析模型需要提供事件、留存、漏斗和分布分析')
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
  assert.match(restoreBody, /\['retention', 'funnel', 'distribution', 'interval', 'path', 'revenue', 'attribution', 'ranking'\]\.includes\(value\.analysisModel\)/)
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
  assert.match(saveBody, /window:\s*normalizeFunnelWindow\(sqlBuilder\.funnel\.window\)/)
  assert.doesNotMatch(saveBody, /windowDays/, '新配置不能继续保存旧 windowDays 字段')
  assert.match(restoreBody, /normalizeFunnelWindow\(funnel\.window, funnel\.windowDays\)/)
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
  assert.match(
    source,
    /content:\s*'以某段时间做过步骤1的用户为样本，查看窗口期内，指定步骤下用户的转化情况'/
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
  assert.match(source, /<FunnelWindowPicker v-model="sqlBuilder\.funnel\.window"/)
  assert.match(source, /window:\s*normalizeFunnelWindow\(sqlBuilder\.funnel\.window\)/)
  assert.match(source, /sqlBuilder\.funnel\.relatedPropertyEnabled/)
  assert.match(source, /function addFunnelStep\(\)/)
  assert.match(source, /function removeFunnelStep\(index: number\)/)
  assert.match(source, /function funnelBlockingIssues\(\)/)
  assert.match(source, /step_field\s*\|\| resultConfig\.stepField \|\| 'step_name'/)
  assert.match(funnelWindowPickerSource, />当天</)
  assert.match(funnelWindowPickerSource, /天（即24小时）/)
  assert.match(funnelWindowPickerSource, /label:\s*'小时'/)
  assert.match(funnelWindowPickerSource, /label:\s*'分钟'/)
  assert.match(funnelWindowPickerSource, /presets:[\s\S]*?day:\s*\[1, 7, 14\]/)
  assert.match(funnelWindowPickerSource, /:teleported="false"/)
  assert.doesNotMatch(funnelWindowPickerSource, /retention|distribution|interval|path/i)
})

test('keeps distribution analysis configuration and controls isolated from other models', () => {
  const saveBody = source.match(/function builderConfigForSave\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const restoreBody = source.match(
    /function restoreSqlBuilderState\(value: any\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction formulaTokensReferenceMetricIds/
  )?.[1] || ''
  const contextBody = source.match(/function collectBuilderAiContext\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const switchBody = source.match(/function handleAnalysisModelChange\(model: AnalysisModel\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''

  assert.match(source, /type AnalysisModel = 'event' \| 'retention' \| 'funnel' \| 'distribution'/)
  assert.match(source, /const isDistributionAnalysis = computed\(\(\) => sqlBuilder\.analysisModel === 'distribution'\)/)
  assert.match(saveBody, /distribution:\s*sqlBuilder\.analysisModel === 'distribution'/)
  assert.match(restoreBody, /\['retention', 'funnel', 'distribution', 'interval', 'path', 'revenue', 'attribution', 'ranking'\]\.includes\(value\.analysisModel\)/)
  assert.match(contextBody, /distribution:\s*sqlBuilder\.analysisModel === 'distribution'/)
  assert.match(
    source,
    /content:\s*'一段时间内，指定用户参与某一事件的总完成次数或属性值按个人聚合后的全员分布情况'/
  )
  assert.match(switchBody, /sqlBuilder\.analysisModel === 'distribution'/)
  assert.match(switchBody, /resetDistributionConfig\(\)/)
  assert.match(source, /<DistributionMetricPicker[\s\S]*?@update:modelValue="updateDistributionMetric"/)
  assert.match(source, /<DistributionIntervalSettings[\s\S]*?@update:modelValue="updateDistributionInterval"/)
  assert.match(source, />使用同时展示</)
  assert.match(source, /function distributionBlockingIssues\(\)/)
  assert.match(source, /form\.chartType = 'table'/)
  assert.match(source, /total_entities_field[\s\S]*?'total_entities'/)
  assert.equal((distributionMetricPickerSource.match(/:teleported="false"/g) || []).length, 1)
  assert.match(distributionMetricPickerSource, /class="distribution-metric-group"/)
  assert.match(distributionMetricPickerSource, /class="distribution-metric-group distribution-property-group"/)
  assert.match(distributionMetricPickerSource, /class="distribution-aggregation-panel"/)
  assert.match(distributionMetricPickerSource, /function choosePreset[\s\S]*?emits\('update:modelValue'/)
  assert.match(distributionMetricPickerSource, /function chooseAggregation[\s\S]*?emits\('update:modelValue'/)
  assert.doesNotMatch(distributionMetricPickerSource, />取消</)
  assert.doesNotMatch(distributionMetricPickerSource, />应用</)
  assert.doesNotMatch(distributionMetricPickerSource, /grid-template-columns:\s*repeat\(3/)
  assert.match(distributionMetricPickerSource, /distribution-metric-popper[\s\S]*?max-width:\s*calc\(100vw - 24px\)/)
  assert.match(distributionIntervalSettingsSource, /distribution-interval-popper[\s\S]*?max-width:\s*calc\(100vw - 24px\)/)
})

test('keeps distribution simultaneous event and aggregation on the same row', () => {
  assert.match(
    source,
    /class="distribution-simultaneous-core-controls"[\s\S]*?v-model="sqlBuilder\.distribution\.simultaneous\.event"[\s\S]*?<span>的<\/span>[\s\S]*?v-model="sqlBuilder\.distribution\.simultaneous\.aggregation"/,
    '同时展示的参与事件与聚合方式必须放在同一个不可拆分的控件组内'
  )
  assert.match(
    source,
    /\.distribution-simultaneous-core-controls\s*\{[\s\S]*?display:\s*grid;[\s\S]*?grid-template-columns:\s*minmax\(160px, 280px\) auto 160px;/,
    '同时展示的参与事件与聚合方式必须保持同行布局'
  )
})

test('keeps interval analysis isolated and exposes the reference controls', () => {
  const saveBody = source.match(/function builderConfigForSave\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const restoreBody = source.match(
    /function restoreSqlBuilderState\(value: any\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction formulaTokensReferenceMetricIds/
  )?.[1] || ''
  const contextBody = source.match(/function collectBuilderAiContext\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const switchBody = source.match(/function handleAnalysisModelChange\(model: AnalysisModel\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''

  assert.match(source, /type AnalysisModel = 'event' \| 'retention' \| 'funnel' \| 'distribution' \| 'interval'/)
  assert.match(source, /const isIntervalAnalysis = computed\(\(\) => sqlBuilder\.analysisModel === 'interval'\)/)
  assert.match(saveBody, /interval:\s*sqlBuilder\.analysisModel === 'interval'/)
  assert.match(restoreBody, /sqlBuilder\.interval\.startEvent/)
  assert.match(restoreBody, /sqlBuilder\.interval\.endEvent/)
  assert.match(restoreBody, /clampIntervalLimitSeconds\(interval\.limitSeconds\)/)
  assert.match(contextBody, /interval:\s*sqlBuilder\.analysisModel === 'interval'/)
  assert.match(contextBody, /comparison:\s*'equal'/)
  assert.match(switchBody, /sqlBuilder\.analysisModel === 'interval'/)
  assert.match(switchBody, /resetIntervalConfig\(\)/)
  assert.match(source, />间隔分析</)
  assert.match(source, />起点事件</)
  assert.match(source, />终点事件</)
  assert.match(source, />使用关联属性</)
  assert.match(source, />间隔上限</)
  assert.match(source, /interval-limit-content[\s\S]*?起点事件到终点事件的间隔不超过[\s\S]*?<IntervalLimitPicker v-model="sqlBuilder\.interval\.limitSeconds"/)
  assert.match(source, /function intervalBlockingIssues\(\)/)
  assert.match(source, /interval_count_field[\s\S]*?'interval_count'/)
  assert.match(intervalLimitPickerSource, /hour:\s*\[1, 3, 12\]/)
  assert.match(intervalLimitPickerSource, /天（即24小时）/)
  assert.match(intervalLimitPickerSource, /interval-limit-menu[\s\S]*?interval-limit-values/)
  assert.match(intervalLimitPickerSource, /ArrowRight/)
  assert.match(intervalLimitPickerSource, /INTERVAL_LIMIT_MIN_SECONDS/)
  assert.match(intervalLimitPickerSource, /INTERVAL_LIMIT_MAX_SECONDS/)
  assert.match(intervalLimitPickerSource, /interval-limit-popper[\s\S]*?max-width:\s*calc\(100vw - 24px\)/)
})

test('keeps path analysis isolated and exposes event split and session controls', () => {
  const saveBody = source.match(/function builderConfigForSave\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const restoreBody = source.match(
    /function restoreSqlBuilderState\(value: any\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction formulaTokensReferenceMetricIds/
  )?.[1] || ''
  const contextBody = source.match(/function collectBuilderAiContext\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const signatureBody = source.match(/function currentPreviewSignature\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const switchBody = source.match(/function handleAnalysisModelChange\(model: AnalysisModel\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''

  assert.match(source, /type AnalysisModel = 'event' \| 'retention' \| 'funnel' \| 'distribution' \| 'interval' \| 'path'/)
  assert.match(source, /const isPathAnalysis = computed\(\(\) => sqlBuilder\.analysisModel === 'path'\)/)
  assert.match(saveBody, /path:\s*sqlBuilder\.analysisModel === 'path'/)
  assert.match(restoreBody, /PATH_EVENT_LIMIT/)
  assert.match(restoreBody, /sqlBuilder\.path\.initialEvent/)
  assert.match(restoreBody, /sqlBuilder\.path\.sessionGapSeconds/)
  assert.match(contextBody, /path:\s*sqlBuilder\.analysisModel === 'path'/)
  assert.match(signatureBody, /path:\s*sqlBuilder\.analysisModel === 'path'/)
  assert.match(switchBody, /sqlBuilder\.analysisModel === 'path'/)
  assert.match(switchBody, /resetPathConfig\(\)/)
  assert.match(source, /<PathEventList[\s\S]*?:max-events="PATH_EVENT_LIMIT"/)
  assert.match(source, /<PathSessionGapPicker v-model="sqlBuilder\.path\.sessionGapSeconds"/)
  assert.match(source, /class="path-initial-event-tag"/)
  assert.match(source, /路径分析只能使用桑基图结果|桑基图/)
  assert.match(pathEventListSource, /class="path-event-trigger"/)
  assert.match(pathEventListSource, /class="path-split-list"/)
  assert.match(pathEventListSource, /class="path-add-split"/)
  assert.match(pathEventListSource, /function addSplitEvent\(event: string\)/)
  assert.match(pathEventListSource, /function removeSplitItem\(event: string\)/)
  assert.match(pathEventListSource, /function toggleEvent\(value: string\)/)
  assert.match(pathEventListSource, /function updateSplitProperty\(event: string, value: string\)/)
  assert.match(pathEventListSource, /splitProperties: \[value\]/)
  assert.doesNotMatch(pathEventListSource, /\bmultiple\b/)
  assert.match(source, /路径分析每个参与事件只能选择一个拆分属性/)
  assert.match(source, /路径分析拆分项请选择拆分属性/)
  assert.match(source, />分析路径以</)
  assert.match(pathEventListSource, /最多选择 \{\{ maxEvents \}\} 个事件/)
  assert.match(pathSessionGapPickerSource, /PATH_SESSION_GAP_MIN_SECONDS/)
  assert.match(pathSessionGapPickerSource, /PATH_SESSION_GAP_MAX_SECONDS/)
  assert.match(pathSessionGapPickerSource, /会话间隔数值/)
  assert.match(pathSessionGapPickerSource, /会话间隔单位/)
  assert.match(pathSessionGapPickerSource, /秒/)
  assert.match(pathSessionGapPickerSource, /分钟/)
  assert.match(pathSessionGapPickerSource, /小时/)
  assert.match(pathSessionGapPickerSource, /path-session-gap-info/)
  assert.match(pathSessionGapPickerSource, /:controls="false"/)
})

test('keeps revenue analysis isolated with cohort, metric, cost, and observation controls', () => {
  const saveBody = source.match(/function builderConfigForSave\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const restoreBody = source.match(
    /function restoreSqlBuilderState\(value: any\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction formulaTokensReferenceMetricIds/
  )?.[1] || ''
  const contextBody = source.match(/function collectBuilderAiContext\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const switchBody = source.match(/function handleAnalysisModelChange\(model: AnalysisModel\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''

  assert.match(source, /type AnalysisModel = 'event' \| 'retention' \| 'funnel' \| 'distribution' \| 'interval' \| 'path' \| 'revenue' \| 'attribution'/)
  assert.match(source, /const isRevenueAnalysis = computed\(\(\) => sqlBuilder\.analysisModel === 'revenue'\)/)
  assert.match(saveBody, /revenue:\s*sqlBuilder\.analysisModel === 'revenue'/)
  assert.match(restoreBody, /sqlBuilder\.revenue\.paymentEvent/)
  assert.match(restoreBody, /sqlBuilder\.revenue\.observationDays = clampRevenueObservationDays/)
  assert.match(contextBody, /revenue:\s*sqlBuilder\.analysisModel === 'revenue'/)
  assert.match(switchBody, /sqlBuilder\.analysisModel === 'revenue'/)
  assert.match(switchBody, /resetRevenueConfig\(\)/)
  assert.match(source, /<RevenueMetricPicker[\s\S]*?@update:modelValue="updateRevenueMetric"/)
  assert.match(source, />同期群</)
  assert.match(source, />付费事件</)
  assert.match(source, />收入口径</)
  assert.match(source, />成本数据</)
  assert.match(source, />观察时长</)
  assert.match(source, /function revenueBlockingIssues\(\)/)
  assert.match(source, /revenue_cohort_table|cohort_date_field/)
  assert.match(source, /revenueMetricUsesProperty\(sqlBuilder\.revenue\.metric\.method\)/)
  assert.match(source, /revenue-heading-row/)
  assert.match(source, /revenue-subject-line/)
  assert.match(source, /const isAttributionAnalysis = computed\(\(\) => sqlBuilder\.analysisModel === 'attribution'\)/)
  assert.match(saveBody, /attribution:\s*sqlBuilder\.analysisModel === 'attribution'/)
  assert.match(restoreBody, /sqlBuilder\.attribution\.targetEvent/)
  assert.match(restoreBody, /normalizeAttributionWindow\(attribution\.window\)/)
  assert.match(contextBody, /attribution:\s*sqlBuilder\.analysisModel === 'attribution'/)
  assert.match(switchBody, /sqlBuilder\.analysisModel === 'attribution'/)
  assert.match(switchBody, /resetAttributionConfig\(\)/)
  assert.match(source, /<AttributionWindowPicker v-model="sqlBuilder\.attribution\.window"/)
  assert.match(source, />归因方式</)
  assert.match(attributionWindowPickerSource, /窗口期/)
  assert.match(source, />目标事件</)
  assert.match(source, /直接转化参与归因计算/)
  assert.match(source, />归因事件</)
  assert.match(source, /function attributionBlockingIssues\(\)/)
  assert.match(source, /ATTRIBUTION_EVENT_LIMIT/)
  assert.match(source, /form\.chartType = 'table'/)
})

test('keeps ranking analysis isolated with rank, tie, metric, and property controls', () => {
  const saveBody = source.match(/function builderConfigForSave\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const restoreBody = source.match(
    /function restoreSqlBuilderState\(value: any\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction formulaTokensReferenceMetricIds/
  )?.[1] || ''
  const contextBody = source.match(/function collectBuilderAiContext\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const signatureBody = source.match(/function currentPreviewSignature\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const switchBody = source.match(/function handleAnalysisModelChange\(model: AnalysisModel\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''

  assert.match(source, /type AnalysisModel = .*'ranking'/)
  assert.match(source, /const isRankingAnalysis = computed\(\(\) => sqlBuilder\.analysisModel === 'ranking'\)/)
  assert.match(source, /\{ label: '排行榜', value: 'ranking'/)
  assert.match(saveBody, /ranking:\s*sqlBuilder\.analysisModel === 'ranking'/)
  assert.match(restoreBody, /sqlBuilder\.ranking\.metric = restoreRankingMetric/)
  assert.match(contextBody, /ranking: sqlBuilder\.analysisModel === 'ranking'/)
  assert.match(signatureBody, /ranking: sqlBuilder\.analysisModel === 'ranking'/)
  assert.match(switchBody, /sqlBuilder\.analysisModel === 'ranking'/)
  assert.match(switchBody, /resetRankingConfig\(\)/)
  assert.match(source, /class="ranking-heading-row"/)
  assert.match(source, />按指标排名</)
  assert.match(source, />并列名次处理</)
  assert.match(source, />当出现相同值时，将</)
  assert.match(source, /<el-select v-model="sqlBuilder\.ranking\.tieHandling" class="ranking-tie-select">/)
  assert.doesNotMatch(source, /<el-radio-group v-model="sqlBuilder\.ranking\.tieHandling">/)
  assert.doesNotMatch(source, /aria-label="重命名排行指标"/)
  assert.match(source, />同时展示指标</)
  assert.match(source, />同时展示属性</)
  assert.match(source, /function rankingBlockingIssues\(\)/)
  assert.match(source, /ranking_table|ranking_value/)
  assert.match(source, /direction: 'asc' \| 'desc'/)
  assert.match(source, /tieHandling: 'default' \| 'skip' \| 'dense'/)
  assert.match(source, /form\.chartType = 'table'/)
})
