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
assert.match(source, /图表配置/)
assert.match(source, /SQL 明细/)
assert.match(source, /:disabled="!canEdit/)
assert.match(panel, /<RoiSqlEditor/)
assert.match(panel, /@saved="handleChartSaved"/)
assert.doesNotMatch(panel, /DashboardSqlEditor\.vue|useDashboardStore|canvasData|canvasViewInfo/)

console.log('ROI SQL editor isolation tests passed')
