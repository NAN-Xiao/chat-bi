import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./index.vue', import.meta.url)), 'utf8')
const style = source.slice(source.indexOf('<style scoped'))

assert.match(source, /class="chart-show-area"/)
assert.doesNotMatch(source, /ref="chartShowAreaRef"/)
assert.match(source, /ref="dashboardFilterControlsRef"[^>]*class="dashboard-filter-controls"/)
assert.match(source, /surface="dashboard"/)
assert.match(source, /:has-outer-title="true"/)
assert.match(
  style,
  /\.chart-base-container\s*\{[^}]*display:\s*flex[^}]*flex-direction:\s*column/s
)
assert.match(style, /\.header-bar\s*\{[^}]*flex:\s*0\s+0\s+auto/s)
assert.match(style, /\.dashboard-filter-controls\s*\{[^}]*flex:\s*0\s+0\s+auto/s)
assert.match(
  style,
  /\.chart-show-area\s*\{[^}]*flex:\s*1\s+1\s+0[^}]*height:\s*auto[^}]*min-width:\s*0[^}]*min-height:\s*0/s,
  '图表外层必须使用零基准并允许双轴收缩，避免摘要尺寸反推父容器'
)
assert.match(
  style,
  /\.chart-content-row\s*\{[^}]*flex:\s*1\s+1\s+0[^}]*min-width:\s*0[^}]*min-height:\s*0/s,
  '顶部和侧边摘要共用的图表行必须使用稳定剩余空间'
)
assert.match(
  style,
  /:deep\(\.chart-container\)\s*\{[^}]*flex:\s*1\s+1\s+0[^}]*min-width:\s*0[^}]*min-height:\s*0/s,
  '图表容器不能通过内容宽高反向撑开图表行'
)
assert.doesNotMatch(style, /\.chart-show-area\s*\{[^}]*height:\s*calc\(/s)
assert.doesNotMatch(
  style,
  /:has\([^)]*(?:pivot-toolbar|date-expression-toolbar)[^)]*\)[^{]*\.chart-show-area\s*\{[^}]*height:/s
)
assert.doesNotMatch(style, /\.chart-loading-info\s*\{[^}]*min-height:\s*140px/s)

assert.match(source, /const frameSize = ref<InsightFrameSize \| null>\(null\)/)
assert.match(source, /function measureCanonicalFrame\(\) \{[\s\S]*resolveCanonicalInsightFrame/)
assert.match(source, /if \(isDashboardSurface\.value && !frameSize\.value\) \{\s*return false\s*\}/)
assert.match(
  source,
  /if \(measuredFrame \|\| !isDashboardSurface\.value\) \{\s*previousInsightLayout = display\.layout\s*previousInsightDensity = display\.density/,
  'unmeasured 默认展示不能污染首次有效测量的迟滞历史'
)
assert.match(source, /resizeObserver\.observe\(containerRef\.value, \{ box: 'border-box' \}\)/)
assert.match(
  source,
  /resizeObserver\.observe\(dashboardFilterControlsRef\.value, \{ box: 'border-box' \}\)/
)
assert.doesNotMatch(source, /resizeObserver\.observe\(chartShowAreaRef\.value/)

const observerStart = source.indexOf('resizeObserver = new ResizeObserver')
const observerEnd = source.indexOf('resizeObserver.observe(containerRef.value', observerStart)
assert.ok(observerStart >= 0 && observerEnd > observerStart, '需要统一的稳定边界 ResizeObserver')
const observerCallback = source.slice(observerStart, observerEnd)
assert.match(observerCallback, /measureCanonicalFrame\(\)/)
assert.doesNotMatch(
  observerCallback,
  /scheduleRenderChart/,
  '尺寸回调只能更新策略尺寸，图表 resize 由 ChartComponent 独占'
)

assert.match(source, /const insightFrameStructureKey = computed/)
assert.match(source, /nextTick\(measureCanonicalFrame\)/)
assert.match(style, /--insight-frame-compact-padding-inline:\s*16px/)
assert.match(style, /--insight-frame-compact-padding-block:\s*14px/)
assert.match(style, /--insight-frame-compact-header-height:\s*34px/)
assert.match(style, /--insight-frame-compact-header-gap:\s*10px/)
assert.match(
  style,
  /padding:\s*var\(--insight-frame-compact-padding-block\)\s+var\(--insight-frame-compact-padding-inline\)/
)
assert.match(style, /min-height:\s*var\(--insight-frame-compact-header-height\)/)
assert.match(style, /margin-bottom:\s*var\(--insight-frame-compact-header-gap\)/)
assert.match(
  style,
  /&\.insight-density-mini,\s*&\.insight-density-basic\s*\{[^}]*padding:\s*10px\s+12px[^}]*\.header-bar\s*\{[^}]*min-height:\s*28px[^}]*margin-bottom:\s*6px/s,
  'mini/basic 必须保留原有紧凑外层几何，规范帧只统一策略输入'
)
assert.match(
  style,
  /&\.insight-density-basic\s*\{[^}]*padding:\s*8px\s+10px[^}]*\.header-bar\s*\{[^}]*min-height:\s*24px[^}]*margin-bottom:\s*4px/s,
  'basic 必须保留最紧凑的原有外层几何'
)
assert.match(
  style,
  /\.dashboard-filter-controls--combined\s*\{[\s\S]*> \.pivot-toolbar\s*\{[^}]*flex:\s*1\s+1\s+0[^}]*min-width:\s*0/s
)
assert.doesNotMatch(
  style,
  /\.pivot-toolbar\s*\{[^}]*margin-bottom:\s*4px/s,
  'density 不得改变工具栏外层 block contribution'
)
assert.match(source, /type !== 'table' && type !== 'metric'/)
console.log('SQView responsive layout tests passed')
