import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./index.vue', import.meta.url)), 'utf8')
const style = source.slice(source.indexOf('<style scoped'))

assert.match(source, /ref="chartShowAreaRef"[^>]*class="chart-show-area"/)
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

const measureFrameMatch = source.match(/function measureFrame\(\) \{([\s\S]*?)\r?\n\}/)
assert.ok(measureFrameMatch, '需要通过统一函数测量图表可用区域')
assert.match(
  measureFrameMatch[1],
  /if \(!el\) \{\s*return false\s*\}/,
  '图表区域尚未挂载时应明确返回尺寸未变化'
)
assert.match(
  measureFrameMatch[1],
  /if \(nextSize\.width === frameSize\.value\.width && nextSize\.height === frameSize\.value\.height\) \{\s*return false\s*\}/,
  '宽高未变化时应明确返回 false'
)
assert.match(
  measureFrameMatch[1],
  /frameSize\.value = nextSize\s*return true/,
  '记录新宽高后应返回 true'
)

const resizeObserverMatch = source.match(
  /resizeObserver = new ResizeObserver\(\(\) => \{([\s\S]*?)\r?\n\s*\}\)/
)
assert.ok(resizeObserverMatch, '卡片需要监听自身图表区域尺寸')
assert.match(
  resizeObserverMatch[1],
  /const frameChanged = measureFrame\(\)/,
  '尺寸监听回调需要保存真实变化结果'
)
assert.match(
  resizeObserverMatch[1],
  /if \(frameChanged && chartType\.value !== 'table'\) scheduleRenderChart\(\)/,
  '只有真实尺寸变化时才允许销毁并重建非表格图表'
)
console.log('SQView responsive layout tests passed')
