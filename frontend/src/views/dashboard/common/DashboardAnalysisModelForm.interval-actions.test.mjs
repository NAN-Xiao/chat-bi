import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const formSource = readFileSync(new URL('./DashboardAnalysisModelForm.vue', import.meta.url), 'utf8')
const editorSource = readFileSync(new URL('./DashboardSqlEditor.vue', import.meta.url), 'utf8')

test('间隔分析事件操作仅在悬浮或激活时显示，并保持在事件行右侧', () => {
  assert.match(formSource, /aria-label="重命名起点事件"/)
  assert.match(formSource, /aria-label="筛选起点事件"/)
  assert.match(formSource, /aria-label="重命名终点事件"/)
  assert.match(formSource, /aria-label="筛选终点事件"/)
  assert.match(formSource, /class="interval-event-editor" :class="\{ 'is-active': intervalFilterExpanded\.start \|\| intervalAliasEditing\.start \}"/)
  assert.match(formSource, /class="interval-event-editor" :class="\{ 'is-active': intervalFilterExpanded\.end \|\| intervalAliasEditing\.end \}"/)
  assert.match(formSource, /\.interval-event-editor:hover \.retention-event-actions[\s\S]*?opacity:\s*1/)
  assert.match(formSource, /\.interval-event-row \{[\s\S]*?grid-template-columns:\s*minmax\(190px, 360px\) auto;/)
})

test('间隔分析事件改名状态随配置保存和恢复', () => {
  assert.match(editorSource, /startEventAlias: sqlBuilder\.interval\.startEventAlias\.trim\(\)/)
  assert.match(editorSource, /endEventAlias: sqlBuilder\.interval\.endEventAlias\.trim\(\)/)
  assert.match(editorSource, /sqlBuilder\.interval\.startEventAlias = typeof interval\.startEventAlias === 'string'/)
  assert.match(editorSource, /sqlBuilder\.interval\.endEventAlias = typeof interval\.endEventAlias === 'string'/)
  assert.match(editorSource, /function beginIntervalEventRename\(target: IntervalEventTarget\)/)
  assert.match(editorSource, /function finishIntervalEventRename\(target: IntervalEventTarget\)/)
  assert.match(editorSource, /function cancelIntervalEventRename\(target: IntervalEventTarget\)/)
})
