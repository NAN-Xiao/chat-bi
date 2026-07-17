import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const editorPath = join(currentDir, 'RoiSqlEditor.vue')
const panelPath = join(currentDir, 'RoiDashboardPanel.vue')

assert.equal(existsSync(editorPath), true, '必须提供完全隔离的 ROI SQL 编辑器')

const source = readFileSync(editorPath, 'utf8')
const panel = readFileSync(panelPath, 'utf8')

assert.doesNotMatch(source, /DashboardSqlEditor\.vue/)
assert.doesNotMatch(source, /useDashboardStore|canvasData|canvasViewInfo/)
assert.doesNotMatch(source, /external_mcp|mcpServerId|mcpTool/)
assert.match(source, /roiDashboardApi\.previewChart/)
assert.match(source, /roiDashboardApi\.createChart/)
assert.match(source, /roiDashboardApi\.updateChart/)
assert.match(source, /reactive<RoiChartForm>/)
assert.match(source, /pivotEnabled/)
assert.match(source, /insightEnabled/)
assert.match(source, /layoutSpan/)
assert.match(source, /form\.pivot\.metric_fields/)
assert.match(source, /form\.pivot\.group_enabled/)
assert.match(source, /图表配置/)
assert.match(source, /SQL 明细/)
assert.match(source, /:disabled="!canEdit/)
const runPreview = source.match(/async function runPreview\(\) \{([\s\S]*?)\n\}/)
assert.ok(runPreview, '必须提供预览入口')
assert.doesNotMatch(
  runPreview[1],
  /if\s*\(\s*!props\.canEdit\s*\|\|\s*previewing\.value/,
  '新预览必须能够替代仍在途的旧预览'
)
assert.match(source, /createRoiChartPreviewRunner/)
assert.doesNotMatch(source, /:loading="previewing"/, '预览中按钮仍必须允许发起最新 B 请求')
assert.match(source, /canCancelRoiEditor\(saving\.value\)/, '保存中关闭必须经过生产守卫')
assert.match(source, /<el-button\s+:disabled="saving"\s+@click="requestClose\(\)"/)
assert.match(source, /:close-on-press-escape="!saving"/)
assert.match(source, /:show-close="!saving"/)
assert.match(panel, /<RoiSqlEditor/)
assert.match(panel, /@saved="handleChartSaved"/)
assert.doesNotMatch(panel, /DashboardSqlEditor\.vue|useDashboardStore|canvasData|canvasViewInfo/)

console.log('ROI SQL editor isolation tests passed')
