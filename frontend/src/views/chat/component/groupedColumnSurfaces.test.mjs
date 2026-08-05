import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const read = (path) => readFileSync(path, 'utf8')

for (const path of [
  'src/views/chat/chat-block/ChartBlock.vue',
  'src/views/dashboard/components/sq-view/index.vue',
  'src/views/dashboard/common/DashboardSqlEditor.vue',
]) {
  assert.match(read(path), /grouped_column/, `${path} 必须提供分组柱状图入口`)
}

assert.match(read('src/views/analysis-assistant/AnalysisAssistantDock.vue'), /grouped_column:\s*'分组柱状图'/)
assert.match(read('src/views/chat/component/chartInsight.ts'), /grouped_column/)
assert.match(read('src/views/chat/component/ChartInsightHeader.vue'), /grouped_column/)

const labels = {
  'src/i18n/zh-CN.json': '分组柱状图',
  'src/i18n/zh-TW.json': '分組柱狀圖',
  'src/i18n/en.json': 'Grouped Column',
  'src/i18n/ko-KR.json': '그룹 세로 막대 차트',
}
for (const [path, expected] of Object.entries(labels)) {
  const messages = JSON.parse(read(path))
  assert.equal(messages.chat.chart_type.grouped_column, expected)
}

const compileModuleUrl = (source) => {
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText
  return `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
}

const chartTypesModuleUrl = compileModuleUrl(read('src/views/chat/component/chartTypes.ts'))
const sizingSource = read('src/views/dashboard/utils/chartSizing.ts').replace(
  '@/views/chat/component/chartTypes.ts',
  chartTypesModuleUrl
)
const moduleUrl = compileModuleUrl(sizingSource)
const { getRecommendedDashboardChartFrame } = await import(moduleUrl)
assert.deepEqual(
  getRecommendedDashboardChartFrame({ chart: { type: 'grouped_column' } }, 3),
  getRecommendedDashboardChartFrame({ chart: { type: 'column' } }, 3)
)
