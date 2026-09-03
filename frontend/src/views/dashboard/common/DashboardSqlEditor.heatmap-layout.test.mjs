import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const editor = readFileSync(new URL('./DashboardSqlEditor.vue', import.meta.url), 'utf8')

test('热力事件筛选入口与事件下拉保持在同一行', () => {
  assert.match(
    editor,
    /<div class="heatmap-event-row">[\s\S]*?v-model="sqlBuilder\.heatmap\.event"[\s\S]*?<span>筛选条件<\/span>[\s\S]*?<\/div>/,
  )
})

test('热力事件筛选树紧跟事件行且位于计算配置之前', () => {
  assert.match(
    editor,
    /<div class="heatmap-event-config">[\s\S]*?<div class="heatmap-event-row">[\s\S]*?class="heatmap-event-filter-tree"[\s\S]*?<\/div>\s*<label class="builder-field-label">计算<\/label>/,
  )
})

test('热力事件下拉宽度为所在配置列的一半', () => {
  assert.match(
    editor,
    /\.heatmap-event-row :deep\(\.builder-field-picker-trigger\)\s*\{[\s\S]*?width:\s*50%;[\s\S]*?flex:\s*0 1 50%;/,
  )
})
