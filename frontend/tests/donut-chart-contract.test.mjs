import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

test('radial chart type predicate recognizes pie and donut only', async () => {
  const source = readFileSync('src/views/chat/component/chartTypes.ts', 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
  const { isRadialPartitionChartType } = await import(moduleUrl)

  assert.equal(isRadialPartitionChartType('pie'), true)
  assert.equal(isRadialPartitionChartType('donut'), true)
  assert.equal(isRadialPartitionChartType('bar'), false)
})

test('donut is registered across chart rendering and editing surfaces', () => {
  const files = {
    types: readFileSync('src/views/chat/component/BaseChart.ts', 'utf8'),
    registry: readFileSync('src/views/chat/component/index.ts', 'utf8'),
    chat: readFileSync('src/views/chat/chat-block/ChartBlock.vue', 'utf8'),
    dashboard: readFileSync('src/views/dashboard/components/sq-view/index.vue', 'utf8'),
    editor: readFileSync('src/views/dashboard/common/DashboardSqlEditor.vue', 'utf8'),
    assistant: readFileSync('src/views/analysis-assistant/AnalysisAssistantDock.vue', 'utf8'),
    insight: readFileSync('src/views/chat/component/ChartInsightHeader.vue', 'utf8'),
    fullscreen: readFileSync('src/views/dashboard/preview/ChartFullscreenDialog.vue', 'utf8'),
    sizing: readFileSync('src/views/dashboard/utils/chartSizing.ts', 'utf8'),
  }

  assert.match(files.types, /\| 'donut'/)
  assert.match(files.registry, /donut: Donut/)
  assert.match(files.chat, /pushChartType\('donut'/)
  assert.match(files.dashboard, /pushChartType\('donut'/)
  assert.match(files.editor, /label: 'donut', value: 'donut'/)
  assert.match(files.editor, /isRadialPartitionChartType/)
  assert.match(files.assistant, /donut: '环形图'/)
  assert.match(files.insight, /\['pie', 'donut'/)
  assert.match(files.fullscreen, /'donut'/)
  assert.match(files.sizing, /isRadialPartitionChartType/)
})

test('donut has labels in every supported locale', () => {
  const expected = {
    'zh-CN.json': '环形图',
    'zh-TW.json': '環形圖',
    'en.json': 'Donut',
    'ko-KR.json': '도넛 차트',
  }
  for (const [file, label] of Object.entries(expected)) {
    const locale = JSON.parse(readFileSync(`src/i18n/${file}`, 'utf8'))
    assert.equal(locale.chat.chart_type.donut, label)
  }
})
