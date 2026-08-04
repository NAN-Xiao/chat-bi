import assert from 'node:assert/strict'
import { resolveInsightDisplay } from './chartInsight.ts'

// 看板卡片是纵向 flex：header-bar(高度随 density 变化) + chart-show-area(填充剩余高度)。
// insightDensity 由 chart-show-area 的测量高度算出，而 density 又通过根节点 class 改变
// header-bar 的 min-height，从而反过来改变 chart-show-area 高度。
// 若密度阈值没有滞回，测量高度会在阈值附近来回跳变 → density 反复翻转 → ResizeObserver
// 每次都触发重渲染 → 图表“不停重新加载/闪烁”。
//
// header-bar min-height 取自 sq-view/index.vue 的样式：regular/compact=34，mini=28，basic=24。
const HEADER_HEIGHT = { regular: 34, compact: 34, mini: 28, basic: 24 }

// 模拟 ResizeObserver ↔ density 的反馈回路：每一步用“当前 density 对应的 header 高度”推出
// chart-show-area 的测量高度，再喂回 resolveInsightDisplay。稳定布局必须收敛到不动点。
function simulateDensityFeedback(base, containerInnerHeight) {
  const measuredHeight = (density) =>
    containerInnerHeight - HEADER_HEIGHT[density ?? 'compact']

  let previousLayout
  let previousDensity
  let density
  const trail = []
  for (let i = 0; i < 12; i += 1) {
    const height = measuredHeight(density)
    const display = resolveInsightDisplay({
      ...base,
      height,
      previousLayout,
      previousDensity,
    })
    trail.push(`${display.density}@${height}`)
    const converged =
      display.density === previousDensity && height === measuredHeight(previousDensity)
    previousLayout = display.layout
    previousDensity = display.density
    density = display.density
    if (converged) {
      return { converged: true, trail }
    }
  }
  return { converged: false, trail }
}

const lineBase = {
  chartType: 'line',
  data: [
    { date: '2026-08-01', value: 10 },
    { date: '2026-08-02', value: 12 },
  ],
  x: [{ value: 'date' }],
  y: [{ value: 'value' }],
  series: [],
  dashboard: true,
  width: 600,
}

// containerInnerHeight=462 让 chart-show-area 落在 TOP_MINI_MAX_HEIGHT(430) 附近：
// compact header(34) → 428(<430 判 mini)，mini header(28) → 434(≥430 判 compact) → 无滞回则震荡。
const lineResult = simulateDensityFeedback(lineBase, 462)
assert.ok(
  lineResult.converged,
  `折线卡片自适应密度必须收敛，否则 header 高度与测量高度互相反馈导致不停重绘：${lineResult.trail.join(' -> ')}`
)

const columnBase = {
  chartType: 'column',
  data: [
    { name: 'A', value: 10 },
    { name: 'B', value: 12 },
  ],
  x: [{ value: 'name' }],
  y: [{ value: 'value' }],
  series: [],
  dashboard: true,
  width: 600,
}

// rich top summary(column) 在 TOP_BASIC_MAX_HEIGHT(360) 附近 compact(34)↔basic(24) 高差 10px。
// containerInnerHeight=390：compact → 356(<360 判 basic)，basic → 366(≥360 判 compact) → 无滞回则震荡。
const columnResult = simulateDensityFeedback(columnBase, 390)
assert.ok(
  columnResult.converged,
  `柱状卡片自适应密度必须收敛，rich top summary 也不能在 basic/compact 间反复翻转：${columnResult.trail.join(' -> ')}`
)

// 直接断言 TOP 分支的密度阈值具备滞回：进入较密档位后，测量高度小幅回升不得立刻切回。
assert.equal(
  resolveInsightDisplay({ ...lineBase, height: 434, previousLayout: 'top', previousDensity: 'mini' })
    .density,
  'mini',
  'mini 档位下测量高度回升到 434(阈值 430 上方一个 header 高差内)必须保持 mini，不能立刻切回 compact'
)
assert.equal(
  resolveInsightDisplay({
    ...lineBase,
    height: 426,
    previousLayout: 'top',
    previousDensity: 'compact',
  }).density,
  'compact',
  'compact 档位下测量高度下探到 426(阈值 430 下方一个 header 高差内)必须保持 compact，不能立刻切到 mini'
)

console.log('chartInsight top-density stability tests passed')
