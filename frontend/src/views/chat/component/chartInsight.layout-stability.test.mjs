import assert from 'node:assert/strict'
import {
  buildInsightLayoutStateKey,
  resolveInsightDisplay,
} from './chartInsight.ts'

const trend = {
  chartType: 'line',
  data: [
    { date: '2026-08-01', value: 10 },
    { date: '2026-08-02', value: 12 },
  ],
  x: [{ value: 'date' }],
  y: [{ value: 'value' }],
  series: [],
  dashboard: true,
}

assert.equal(
  resolveInsightDisplay({ ...trend, width: 1106, height: 280 }).layout,
  'side',
  '宽屏趋势图在 top 布局的 280px 高度应切换到 side'
)
assert.equal(
  resolveInsightDisplay({ ...trend, width: 1102, height: 270, previousLayout: 'side' }).layout,
  'side',
  '切换后的 side 布局高度约 270px 时必须保持 side，不能切回 top 形成重绘循环'
)
assert.equal(
  resolveInsightDisplay({ ...trend, width: 1102, height: 270, previousLayout: 'top' }).layout,
  'top',
  'top 布局低于 280px 时不能进入 side，迟滞区间必须保持上一布局'
)
assert.equal(
  resolveInsightDisplay({ ...trend, width: 1102, height: 255, previousLayout: 'side' }).layout,
  'top',
  'side 布局低于退出阈值后应稳定回到 top'
)
assert.equal(
  resolveInsightDisplay({
    ...trend,
    y: [{ value: 'value' }, { value: 'other' }],
    width: 1106,
    height: 280,
    previousLayout: 'side',
  }).layout,
  'top',
  '多指标趋势图不能误用宽屏单指标布局迟滞'
)

assert.equal(
  resolveInsightDisplay({
    ...trend,
    y: [{ value: 'value' }, { value: 'd1' }, { value: 'd3' }, { value: 'd7' }],
    width: 1094,
    height: 324,
    previousLayout: 'side',
    previousDensity: 'compact',
  }).density,
  'compact',
  'compact 样式压缩后的 324px 高度仍应保持 compact，不能反向切换成 mini'
)
assert.equal(
  resolveInsightDisplay({
    ...trend,
    y: [{ value: 'value' }, { value: 'd1' }, { value: 'd3' }, { value: 'd7' }],
    width: 1102,
    height: 342,
    previousLayout: 'side',
    previousDensity: 'mini',
  }).density,
  'mini',
  'mini 样式扩展后的 342px 高度仍应保持 mini，不能反向切换成 compact'
)
assert.equal(
  resolveInsightDisplay({
    ...trend,
    y: [{ value: 'value' }, { value: 'd1' }, { value: 'd3' }, { value: 'd7' }],
    width: 1102,
    height: 355,
    previousLayout: 'side',
    previousDensity: 'mini',
  }).density,
  'compact',
  '真实高度跨出迟滞上界后应允许 mini 切换为 compact'
)
assert.equal(
  resolveInsightDisplay({
    ...trend,
    y: [{ value: 'value' }, { value: 'd1' }, { value: 'd3' }, { value: 'd7' }],
    width: 1094,
    height: 305,
    previousLayout: 'side',
    previousDensity: 'compact',
  }).density,
  'mini',
  '真实高度跨出迟滞下界后应允许 compact 切换为 mini'
)

const compactAtHardFloor = resolveInsightDisplay({
  ...trend,
  width: 300,
  height: 200,
  previousLayout: 'top',
})
assert.equal(compactAtHardFloor.show, true, '达到硬下界时应显示摘要')
assert.equal(compactAtHardFloor.density, 'basic', '达到硬下界时应使用 basic 摘要')

assert.equal(
  resolveInsightDisplay({ ...trend, width: 299, height: 200 }).show,
  false,
  '宽度低于硬下界时应隐藏摘要'
)
assert.equal(
  resolveInsightDisplay({ ...trend, width: 300, height: 199 }).show,
  false,
  '高度低于硬下界时应隐藏摘要'
)

const restoredAfterWidth = resolveInsightDisplay({
  ...trend,
  width: 520,
  height: 400,
  previousLayout: 'top',
  previousDensity: 'mini',
  previousShow: false,
})
const freshAtRestoredSize = resolveInsightDisplay({
  ...trend,
  width: 520,
  height: 400,
  previousLayout: 'top',
  previousDensity: 'mini',
})
assert.equal(restoredAfterWidth.show, true, '恢复宽度后不应再额外要求高度达到 430px')
assert.deepEqual(
  restoredAfterWidth,
  freshAtRestoredSize,
  '固定布局与密度历史时，显隐结果不能依赖 previousShow 路径'
)

const topHistory = resolveInsightDisplay({
  ...trend,
  width: 1102,
  height: 270,
  previousLayout: 'top',
  previousDensity: 'basic',
})
const sideHistory = resolveInsightDisplay({
  ...trend,
  width: 1102,
  height: 270,
  previousLayout: 'side',
  previousDensity: 'mini',
})
assert.equal(topHistory.layout, 'top', '布局迟滞区允许保留 top 历史')
assert.equal(sideHistory.layout, 'side', '布局迟滞区允许保留 side 历史')

const multiMetricColumn = {
  chartType: 'column',
  data: [
    { week: '2026-09-21', day1: 100, day2: 10 },
    { week: '2026-09-28', day1: 90, day2: 12 },
  ],
  x: [{ value: 'week' }],
  y: [
    { value: 'day1' },
    { value: 'day2' },
    { value: 'day3' },
    { value: 'day4' },
  ],
  series: [],
  dashboard: true,
}

const paddingByDensity = { regular: 20, compact: 20, mini: 16, basic: 14 }

function simulateLayoutWidthFeedback(chart, borderBoxWidth, height) {
  let previousLayout
  let previousDensity
  const trail = []
  for (let index = 0; index < 8; index += 1) {
    const measuredWidth = borderBoxWidth - 2 * paddingByDensity[previousDensity || 'compact']
    const display = resolveInsightDisplay({
      ...chart,
      width: measuredWidth,
      height,
      previousLayout,
      previousDensity,
    })
    trail.push(`${display.layout}:${display.density}@${measuredWidth}`)
    if (display.layout === previousLayout && display.density === previousDensity) {
      return { converged: true, trail }
    }
    previousLayout = display.layout
    previousDensity = display.density
  }
  return { converged: false, trail }
}

const multiMetricFeedback = simulateLayoutWidthFeedback(multiMetricColumn, 710, 320)
assert.ok(
  multiMetricFeedback.converged,
  `多指标卡片的顶部/侧边摘要必须在内边距反馈下收敛：${multiMetricFeedback.trail.join(' -> ')}`
)


const paddingBlockByDensity = { regular: 18, compact: 18, mini: 14, basic: 12 }
const headerBlockByDensity = { regular: 46, compact: 46, mini: 34, basic: 28 }

function simulateLayoutHeightFeedback(chart, borderBoxHeight, controlsBlock) {
  let previousLayout
  let previousDensity
  const trail = []
  for (let index = 0; index < 8; index += 1) {
    const density = previousDensity || 'compact'
    const measuredHeight = borderBoxHeight
      - 2 * paddingBlockByDensity[density]
      - headerBlockByDensity[density]
      - controlsBlock
    const display = resolveInsightDisplay({
      ...chart,
      width: 1380,
      height: measuredHeight,
      previousLayout,
      previousDensity,
    })
    trail.push(`${display.layout}:${display.density}@${measuredHeight}`)
    if (display.layout === previousLayout && display.density === previousDensity) {
      return { converged: true, trail }
    }
    previousLayout = display.layout
    previousDensity = display.density
  }
  return { converged: false, trail }
}

const multiMetricHeightFeedback = simulateLayoutHeightFeedback(multiMetricColumn, 374, 36)
assert.ok(
  multiMetricHeightFeedback.converged,
  `多指标卡片的顶部/侧边摘要必须在高度反馈下收敛：${multiMetricHeightFeedback.trail.join(' -> ')}`
)

const wideTrendFeedback = simulateLayoutWidthFeedback(trend, 1130, 300)
assert.ok(
  wideTrendFeedback.converged,
  `宽屏趋势卡片的顶部/侧边摘要必须在内边距反馈下收敛：${wideTrendFeedback.trail.join(' -> ')}`
)

assert.equal(
  resolveInsightDisplay({ ...multiMetricColumn, width: 640, height: 320, previousLayout: 'side' }).layout,
  'top',
  '多指标卡片真正变窄后应退出侧边摘要'
)
assert.equal(
  resolveInsightDisplay({ ...multiMetricColumn, width: 720, height: 320, previousLayout: 'top' }).layout,
  'side',
  '多指标卡片真正变宽后应进入侧边摘要'
)
assert.equal(
  resolveInsightDisplay({ ...multiMetricColumn, width: 720, height: 250, previousLayout: 'side' }).layout,
  'top',
  '多指标卡片真正变矮后应退出侧边摘要'
)
assert.equal(
  resolveInsightDisplay({ ...multiMetricColumn, width: 720, height: 310, previousLayout: 'top' }).layout,
  'side',
  '多指标卡片真正变高后应进入侧边摘要'
)

assert.equal(
  resolveInsightDisplay({ ...trend, width: 1200, height: 540, previousLayout: 'top' }).layout,
  'top',
  '宽屏趋势图的宽高比处于切换带时应保留顶部布局'
)
assert.equal(
  resolveInsightDisplay({ ...trend, width: 1200, height: 540, previousLayout: 'side' }).layout,
  'side',
  '宽屏趋势图的宽高比处于切换带时应保留侧边布局'
)

const stateKey = buildInsightLayoutStateKey({
  viewId: 'chart-a',
  chartType: 'line',
  x: trend.x,
  y: trend.y,
  series: trend.series,
  dashboard: true,
})
assert.notEqual(
  stateKey,
  buildInsightLayoutStateKey({
    viewId: 'chart-b',
    chartType: 'line',
    x: trend.x,
    y: trend.y,
    series: trend.series,
    dashboard: true,
  }),
  '组件复用为另一张图表时必须生成不同状态签名，不能继承旧图布局'
)
assert.notEqual(
  stateKey,
  buildInsightLayoutStateKey({
    viewId: 'chart-a',
    chartType: 'line',
    x: trend.x,
    y: [{ value: 'other' }],
    series: trend.series,
    dashboard: true,
  }),
  '同一图表改变布局资格轴时必须重置迟滞状态'
)

console.log('chartInsight layout stability tests passed')
