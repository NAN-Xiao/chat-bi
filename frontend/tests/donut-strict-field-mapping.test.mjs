import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const dashboardEditor = readFileSync('src/views/dashboard/common/DashboardSqlEditor.vue', 'utf8')
const analysisAssistant = readFileSync('src/views/analysis-assistant/AnalysisAssistantDock.vue', 'utf8')
const chartInsightHeader = readFileSync('src/views/chat/component/ChartInsightHeader.vue', 'utf8')
const radialChart = readFileSync('src/views/chat/component/charts/RadialPartitionChart.ts', 'utf8')
const radialValidation = readFileSync('src/views/chat/component/charts/radialPartition.ts', 'utf8')

function functionBody(source, name) {
  const start = source.indexOf(`function ${name}(`)
  assert.ok(start >= 0, `${name} should exist`)
  const next = source.indexOf('\nfunction ', start + 1)
  return source.slice(start, next >= 0 ? next : undefined)
}

test('DashboardSqlEditor requires exactly one explicit donut value and category field', () => {
  const previewY = dashboardEditor.match(/const chartPreviewYFields = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)/)?.[1] || ''
  const previewSeries = dashboardEditor.match(/const chartPreviewSeriesFields = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)/)?.[1] || ''
  const buildChart = functionBody(dashboardEditor, 'buildChart')
  const donutBuild = buildChart.match(/if \(form\.chartType === 'donut'\) \{([\s\S]*?)\r?\n\s*\}/)?.[1] || ''
  const validateBeforeApply = functionBody(dashboardEditor, 'validateBeforeApply')
  const donutValidation = functionBody(dashboardEditor, 'donutFieldMappingValidationErrorKey')

  assert.match(previewY, /form\.chartType === 'donut'[\s\S]*form\.y\.length === 1[\s\S]*return form\.y/)
  assert.match(previewSeries, /form\.chartType === 'pie' \? effectiveSeriesField\.value \|\| form\.x : effectiveSeriesField\.value/)
  assert.match(buildChart, /form\.chartType === 'donut'[\s\S]*toAxes\(form\.y, \{ metrics: true \}\)[\s\S]*toAxes\(\[effectiveSeriesField\.value\]/)
  assert.doesNotMatch(donutBuild, /slice\(0,\s*1\)/)
  assert.match(donutValidation, /form\.y\.length !== 1/)
  assert.match(donutValidation, /donutSeriesFields\.value\.length === 0/)
  assert.match(validateBeforeApply, /validateDonutFieldMapping\(\)/)
  assert.ok(
    validateBeforeApply.indexOf('validateDonutFieldMapping()') < validateBeforeApply.indexOf('props.allowStaticApply'),
    'static apply must not bypass donut mapping validation'
  )
})

test('DashboardSqlEditor preserves invalid donut mappings until shared validation blocks every save path', () => {
  const resetFieldSelections = functionBody(dashboardEditor, 'resetFieldSelections')
  const initEditor = functionBody(dashboardEditor, 'initEditor')
  const buildChart = functionBody(dashboardEditor, 'buildChart')
  const writeEditorState = functionBody(dashboardEditor, 'writeEditorStateToViewInfo')
  const validateBeforeApply = functionBody(dashboardEditor, 'validateBeforeApply')

  assert.match(resetFieldSelections, /form\.chartType !== 'donut'[\s\S]*form\.y = form\.y\.filter/)
  assert.match(resetFieldSelections, /form\.chartType !== 'donut'[\s\S]*form\.series = ''/)
  assert.match(initEditor, /const persistedSeries = axisValues\(chart\.series\)[\s\S]*donutSeriesFields\.value = persistedSeries/)
  assert.match(buildChart, /form\.chartType === 'donut'[\s\S]*toAxes\(donutSeriesFields\.value\)/)
  assert.match(dashboardEditor, /function donutFieldMappingValidationErrorKey\(\)/)
  assert.match(dashboardEditor, /donutSeriesFields\.value\.length !== 1/)
  assert.match(validateBeforeApply, /validateDonutFieldMapping\(\)/)
  assert.match(writeEditorState, /validateDonutFieldMapping\(\)/)
})

test('AnalysisAssistantDock only falls back from pie series to x', () => {
  const getChartSeries = analysisAssistant.match(/const getChartSeries = \(chart\?: AnalysisChartConfig\) => \{([\s\S]*?)\r?\n\}/)?.[1] || ''

  assert.match(getChartSeries, /chart\?\.type === 'pie' && chart\.axis\?\.x/)
  assert.doesNotMatch(getChartSeries, /isRadialPartitionChartType\(chart\.type\)/)
})

test('ChartInsightHeader only falls back from pie series to x', () => {
  const categoryLabel = functionBody(chartInsightHeader, 'categoryLabel')

  assert.match(categoryLabel, /props\.chartType === 'donut'[\s\S]*seriesAxis\.value/)
  assert.match(categoryLabel, /props\.chartType === 'pie'[\s\S]*seriesAxis\.value \|\| xAxis\.value/)
  assert.doesNotMatch(
    categoryLabel,
    /isRadialPartitionChartType\(props\.chartType\)[\s\S]*seriesAxis\.value \|\| xAxis\.value/
  )
})

test('DashboardSqlEditor preserves pie single-value and x fallback compatibility', () => {
  const previewY = dashboardEditor.match(/const chartPreviewYFields = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)/)?.[1] || ''
  const previewSeries = dashboardEditor.match(/const chartPreviewSeriesFields = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)/)?.[1] || ''
  const buildChart = functionBody(dashboardEditor, 'buildChart')
  const validateBeforeApply = functionBody(dashboardEditor, 'validateBeforeApply')

  assert.match(previewY, /form\.chartType === 'pie'[\s\S]*form\.y\.slice\(0, 1\)/)
  assert.match(previewSeries, /form\.chartType === 'pie' \? effectiveSeriesField\.value \|\| form\.x/)
  assert.match(buildChart, /form\.chartType === 'pie'[\s\S]*form\.y\.slice\(0, 1\)[\s\S]*effectiveSeriesField\.value \|\| form\.x/)
  assert.match(validateBeforeApply, /form\.chartType === 'pie' && !\(form\.series \|\| form\.x\)/)
})

test('donut reports distinct missing and multiple-field validation codes while pie stays compatible', () => {
  assert.match(radialValidation, /'multiple_category_fields'/)
  assert.match(radialValidation, /'multiple_value_fields'/)
  assert.match(
    radialChart,
    /this\.radialOptions\.name === 'donut'[\s\S]*series\.length === 0 \? 'missing_category_field' : 'multiple_category_fields'/
  )
  assert.match(
    radialChart,
    /y\.length === 0 \? 'missing_value_field' : 'multiple_value_fields'/
  )
  assert.match(radialChart, /console\.debug\(\{ instance: this \}\)[\s\S]*return/)
})

test('four locales define explicit multiple-field validation messages', () => {
  for (const file of ['zh-CN.json', 'zh-TW.json', 'en.json', 'ko-KR.json']) {
    const locale = JSON.parse(readFileSync(`src/i18n/${file}`, 'utf8'))
    assert.equal(typeof locale.chat.chart_validation.multiple_category_fields, 'string')
    assert.equal(typeof locale.chat.chart_validation.multiple_value_fields, 'string')
  }
})
