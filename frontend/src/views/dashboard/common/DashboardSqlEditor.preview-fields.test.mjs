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
const pivotGroupValueOptionsMatch = source.match(
  /const pivotGroupValueOptions = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)\r?\nconst previewDisplayData/
)
const chartPreviewSeriesFieldsMatch = source.match(
  /const chartPreviewSeriesFields = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)\r?\nconst showPivotGroupValueConfig/
)
const activePivotGroupValueFieldMatch = source.match(
  /const activePivotGroupValueField = computed\(\(\) =>([\s\S]*?)\r?\n\)\r?\nconst previewHasPivotGroupField/
)
const normalizePivotSelectionsMatch = source.match(
  /function normalizePivotSelections\(\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction initPivotConfig/
)
const sanitizePivotTimeFieldMatch = source.match(
  /function sanitizePivotTimeField\(\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction normalizePivotSelections/
)
const pivotTimeFieldOptionsMatch = source.match(
  /const pivotTimeFieldOptions = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)\r?\nconst pivotGroupFieldOptions/
)
const buildPivotConfigMatch = source.match(
  /function buildPivotConfig\([\s\S]*?\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction previewPivotPayload/
)
const initPivotConfigMatch = source.match(
  /function initPivotConfig\(pivot\?: any\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction buildPivotConfig/
)
const buildPivotGroupEnabledMatch = buildPivotConfigMatch?.[1].match(/group_enabled:\s*([^\r\n]+),/)
const pivotGroupFieldWatcherMatch = source.match(
  /watch\(\s*\(\) => activePivotGroupValueField\.value,([\s\S]*?)\r?\n\)\r?\n\r?\nwatch\(/
)
const pivotEnabledWatcherMatch = source.match(
  /watch\(\s*\(\) => form\.pivotEnabled,([\s\S]*?)\r?\n\)\r?\n\r?\nwatch\(/
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
  /previewDisplayData/,
  '图表预览 series 必须按当前预览有效数据清洗，允许透视结果缺少图例字段时回退源数据'
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
  '分组可见项必须跟随图表分类字段'
)
assert.doesNotMatch(
  activePivotGroupValueFieldMatch[1],
  /form\.pivotGroupField/,
  '分组可见项不能跟随透视分组字段，否则会和分类字段脱节'
)
assert.match(source, /t\('dashboard\.pivot_group_field'\)/, '透视配置区需要提供分组字段选择器')
assert.match(source, /v-model="form\.pivotGroupField"/, '分组字段选择器必须写入 form.pivotGroupField')
assert.ok(sanitizePivotTimeFieldMatch, '需要保留透视时间字段清理逻辑')
assert.match(
  sanitizePivotTimeFieldMatch[1],
  /return timeFields\.length > 0/,
  '清理透视时间字段时需要返回是否还有可选日期字段'
)
assert.ok(normalizePivotSelectionsMatch, '需要保留透视字段规范化逻辑')
assert.ok(pivotTimeFieldOptionsMatch, '需要保留透视时间字段选项')
assert.match(
  pivotTimeFieldOptionsMatch[1],
  /dateFields\.length \? dateFields : sourcePreview\.fields/,
  '无日期字段时透视时间字段应兜底为 SQL 结果字段，允许用户继续启用透视'
)
assert.doesNotMatch(
  source,
  /pivotToggleDisabled/,
  '交互透视开关不应因 SQL 结果缺少日期字段而禁用'
)
assert.doesNotMatch(
  normalizePivotSelectionsMatch[1],
  /form\.pivotTimeField = defaultPivotField\(form\.x/,
  '透视时间字段不能默认使用维度轴，否则排行图会把渠道当时间字段'
)
assert.doesNotMatch(
  normalizePivotSelectionsMatch[1],
  /pickAllowedField/,
  '透视时间字段不合法时不能自动兜底到其他日期字段，应清空并关闭透视'
)
assert.doesNotMatch(source, /function pickAllowedField/, '透视字段选择不应保留自动兜底字段工具')
assert.doesNotMatch(
  source,
  /form\.pivotTimeField\s*\|\|\s*form\.x/,
  '透视相关推断只能使用显式透视时间字段，不能回退到维度轴'
)
assert.match(
  normalizePivotSelectionsMatch[1],
  /const hasSelectableTimeField = sanitizePivotTimeField\(\)/,
  '透视规范化必须始终校验时间字段，不能只在 fields 有值时才清理旧值'
)
assert.match(
  normalizePivotSelectionsMatch[1],
  /if \(!hasSelectableTimeField\)/,
  '完全没有可选字段时才应关闭透视'
)
assert.doesNotMatch(
  normalizePivotSelectionsMatch[1],
  /!form\.pivotTimeField[\s\S]*form\.pivotEnabled = false/,
  '缺少真实日期字段或尚未选择时间字段时不应自动关闭透视'
)
assert.ok(pivotEnabledWatcherMatch, '需要监听启用透视动作，清理旧的非法透视字段')
assert.match(
  pivotEnabledWatcherMatch[1],
  /sanitizePivotTimeField\(\)/,
  '启用透视时必须清空非法时间字段，不能继续显示渠道等旧值'
)
assert.doesNotMatch(
  pivotEnabledWatcherMatch[1],
  /form\.pivotTimeField\s*=\s*pivotTimeFieldOptions\.value\[0\]/,
  '启用透视时不能自动选择第一个时间字段，必须由用户显式选择'
)
assert.doesNotMatch(
  pivotEnabledWatcherMatch[1],
  /form\.pivotEnabled = false/,
  '手动点击透视开关不应靠 watcher 自动回弹'
)
assert.doesNotMatch(source, /:disabled="pivotToggleDisabled"/, '透视开关不应绑定无日期字段禁用条件')
assert.doesNotMatch(source, /:title="pivotToggleDisabledReason"/, '透视开关不应显示无日期字段禁用原因')
assert.doesNotMatch(
  normalizePivotSelectionsMatch[1],
  /preferredPivotGroupField/,
  '透视分组字段不能自动猜测，应只使用用户显式选择或已保存的 group_field'
)
assert.doesNotMatch(source, /function preferredPivotGroupField/, '不应保留自动猜测透视分组字段的逻辑')
assert.match(
  source,
  /function alignSeriesAndPivotGroupFields/,
  'SQL 预览后需要用数据基数纠正分类字段和分组字段互换的旧状态'
)
assert.match(
  source,
  /if \(alignSeriesAndPivotGroupFields\(\)\) \{\r?\n\s*syncPivotGroupValues\(\{ forceAll: true \}\)/,
  '分类/分组字段自动纠正后必须立刻按新的分组字段重置可见项'
)
assert.ok(pivotGroupFieldWatcherMatch, '需要监听透视分组字段变化')
assert.match(
  pivotGroupFieldWatcherMatch[1],
  /syncPivotGroupValues\(\{ forceAll: true \}\)/,
  '透视分组字段变化时必须重置分组可见项，不能混入上一个字段的值'
)
assert.ok(buildPivotConfigMatch, '需要保留透视配置构建逻辑')
assert.ok(initPivotConfigMatch, '需要保留透视配置初始化逻辑')
assert.match(
  initPivotConfigMatch[1],
  /normalizePivotSelections\(\)[\s\S]*if \(!form\.pivotEnabled\) \{[\s\S]*form\.pivotGroupValues = \[\][\s\S]*return[\s\S]*\}/,
  '旧配置中的时间字段不合法时，初始化应关闭透视并停止恢复旧分组值'
)
assert.match(
  buildPivotConfigMatch[1],
  /const groupField = activePivotGroupValueField\.value/,
  '保存和运行预览的透视分组字段必须来自分类字段对应的分组可见项字段'
)
assert.doesNotMatch(
  buildPivotConfigMatch[1],
  /const groupField = effectiveSeriesField/,
  '保存时不能用图表分类字段覆盖透视分组字段'
)
assert.ok(buildPivotGroupEnabledMatch, '需要显式保存透视分组启用状态')
assert.match(
  buildPivotGroupEnabledMatch?.[1] || '',
  /pivotGroupValues/,
  '保存分组可见项时必须同步启用分组，否则仪表盘会继续显示不分组'
)
assert.match(
  showPivotGroupValueConfigMatch[1],
  /sourceHasPivotGroupValues/,
  '分组可见项显示应基于源数据分组值，不能因为透视后的预览结果缺少分组字段而隐藏'
)
assert.match(
  showPivotGroupValueConfigMatch[1],
  /form\.pivotGroupValues\.length/,
  '已有分组可见项配置时，即使当前源预览暂时缺少分组字段也应保留配置入口'
)
assert.ok(pivotGroupValueOptionsMatch, '需要保留分组可见项选项计算逻辑')
assert.doesNotMatch(
  pivotGroupValueOptionsMatch[1],
  /form\.pivotGroupValues/,
  '分组可见项下拉只能展示当前分组字段的实际值，不能混入上一个字段的已选值'
)
assert.doesNotMatch(
  showPivotGroupValueConfigMatch[1],
  /form\.pivotGroupEnabled/,
  '分组可见项应跟随分类字段显示，不能因为默认不分组而隐藏'
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
