import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('./DashboardDateExpressionPicker.vue', import.meta.url)),
  'utf8'
)

assert.match(source, /defineModel<DashboardDateExpression \| null>/)
assert.match(source, /variant\?:\s*'default'\s*\|\s*'roi'/)
assert.match(source, /variant:\s*'default'/)
assert.match(source, /date-expression-picker--\$\{variant\}/)
assert.match(source, /cloneDashboardDateExpression/)
assert.match(source, /defaultDashboardDateExpression/)
assert.doesNotMatch(source, /preset:\s*['"]past_30_days['"]/, '日期选择器不得维护过去 30 天默认值')
assert.match(source, /function openPicker/)
assert.match(source, /function closeWithoutApply/)
assert.match(source, /function applyDraft/)
assert.match(source, /emit\('apply', next\)/)
assert.match(source, /preset-options/)
assert.match(source, /endpoint-mode/)
assert.match(source, /picker-footer/)
assert.match(source, /动态时间/)
assert.match(source, /静态时间/)
assert.match(source, /endpoint-connector/)
assert.match(source, /endpoint-static-badge/)
assert.match(source, /side === 'start' && draft\[side\]\.mode === 'static'/)
assert.match(
  source,
  /import\s*{[\s\S]*ElConfigProvider[\s\S]*ElDatePickerPanel[\s\S]*}\s*from\s*'element-plus'/
)
assert.match(source, /import elementZhCnLocale from 'element-plus\/es\/locale\/lang\/zh-cn'/)
assert.match(source, /import 'element-plus\/es\/components\/date-picker-panel\/style\/css'/)
assert.match(source, /const calendarRange = computed/)
assert.match(source, /function updateCalendarRange/)
assert.match(source, /dashboardDateExpressionCalendarRange\(draft\.value, now\.value, props\.timezone\)/)
assert.match(source, /buildDashboardDateExpressionFromCalendarRange\(value\)/)
assert.match(source, /if \(next\) draft\.value = next/)
assert.match(
  source,
  /<ElConfigProvider :locale="elementZhCnLocale">[\s\S]*<ElDatePickerPanel/
)
assert.match(source, /<ElDatePickerPanel[\s\S]*v-model="calendarRange"/)
assert.match(source, /type="daterange"/)
assert.match(source, /value-format="YYYY-MM-DD"/)
assert.match(source, /unlink-panels/)
assert.match(source, /:width="680"/)
assert.match(source, /grid-template-columns:\s*142px minmax\(0, 1fr\)/)
assert.match(
  source,
  /\.calendar-panel :deep\(\.el-date-range-picker\)\s*{[\s\S]*?width:\s*100%/
)
assert.match(
  source,
  /\.calendar-panel :deep\(\.el-date-range-picker \.el-picker-panel__body\)\s*{[\s\S]*?min-width:\s*0/
)
assert.match(
  source,
  /:global\(\.dashboard-date-expression-popper\)\s*{[\s\S]*?max-width:\s*calc\(100vw - 16px\)/
)
assert.match(source, /\.date-expression-picker--roi[\s\S]*?\.endpoint-controls[\s\S]*?display:\s*flex/)
assert.match(source, /\.date-expression-picker--roi[\s\S]*?\.endpoint-connector[\s\S]*?color:\s*#86909c/)
assert.match(source, /\.date-expression-picker--roi[\s\S]*?\.endpoint-static-badge[\s\S]*?background:\s*#f2f3f5/)
assert.match(
  source,
  /@media \(max-width: 560px\)[\s\S]*?\.picker-body\s*{[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\)/
)
const compactViewportStyles = source.match(
  /@media \(max-width: 720px\) \{([\s\S]*?)\n\}\n\n@media \(max-width: 560px\)/
)?.[1] || ''
assert.match(compactViewportStyles, /\.calendar-panel\s*{[\s\S]*?min-width:\s*502px/)
assert.doesNotMatch(source, /resourceId|dashboardMode|ROI看板|sq-view/)

console.log('dashboard date expression picker contract passed')
