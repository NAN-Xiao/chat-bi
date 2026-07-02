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
  '数据预览字段必须来自清洗后的有效字段，避免空值字段被 Object.keys 误判为存在'
)
assert.match(source, /function isMeaningfulPreviewValue/, '需要显式识别预览行中的有效值')
assert.match(source, /function visiblePreviewFields/, '需要复用同一套有效字段清洗逻辑')

assert.ok(showPivotGroupValueConfigMatch, '需要保留透视分组值显示条件')
assert.match(
  showPivotGroupValueConfigMatch[1],
  /form\.pivotGroupEnabled/,
  '只有启用透视分组时才显示分组可见项'
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

const previewDisplayDataMatch = source.match(
  /const previewDisplayData = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)\r?\nconst hasPreviewData/
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
  '分组字段不能只按 key 存在判断，空字符串/空值字段不能触发分组可见项'
)
