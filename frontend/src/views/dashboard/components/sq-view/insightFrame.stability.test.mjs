import assert from 'node:assert/strict'
import { resolveInsightDisplay } from '../../../chat/component/chartInsight.ts'
import {
  parseCssPixel,
  resolveCanonicalInsightFrame,
  sameInsightFrame,
} from './insightFrame.ts'

assert.equal(parseCssPixel('16px'), 16)
assert.equal(parseCssPixel(' -0.5px '), -0.5)
assert.equal(parseCssPixel('0'), null)
assert.equal(parseCssPixel('calc(10px + 2px)'), null)
assert.equal(parseCssPixel(''), null)

function geometryForFrame(width, height, controlsBlock = 0) {
  return {
    borderBox: { width: width + 32, height: height + 72 + controlsBlock },
    borderInline: 0,
    borderBlock: 0,
    compactPaddingInline: 16,
    compactPaddingBlock: 14,
    compactHeaderHeight: 34,
    compactHeaderGap: 10,
    controlsBlock,
  }
}

assert.deepEqual(
  resolveCanonicalInsightFrame({
    borderBox: { width: 1179, height: 360 },
    borderInline: 0,
    borderBlock: 0,
    compactPaddingInline: 16,
    compactPaddingBlock: 14,
    compactHeaderHeight: 34,
    compactHeaderGap: 10,
    controlsBlock: 36,
  }),
  { width: 1147, height: 252 },
  '录屏卡片必须归一到 compact 稳定帧，不能继续使用 basic/mini 的 280/270px 子区域'
)
assert.equal(resolveCanonicalInsightFrame(geometryForFrame(0, 300)), null)
assert.equal(
  sameInsightFrame(
    resolveCanonicalInsightFrame(geometryForFrame(520, 400, 36)),
    { width: 520, height: 400 }
  ),
  true
)

const dates = [
  { date: '2026-08-01', value: 10, group: 'A' },
  { date: '2026-08-02', value: 12, group: 'B' },
]
const metricAxes = ['m1', 'm2', 'm3', 'm4'].map((value) => ({ value }))
const groupedData = ['A', 'B', 'C', 'D', 'E', 'F'].map((group, index) => ({
  date: '2026-08-01',
  value: index + 1,
  group,
}))
const weeklyDates = [
  { date: '2026-08-01 week', value: 10 },
  { date: '2026-08-08 week', value: 12 },
]
const monthlyDates = [
  { date: '2026-07', value: 10 },
  { date: '2026-08', value: 12 },
]
const scenarios = [
  {
    name: 'multi-line',
    chartType: 'line',
    data: dates,
    x: [{ value: 'date' }],
    y: metricAxes,
    series: [],
  },
  {
    name: 'multi-area',
    chartType: 'area',
    data: dates,
    x: [{ value: 'date' }],
    y: metricAxes,
    series: [],
  },
  {
    name: 'multi-column',
    chartType: 'column',
    data: dates,
    x: [{ value: 'date' }],
    y: metricAxes,
    series: [],
  },
  {
    name: 'multi-bar',
    chartType: 'bar',
    data: dates,
    x: [{ value: 'date' }],
    y: metricAxes,
    series: [],
  },
  {
    name: 'six-groups',
    chartType: 'line',
    data: groupedData,
    x: [{ value: 'date' }],
    y: [{ value: 'value' }],
    series: [{ value: 'group' }],
  },
  {
    name: 'sankey',
    chartType: 'sankey',
    data: dates,
    x: [{ value: 'date' }],
    y: [{ value: 'value' }],
    series: [],
  },
  {
    name: 'treemap',
    chartType: 'treemap',
    data: dates,
    x: [{ value: 'date' }],
    y: [{ value: 'value' }],
    series: [],
  },
  {
    name: 'wide-day-trend',
    chartType: 'line',
    data: dates,
    x: [{ value: 'date' }],
    y: [{ value: 'value' }],
    series: [],
  },
  {
    name: 'wide-week-trend',
    chartType: 'line',
    data: weeklyDates,
    x: [{ value: 'date' }],
    y: [{ value: 'value' }],
    series: [],
  },
  {
    name: 'wide-month-trend',
    chartType: 'line',
    data: monthlyDates,
    x: [{ value: 'date' }],
    y: [{ value: 'value' }],
    series: [],
  },
  {
    name: 'rich-bar',
    chartType: 'bar',
    data: dates,
    x: [{ value: 'date' }],
    y: [{ value: 'value' }],
    series: [],
  },
  {
    name: 'rich-column',
    chartType: 'column',
    data: dates,
    x: [{ value: 'date' }],
    y: [{ value: 'value' }],
    series: [],
  },
  {
    name: 'rich-heatmap',
    chartType: 'heatmap',
    data: dates,
    x: [{ value: 'date' }],
    y: [{ value: 'value' }],
    series: [],
  },
  {
    name: 'rich-scatter',
    chartType: 'scatter',
    data: dates,
    x: [{ value: 'date' }],
    y: [{ value: 'value' }],
    series: [],
  },
  {
    name: 'rich-funnel',
    chartType: 'funnel',
    data: dates,
    x: [{ value: 'date' }],
    y: [{ value: 'value' }],
    series: [],
  },
  {
    name: 'pie',
    chartType: 'pie',
    data: dates,
    x: [{ value: 'date' }],
    y: [{ value: 'value' }],
    series: [],
  },
  {
    name: 'empty-line',
    chartType: 'line',
    data: [],
    x: [{ value: 'date' }],
    y: [{ value: 'value' }],
    series: [],
  },
]
const frameWidths = [
  299, 300, 301, 439, 440, 441, 499, 500, 501, 559, 560, 561, 679, 680, 681, 759,
  760, 761, 899, 900, 901, 1099, 1100, 1101,
]
const frameHeights = [
  249, 250, 251, 259, 260, 261, 279, 280, 281, 329, 330, 331, 359, 360, 361, 389,
  390, 391, 429, 430, 431,
]

function assertConverges(scenario, frame) {
  let previousLayout
  let previousDensity
  let previousSignature = ''
  for (let step = 0; step < 8; step += 1) {
    const display = resolveInsightDisplay({
      ...scenario,
      dashboard: true,
      width: frame.width,
      height: frame.height,
      previousLayout,
      previousDensity,
    })
    const signature = JSON.stringify(display)
    if (signature === previousSignature) return
    previousSignature = signature
    previousLayout = display.layout
    previousDensity = display.density
  }
  assert.fail(`${scenario.name} 未在稳定帧 ${frame.width}x${frame.height} 收敛`)
}

for (const scenario of scenarios) {
  for (const width of frameWidths) {
    for (const height of frameHeights) {
      for (const controlsBlock of [0, 30, 36, 66]) {
        const frame = resolveCanonicalInsightFrame(geometryForFrame(width, height, controlsBlock))
        assert.ok(frame, `${scenario.name} 应生成正规范化尺寸`)
        assert.deepEqual(frame, { width, height })
        assertConverges(scenario, frame)
      }
    }
  }
}

console.log('insight frame stability tests passed')
