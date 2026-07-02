import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'DashboardSqlEditor.vue')
const source = readFileSync(componentPath, 'utf8')

const chartPreviewMatch = source.match(/<ChartComponent[\s\S]*?:columns="([^"]+)"/)
const previewTableFieldsMatch = source.match(
  /const previewTableFields = computed\(\(\) => ([^\r\n]+)\)/
)
const showPivotGroupValueConfigMatch = source.match(
  /const showPivotGroupValueConfig = ([\s\S]*?)const pivotGroupValueOptions/
)
const previewDisplayDataMatch = source.match(
  /const previewDisplayData = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)\r?\nconst hasPreviewData/
)
const chartPreviewSeriesFieldsMatch = source.match(
  /const chartPreviewSeriesFields = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)\r?\nconst showPivotGroupValueConfig/
)
const activePivotGroupValueFieldMatch = source.match(
  /const activePivotGroupValueField = computed\(\(\) => ([^\r\n]+)\)/
)
const buildPivotConfigMatch = source.match(
  /function buildPivotConfig\([\s\S]*?\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction previewPivotPayload/
)

assert.ok(chartPreviewMatch, '图表预览组件需要声明 columns 绑定')
assert.match(
  chartPreviewMatch[1],
  /previewTableFields/,
  '表格图表预览列必须使用 previewTableFields，避免用 sourcePreview.fields 渲染不存在的字段'
)

assert.ok(previewTableFieldsMatch, '需要保留数据预览字段计算逻辑')
assert.doesNotMatch(
  previewTableFieldsMatch[1],
  /form\.columns/,
  '数据预览字段必须来自实际 preview 结果，不能优先使用表单列配置'
)
assert.match(
  previewTableFieldsMatch[1],
  /previewDisplayFields/,
  '数据预览字段必须来自清洗后的有效字段，避免运行预览后空值字段重新出现'
)
assert.match(source, /function isMeaningfulPreviewValue/, '需要显式识别预览行中的有效值')
assert.match(source, /function visiblePreviewFields/, '需要复用同一套有效字段清洗逻辑')

assert.ok(chartPreviewSeriesFieldsMatch, '需要保留图表预览分类字段清洗逻辑')
assert.match(
  chartPreviewSeriesFieldsMatch[1],
  /previewDisplayFields/,
  '图表预览 series 必须按当前预览有效字段清洗，避免空分类字段导致暂无预览数据'
)
assert.match(
  source,
  /:series="toAxes\(chartPreviewSeriesFields\)"/,
  'ChartComponent 必须使用清洗后的 chartPreviewSeriesFields'
)

assert.ok(showPivotGroupValueConfigMatch, '需要保留透视分组值显示条件')
assert.ok(activePivotGroupValueFieldMatch, '需要保留透视分组选项字段计算逻辑')
assert.match(
  activePivotGroupValueFieldMatch[1],
  /effectiveSeriesField\.value/,
  '分组可见项必须跟随用户显式选择的分类字段'
)
assert.doesNotMatch(
  activePivotGroupValueFieldMatch[1],
  /form\.pivotGroupField\s*\|\|/,
  '分类清空时不能用内部 pivotGroupField 兜底显示分组可见项'
)
assert.ok(buildPivotConfigMatch, '需要保留透视配置构建逻辑')
assert.match(
  buildPivotConfigMatch[1],
  /const groupField = activePivotGroupValueField\.value/,
  '保存和运行预览的透视分组字段必须跟随显式分类字段'
)
assert.doesNotMatch(
  buildPivotConfigMatch[1],
  /const groupField = form\.pivotGroupField\s*\|\|/,
  '分类清空时不能继续把内部 pivotGroupField 写入透视配置'
)
assert.match(
  showPivotGroupValueConfigMatch[1],
  /sourceHasPivotGroupValues/,
  '分组可见项显示应基于源数据分组值，不能因为透视后的预览结果缺少分组字段而隐藏'
)
assert.doesNotMatch(
  showPivotGroupValueConfigMatch[1],
  /previewHasPivotGroupField/,
  '预览结果是否包含分组字段只能决定是否过滤预览数据，不能决定是否显示分组可见项'
)

assert.ok(previewDisplayDataMatch, '需要保留图表预览数据计算逻辑')
assert.match(
  previewDisplayDataMatch[1],
  /previewHasPivotGroupField/,
  '只有当前预览数据真实包含分组字段时，才允许按分组可见项过滤预览数据'
)
assert.doesNotMatch(
  source.match(/const previewHasPivotGroupField = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)/)?.[1] || '',
  /hasOwnProperty/,
  '分组字段不能只按 key 存在判断，空字符串/空值字段不能触发分组过滤'
)
