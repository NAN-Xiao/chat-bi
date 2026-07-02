import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'index.vue')
const source = readFileSync(componentPath, 'utf8')

const syncPivotStateMatch = source.match(
  /function syncPivotStateFromView\([\s\S]*?\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction schedulePivotRefresh/
)
const renderableChartDataMatch = source.match(
  /const renderableChartData = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)/
)
const renderSeriesMatch = source.match(
  /const renderSeries = computed<ChartAxis\[\]>\(\(\) => \{([\s\S]*?)\r?\n\}\)\r?\nconst pivotGroupValueFilterEnabled/
)
const pivotTimeFieldMatch = source.match(
  /const pivotTimeField = computed\(\(\) => ([^\r\n]+)\)/
)
const pivotGroupFieldMatch = source.match(
  /const pivotGroupField = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)\r?\nconst pivotDimensions/
)
const pivotGroupPopoverMatch = source.match(
  /<el-popover\s+v-if="pivotHasGroup"([\s\S]*?)>\s*<template #reference>/
)

assert.ok(syncPivotStateMatch, '需要保留仪表盘透视状态初始化逻辑')
assert.ok(pivotTimeFieldMatch, '需要保留仪表盘透视时间字段计算逻辑')
assert.doesNotMatch(
  pivotTimeFieldMatch[1],
  /firstAxisValue\(props\.viewInfo\?\.chart\?\.xAxis\)/,
  '仪表盘透视时间字段必须取 pivot.time_field，不能兜底到图表维度轴'
)
assert.ok(pivotGroupFieldMatch, '需要保留仪表盘透视分组字段计算逻辑')
assert.doesNotMatch(
  pivotGroupFieldMatch[1],
  /firstAxisValue\(props\.viewInfo\?\.chart\?\.series\)/,
  '仪表盘透视分组字段必须取 pivot.group_field，不能兜底到图表分类字段'
)
assert.doesNotMatch(
  syncPivotStateMatch[1],
  /pivotDimensions\.value\[0\]/,
  '仪表盘分组字段必须取保存的 group_field，不能自动猜第一个维度'
)
assert.match(
  syncPivotStateMatch[1],
  /configuredPivotGroupValues/,
  '已保存分组可见项时，即使旧配置 group_enabled=false，仪表盘也应按分组初始化'
)
assert.match(
  syncPivotStateMatch[1],
  /pivotState\.groupField = pivotGroupField\.value \|\| ''/,
  '仪表盘分组字段应严格同步保存的 group_field，缺失时置空'
)
assert.ok(renderableChartDataMatch, '需要保留仪表盘图表数据源计算逻辑')
assert.match(
  renderableChartDataMatch[1],
  /source_data/,
  '旧物化结果缺少分组字段时，应使用保存的 source_data 兜底渲染分组视图'
)
assert.ok(renderSeriesMatch, '需要保留仪表盘图表 series 计算逻辑')
assert.match(
  renderSeriesMatch[1],
  /const chartSeries = normalizeAxisList\(props\.viewInfo\?\.chart\?\.series\)/,
  '启用国家分组筛选时，图表图例仍应优先使用原始 chart.series，例如渠道'
)
assert.ok(pivotGroupPopoverMatch, '需要保留分组可见项弹层')
assert.match(
  pivotGroupPopoverMatch[1],
  /v-model:visible="pivotGroupPopoverVisible"/,
  '分组可见项弹层需要受控 visible，便于外部点击兜底关闭'
)
assert.match(
  source,
  /document\.addEventListener\('pointerdown', handlePivotGroupOutsidePointerDown, true\)/,
  '分组可见项弹层应在捕获阶段监听外部点击，避免图表层阻止冒泡导致无法关闭'
)
assert.match(
  source,
  /document\.removeEventListener\('pointerdown', handlePivotGroupOutsidePointerDown, true\)/,
  '分组可见项弹层隐藏或组件卸载时必须移除外部点击监听'
)
