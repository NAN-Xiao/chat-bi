import assert from 'node:assert/strict'
import { resolveInsightDisplay } from './chartInsight.ts'

// 当前运行时只以真实外部 resize 产生的规范帧决定布局和密度。本测试保留旧的密度相关
// 内部剩余高度模型作为防回归模型：若迟滞被移除，曾经的档位翻转路径会再次暴露出来。
//
// header-bar min-height 取自 sq-view/index.vue 的样式：regular/compact=34，mini=28，basic=24。
const HEADER_HEIGHT = { regular: 34, compact: 34, mini: 28, basic: 24 }

// 防回归模型：每一步用当前 density 的 header 高度推导历史内部可用高度，再喂回策略。
// 这不是 SQView 当前的测量来源；策略仍须在该旧路径上收敛，避免未来恢复类似反馈时震荡。
function simulateLegacyDensityFeedback(base, containerInnerHeight) {
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

// containerInnerHeight=462 让历史内部可用高度落在 TOP_MINI_MAX_HEIGHT(430) 附近：
// compact header(34) → 428(<430 判 mini)，mini header(28) → 434(≥430 判 compact) → 无滞回则震荡。
const lineResult = simulateLegacyDensityFeedback(lineBase, 462)
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
const columnResult = simulateLegacyDensityFeedback(columnBase, 390)
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
