import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'DashboardSqlEditor.vue')
const source = readFileSync(componentPath, 'utf8')
const filterTreePath = join(currentDir, 'BuilderFilterTree.vue')
const filterTreeSource = readFileSync(filterTreePath, 'utf8')

const chartPreviewMatch = source.match(/<ChartComponent[\s\S]*?:columns="([^"]+)"/)
const previewTableFieldsMatch = source.match(
  /const previewTableFields = computed\(\(\) => ([^\r\n]+)\)/
)
const showPivotGroupValueConfigMatch = source.match(
  /const showPivotGroupValueConfig = ([\s\S]*?)const pivotGroupValueOptions/
)
const previewDisplayDataMatch = source.match(
  /const previewDisplayData = ([\s\S]*?)const hasPreviewData/
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
assert.match(source, /const SQL_EDITOR_TIME_FIELD = 'dt'/, 'SQL 编辑器时间字段必须固定为 dt')
assert.match(source, /function fixedSqlEditorTimeFieldIssue\(\)/, '固定时间字段缺失时必须显式校验')
assert.doesNotMatch(
  source,
  /preferredBuilderTimeField\(builderTimeFieldOptions\.value\)/,
  '固定时间字段缺失时不得自动回退到其他时间字段'
)

assert.match(
  source,
  /formulaTokensToText/,
  '计算指标应使用公式 token 展示文本，而不是固定左右指标选择器'
)
assert.match(
  source,
  /<BuilderFieldPicker\s+v-model="item\.field"[\s\S]*?:options="analysisFieldOptions"[\s\S]*?:mode="analysisFieldPickerMode"/,
  '普通分析指标字段应使用 BuilderFieldPicker，并在事件数据源下进入事件选择面板'
)
assert.match(
  source,
  /const hasTrackingEventCatalog = computed\(\(\) =>[\s\S]*trackingEventCatalog\.value[\s\S]*Array\.isArray\(trackingEventCatalog\.value\?\.groups\)/,
  '应按事件目录是否存在识别事件上下文，不能只按事件数量判断'
)
assert.match(
  source,
  /const usesTrackingEventPicker = computed\(\(\) =>[\s\S]*hasTrackingEventCatalog\.value[\s\S]*hasTrackingEventOptions\.value/,
  '事件目录为空时仍应保持事件选择器，避免静默回退到普通字段'
)
assert.match(
  source,
  /tableRole\?: string[\s\S]*const schemaFieldOptions/,
  '字段选择器需要拿到 tracking 表角色，用于过滤对象组类型表'
)
assert.match(
  source,
  /trackingConfigApi\.get\(\)[\s\S]*trackingTableRoleByName[\s\S]*tableRole/,
  '加载字段时应把 tracking 表角色补到字段 option'
)
assert.match(
  source,
  /tableReferenceLabel\?: string[\s\S]*const schemaFieldOptions/,
  '事件参数字段需要保留事件明细表 label 引用，用于字段选择器展示来源'
)
assert.match(
  source,
  /function eventDetailTableLabel\(eventTable: string\)/,
  '事件参数字段需要通过事件明细表名解析真实表 label，不能只显示事件参数对照'
)
assert.match(
  source.match(/const trackingEventPropertyOptions = computed[\s\S]*?\n\}\)/)?.[0] || '',
  /const tableReferenceLabel = eventDetailTableLabel\(eventTable\)[\s\S]*tableReferenceLabel,/,
  '事件参数 option 应携带所属事件明细表 label 引用'
)
const metricMeasureFieldOptionsMatch = source.match(/function metricMeasureFieldOptions[\s\S]*?\n\}/)
assert.ok(metricMeasureFieldOptionsMatch, '需要保留事件计算字段候选函数')
assert.match(
  source,
  /function eventDetailFieldOptions\(eventTable: string\)/,
  '事件计算字段候选需要包含事件明细表普通字段'
)
assert.match(
  metricMeasureFieldOptionsMatch[0],
  /\.\.\.eventProperties[\s\S]*\.\.\.eventDetailFieldOptions\(eventOption\.eventTable \|\| eventOption\.table\)/,
  '事件计算字段候选应同时包含事件参数和事件明细字段'
)
assert.match(
  metricMeasureFieldOptionsMatch[0],
  /\['sum', 'avg'\]\.includes\(item\.aggregation \|\| ''\)[\s\S]*options\.filter\(isNumericFieldOption\)/,
  '求和和平均值应继续只展示数值字段'
)
assert.match(
  source,
  /const builderFieldOptions = computed\(\(\) => eventScopedSchemaFieldOptions\.value\.filter\(isSelectableFieldOption\)/,
  '分组项、全局筛选等候选应先限定事件表，再统一过滤对象组类型字段'
)
assert.match(
  source,
  /<div v-if="sqlBuilder\.activeTab === 'builder'" class="sql-builder-builder-pane">/,
  '图表配置 tab 应使用 v-if 懒挂载，避免打开 SQL 明细时提前渲染大量字段选择器'
)
assert.match(
  source,
  /<div v-if="sqlBuilder\.activeTab === 'sql'" class="sql-detail-pane">/,
  'SQL 明细 tab 应独立挂载，避免和图表配置面板同时参与首屏渲染'
)
assert.doesNotMatch(
  source.match(/class="metric-chip-row"[\s\S]*?<span class="metric-of">/)?.[0] || '',
  /<el-select\s+v-model="item\.field"/,
  '普通分析指标字段不应继续使用扁平字段下拉，否则事件会退化成普通字段列表'
)
assert.match(
  source.match(/class="metric-body"[\s\S]*?class="metric-chip-row"/)?.[0] || '',
  /<el-input[\s\S]*v-model="item\.alias"[\s\S]*class="metric-title-input"/,
  '普通分析指标标题应展示可编辑别名输入框，让用户能直接修改指标输出名称'
)
assert.match(
  source.match(/class="formula-metric-title-wrap"[\s\S]*?class="formula-decimal-pill"/)?.[0] || '',
  /<el-input[\s\S]*v-model="item\.alias"[\s\S]*class="formula-metric-title-input"/,
  '公式指标标题应展示可编辑别名输入框，让用户能直接修改自定义指标名称'
)
assert.match(
  source,
  /\.metric-chip-row \{[\s\S]*grid-template-columns:\s*minmax\(220px,\s*320px\) 18px 104px 24px;/,
  '普通分析指标事件选择框不应随整行拉满，需要限制最大宽度'
)
assert.doesNotMatch(
  source,
  /title="添加条件组"|<span>条件组<\/span>|<el-icon><FolderAdd \/><\/el-icon>/,
  '页面编辑器筛选区域应屏蔽条件组新增入口'
)
assert.doesNotMatch(
  filterTreeSource.match(/<div v-if="showToolbar" class="builder-filter-toolbar">[\s\S]*?<\/div>/)?.[0] || '',
  /addGroup|FolderAdd|条件组/,
  '通用筛选树工具栏应只保留筛选条件入口，不再提供条件组入口'
)
assert.doesNotMatch(
  `${source}\n${filterTreeSource}`,
  />\s*条件组\s*</,
  '筛选 UI 中不应继续展示条件组文案'
)
assert.match(
  filterTreeSource,
  /class="builder-filter-node-list"[\s\S]*<div v-else class="builder-empty-row"[\s\S]*<div v-if="showToolbar" class="builder-filter-toolbar"/,
  '筛选条件新增按钮应渲染在筛选输入行下面'
)
assert.match(
  source,
  /serializeFormulaTokensForContext/,
  'AI SQL 上下文必须序列化公式 token，并把 metricId 转成指标别名'
)
assert.match(
  source,
  /serializeFormulaTokensForContext\(item\.tokens, metricAliasById, fieldOptionPayload\)/,
  '公式 token 上下文必须经 fieldOptionPayload 保留 JSON sourceField/jsonPath'
)
assert.match(
  source,
  /formulaMetrics:/,
  '手动图表配置上下文必须向后端提供 formulaMetrics'
)
assert.doesNotMatch(
  source,
  /availableJsonFields:/,
  '手动图表 AI SQL 上下文不应携带 availableJsonFields 全量 JSON 子字段，避免 prompt 过大导致生成变慢'
)
assert.match(
  source,
  /appendFormulaToken/,
  '页面需要提供公式 token 插入入口'
)
assert.match(
  source,
  /contenteditable="true"/,
  '公式编辑区应是可聚焦的 contenteditable token editor'
)
assert.match(
  source,
  /formulaCursorIndex/,
  '公式键盘插入应依赖当前光标位置'
)
assert.match(
  source,
  /appendFormulaAtomicMetric/,
  '公式内部应支持直接插入事件指标'
)
assert.match(
  source,
  /插入事件/,
  '公式按钮文案应为插入事件，贴近事件分析操作逻辑'
)
assert.match(
  source,
  /title="添加公式指标"[\s\S]*?>\s*Σ\s*<\/button>/,
  '公式指标应通过分析指标标题区的 Σ 入口添加，贴近 ThinkingData 操作逻辑'
)
assert.match(
  source,
  /title="添加公式指标"[\s\S]*@click\.stop="addCalculatedMetricItem"/,
  '添加公式指标入口必须阻止冒泡，避免被外层点击收起逻辑立刻关闭键盘'
)
assert.doesNotMatch(
  source.match(/function addCalculatedMetricItem\(\) \{[\s\S]*?\n\}/)?.[0] || '',
  /addMetricItem\(\)/,
  '新增公式指标时不应自动补普通分析指标，避免公式指标场景出现无关的默认指标'
)
assert.match(
  source,
  /if \(!sqlBuilder\.metricItems\.length && !sqlBuilder\.calculatedMetrics\.length\) \{\r?\n\s*addMetricItem\(\)/,
  '加载字段后只有普通指标和公式指标都为空时才应自动补默认普通指标'
)
assert.match(
  source,
  /pruneAutoSeededMetricItemsForFormulaOnlyBuilder\(\)/,
  '恢复已有配置时应清理公式指标场景下历史自动补出的默认普通指标'
)
assert.doesNotMatch(
  source,
  /添加计算指标|暂无计算指标|<span>计算指标<\/span>/,
  '本地旧的计算指标独立操作流程应暂时屏蔽'
)
assert.doesNotMatch(
  source,
  /`计算指标\$\{/,
  '新增公式指标默认名称不应继续使用计算指标文案'
)
assert.match(
  source,
  /class="formula-metric-head"/,
  '公式指标应使用紧凑头部展示名称、精度和操作入口'
)
assert.match(
  source.match(/class="metric-item formula-metric-item"[\s\S]*?<div class="metric-body">/)?.[0] || '',
  /class="metric-index formula-metric-index"[\s\S]*sqlBuilder\.metricItems\.length \+ index \+ 1/,
  '公式指标左侧应延续普通分析指标序号，形成 1、2、3 的连续排列'
)
assert.match(
  source,
  /class="formula-decimal-pill"/,
  '公式指标小数位应像 ThinkingData 一样显示为头部 pill'
)
assert.match(
  source,
  /class="formula-token-filter"/,
  '公式内事件指标应保留筛选入口视觉位置'
)
assert.match(
  source,
  /formulaAtomicMetricLabel/,
  '公式内事件指标 token 编辑后应刷新聚合展示标签'
)
assert.match(
  source,
  /activeFormulaAtomicMetricKey/,
  '公式内已插入事件指标应记录当前编辑 token，支持原位编辑'
)
assert.match(
  source,
  /function startEditFormulaAtomicMetric/,
  '点击已插入事件指标时应进入原位编辑态'
)
assert.match(
  source,
  /function syncFormulaAtomicMetric/,
  '原位编辑事件、聚合方式或计算字段后应同步刷新 token 展示配置'
)
assert.match(
  source,
  /<template v-if="token\.type === 'atomicMetric'">[\s\S]*class="formula-token-editor-row"/,
  '已插入事件指标应默认在原位置展示可编辑行'
)
assert.match(
  source,
  /class="formula-token-editor-row"[\s\S]*class="formula-insert-target"[\s\S]*@click\.stop="setFormulaCursor\(item, tokenIndex \+ 1\)"/,
  '已插入事件指标的可编辑行后面必须保留独立插入点，允许在两个事件之间继续插入运算符'
)
assert.match(
  source,
  /@click="handleFormulaDisplayClick\(\$event, item\)"/,
  '公式编辑框空白区域点击应按点击所在行定位光标，不能总是跳到公式末尾'
)
assert.match(
  source,
  /function handleFormulaDisplayClick\(event: MouseEvent, item: SqlBuilderCalculatedMetricItem\) \{[\s\S]*formula-token[\s\S]*getBoundingClientRect\(\)[\s\S]*setFormulaCursor\(item, tokenIndex \+ 1\)/,
  '公式编辑框空白点击应根据同行 token 计算插入位置，点第一行右侧应插到第一行后'
)
assert.match(
  source,
  /\.formula-display \{[\s\S]*width:\s*100%;[\s\S]*box-sizing:\s*border-box;/,
  '公式编辑框应撑满父容器，确保右侧空白区域也属于可点击输入范围'
)
assert.doesNotMatch(
  source.match(/\.formula-display \{[\s\S]*?\n\}/)?.[0] || '',
  /border:\s*1px\s+solid/,
  '公式编辑框不应显示外层边框'
)
assert.doesNotMatch(
  source.match(/\.formula-display\.is-invalid \{[\s\S]*?\n\}/)?.[0] || '',
  /border-color/,
  '公式编辑框校验错误时也不应重新显示外层边框'
)
assert.doesNotMatch(
  source.match(/<template v-if="token\.type === 'atomicMetric'">[\s\S]*<template v-else>/)?.[0] || '',
  /isEditingFormulaAtomicMetric/,
  '已插入事件指标不应只有进入编辑态后才显示可编辑行'
)
assert.match(
  source,
  /v-model="token\.metric\.field"[\s\S]*:options="analysisFieldOptions"[\s\S]*:mode="analysisFieldPickerMode"/,
  '原位编辑态的事件应复用上方同一套事件选择器'
)
assert.match(
  source,
  /v-model="token\.metric\.aggregation"[\s\S]*builderAggregationOptions/,
  '原位编辑态应允许直接修改事件指标聚合方式'
)
assert.match(
  source,
  /v-if="token\.metric\.aggregation !== 'count'"[\s\S]*v-model="token\.metric\.metric"/,
  '非总次数聚合时原位编辑态应允许修改计算字段'
)
assert.match(
  source,
  /class="formula-token-filter"[\s\S]*@click\.stop="toggleFormulaAtomicMetricFilter\(item, tokenIndex, token\.metric\)"/,
  '公式内事件指标筛选图标必须切换该事件自己的筛选条件'
)
assert.match(
  source,
  /<BuilderFilterTree\s+v-if="token\.metric\.filters\.length"[\s\S]*:nodes="token\.metric\.filters"[\s\S]*:logic="token\.metric\.filterLogic"[\s\S]*@update:logic="token\.metric\.filterLogic = \$event"/,
  '公式内事件指标筛选条件应在当前 token 下方展开并绑定 token.metric.filters'
)
assert.match(
  source,
  /class="formula-token-stack"[\s\S]*<BuilderFilterTree\s+v-if="token\.metric\.filters\.length"/,
  '公式内事件指标筛选条件应归属到当前事件 token 容器里，点击哪个事件就显示在哪个事件下面'
)
assert.match(
  source,
  /class="formula-token-flow"[\s\S]*class="formula-token-editor-row"[\s\S]*class="formula-insert-target"[\s\S]*<BuilderFilterTree\s+v-if="token\.metric\.filters\.length"/,
  '事件后面的输入插入点应保持在筛选树上方的公式输入流里，筛选条件只能显示在事件行下面'
)
assert.doesNotMatch(
  source,
  /class="formula-token-filter-panel"/,
  '公式筛选条件不应再按公式整体统一渲染到下方'
)
assert.match(
  source,
  /function toggleFormulaAtomicMetricFilter\(item: SqlBuilderCalculatedMetricItem, tokenIndex: number, metric: FormulaAtomicMetric\)/,
  '公式内事件指标需要专门的筛选展开函数，避免筛选按钮只是空图标'
)
assert.match(
  source,
  /\.formula-token-stack \{[\s\S]*display:\s*inline-flex;[\s\S]*flex-direction:\s*column;/,
  '公式内事件指标筛选树应另起一整行显示，避免挤在公式 token 中间'
)
assert.match(
  source,
  /activeFormulaMetricId === item\.id/,
  '公式键盘工具区应仅在当前公式激活时展开，避免常驻占位'
)
assert.match(
  source,
  /class="formula-toolbar-panel"/,
  '公式键盘应使用贴近 ThinkingData 的浮层面板布局'
)
assert.doesNotMatch(
  source.match(/class="formula-toolbar-panel"[\s\S]*?class="formula-keyboard-layout"/)?.[0] || '',
  /formula-picker-row|v-model="item\.pendingEventField"|v-model="item\.pendingAggregation"/,
  '公式键盘面板顶部不应再展示事件选择器，事件应插入后在公式行内原位编辑'
)
assert.match(
  source,
  /class="formula-number-pad"/,
  '公式键盘数字区应独立成 3 列小键盘'
)
assert.match(
  source,
  /class="formula-operator-pad"/,
  '公式键盘运算符区应独立成 2 列操作键盘'
)
assert.match(
  source,
  /class="formula-command-panel"/,
  '公式键盘右侧应独立展示插入和清空操作'
)
assert.match(
  source,
  /Ctrl\+E/,
  '插入事件按钮下方应展示 Ctrl+E 快捷键提示'
)
assert.match(
  source,
  /Ctrl\+D/,
  '清空按钮下方应展示 Ctrl+D 快捷键提示'
)
assert.doesNotMatch(
  source,
  /插入指标/,
  '公式编辑器不应继续暴露“插入指标”作为主入口'
)
assert.doesNotMatch(
  source,
  /leftMetricId: item\.leftMetricId/,
  '新版计算指标保存不应继续依赖固定左指标字段'
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

assert.match(
  source,
  /isNumericFieldOption/,
  '图表配置器需要复用统一的数值字段判断'
)
assert.match(
  source,
  /eventScopedSchemaFieldOptions\.value\.find\(isNumericFieldOption\)/,
  '新增指标时需要从事件范围内优先选择统一判断后的数值字段'
)
assert.match(
  source,
  /\['sum', 'avg'\]\.includes\(item\.aggregation\)[\s\S]*?!isNumericFieldOption\(metricField\)/,
  '求和和平均值校验都需要使用统一数值判断，文本字段仍然会被拦截'
)
assert.match(
  source,
  /option\.field === SQL_EDITOR_TIME_FIELD \|\| option\.value === SQL_EDITOR_TIME_FIELD/,
  '固定 dt 字段必须在当前 Schema 中精确匹配'
)
