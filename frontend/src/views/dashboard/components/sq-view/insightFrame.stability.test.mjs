import assert from 'node:assert/strict'
import { resolveInsightDisplay } from '../../../chat/component/chartInsight.ts'
import {
  parseCssPixel,
  resolveCanonicalInsightFrame,
  sameInsightFrame,
} from './insightFrame.ts'
import {
  resolveTabInsightControlsReserve,
  resolveTabInsightControlsVariant,
} from './tabInsightLayout.ts'

assert.deepEqual(
  ['none', 'pivot', 'date', 'combined'].map(resolveTabInsightControlsReserve),
  [0, 30, 36, 36],
  'Tab 工具栏必须使用固定 reserve，不读取实时子节点高度'
)
assert.equal(resolveTabInsightControlsVariant({ pivot: true, date: true }), 'combined')

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
const compactDashboardFrame = resolveCanonicalInsightFrame({
  borderBox: { width: 752, height: 330 },
  borderInline: 0,
  borderBlock: 0,
  compactPaddingInline: 16,
  compactPaddingBlock: 14,
  compactHeaderHeight: 34,
  compactHeaderGap: 10,
  controlsBlock: 36,
})
assert.deepEqual(
  compactDashboardFrame,
  { width: 720, height: 222 },
  '截图中的第一行卡片必须按 Card 根节点得到稳定规范帧'
)
assert.equal(
  resolveInsightDisplay({
    chartType: 'line',
    data: [{ date: '2026-08-04', value: 10 }],
    x: [{ value: 'date' }],
    y: [{ value: 'value' }],
    series: [],
    dashboard: true,
    ...compactDashboardFrame,
  }).show,
  true,
  '752x330 且包含日期控件的看板卡片必须显示 basic 摘要'
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
    name: 'wide-area-trend',
    chartType: 'area',
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
const initialHistories = [
  {},
  { previousLayout: 'top', previousDensity: 'regular' },
  { previousLayout: 'top', previousDensity: 'compact' },
  { previousLayout: 'top', previousDensity: 'mini' },
  { previousLayout: 'top', previousDensity: 'basic' },
  { previousLayout: 'side', previousDensity: 'regular' },
  { previousLayout: 'side', previousDensity: 'compact' },
  { previousLayout: 'side', previousDensity: 'mini' },
  { previousLayout: 'side', previousDensity: 'basic' },
]
const requiredHysteresisBoundaries = new Set([
  'top-basic-width',
  'top-mini-width',
  'top-mini-height',
  'side-mini-width',
  'side-mini-height',
  'side-compact-width',
  'side-compact-height',
])
const exercisedHysteresisBoundaries = new Set()
const requiredBoundarySamples = new Set([
  'top-basic-width:419', 'top-basic-width:420', 'top-basic-width:421',
  'top-basic-width:459', 'top-basic-width:460', 'top-basic-width:461',
  'top-basic-height:339', 'top-basic-height:340', 'top-basic-height:341',
  'top-basic-height:379', 'top-basic-height:380', 'top-basic-height:381',
  'top-mini-width:539', 'top-mini-width:540', 'top-mini-width:541',
  'top-mini-width:579', 'top-mini-width:580', 'top-mini-width:581',
  'top-mini-height:409', 'top-mini-height:410', 'top-mini-height:411',
  'top-mini-height:449', 'top-mini-height:450', 'top-mini-height:451',
  'side-mini-width:739', 'side-mini-width:740', 'side-mini-width:741',
  'side-mini-width:779', 'side-mini-width:780', 'side-mini-width:781',
  'side-mini-height:309', 'side-mini-height:310', 'side-mini-height:311',
  'side-mini-height:349', 'side-mini-height:350', 'side-mini-height:351',
  'side-compact-width:879', 'side-compact-width:880', 'side-compact-width:881',
  'side-compact-width:919', 'side-compact-width:920', 'side-compact-width:921',
  'side-compact-height:369', 'side-compact-height:370', 'side-compact-height:371',
  'side-compact-height:409', 'side-compact-height:410', 'side-compact-height:411',
  'wide-day-trend-aspect-ratio:499', 'wide-day-trend-aspect-ratio:500', 'wide-day-trend-aspect-ratio:501',
  'wide-area-trend-aspect-ratio:499', 'wide-area-trend-aspect-ratio:500', 'wide-area-trend-aspect-ratio:501',
  'rich-width:499', 'rich-width:500', 'rich-width:501',
  'rich-width:639', 'rich-width:640', 'rich-width:641',
])
const exercisedBoundarySamples = new Set()

function assertConverges(scenario, frame, initialHistory = {}) {
  let previousLayout = initialHistory.previousLayout
  let previousDensity = initialHistory.previousDensity
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

function assertDensityTransition(scenario, boundary, phase, params, expected) {
  exercisedHysteresisBoundaries.add(boundary)
  const sample = boundary.includes('height') || boundary.includes('aspect-ratio')
    ? params.height
    : params.width
  exercisedBoundarySamples.add(`${boundary}:${sample}`)
  const display = resolveInsightDisplay({ ...scenario, dashboard: true, ...params })
  for (const [property, value] of Object.entries(expected)) {
    assert.equal(
      display[property],
      value,
      `${scenario.name} ${boundary} ${phase} 应为 ${property}=${value}，实际为 ${display[property]}`
    )
  }
}

const topTrend = scenarios.find((scenario) => scenario.name === 'wide-day-trend')
const sideSummary = scenarios.find((scenario) => scenario.name === 'multi-line')
const richBar = scenarios.find((scenario) => scenario.name === 'rich-bar')
assert.ok(topTrend && sideSummary && richBar, '边界测试需要 top、side 和 rich 场景')

const boundaryCases = [
  {
    scenario: topTrend,
    boundary: 'top-basic-width',
    cases: [
      ['enter', { width: 419, height: 500, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'basic' }],
      ['enter-boundary', { width: 420, height: 500, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'mini' }],
      ['enter-after', { width: 421, height: 500, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'mini' }],
      ['keep', { width: 459, height: 500, previousLayout: 'top', previousDensity: 'basic' }, { show: true, layout: 'top', density: 'basic' }],
      ['exit-boundary', { width: 460, height: 500, previousLayout: 'top', previousDensity: 'basic' }, { show: true, layout: 'top', density: 'mini' }],
      ['exit-after', { width: 461, height: 500, previousLayout: 'top', previousDensity: 'basic' }, { show: true, layout: 'top', density: 'mini' }],
    ],
  },
  {
    scenario: topTrend,
    boundary: 'top-basic-height',
    cases: [
      ['enter', { width: 600, height: 339, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'basic' }],
      ['enter-boundary', { width: 600, height: 340, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'mini' }],
      ['enter-after', { width: 600, height: 341, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'mini' }],
      ['keep', { width: 600, height: 379, previousLayout: 'top', previousDensity: 'basic' }, { show: true, layout: 'top', density: 'basic' }],
      ['exit-boundary', { width: 600, height: 380, previousLayout: 'top', previousDensity: 'basic' }, { show: true, layout: 'top', density: 'mini' }],
      ['exit-after', { width: 600, height: 381, previousLayout: 'top', previousDensity: 'basic' }, { show: true, layout: 'top', density: 'mini' }],
    ],
  },
  {
    scenario: topTrend,
    boundary: 'top-mini-width',
    cases: [
      ['enter', { width: 539, height: 500, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'mini' }],
      ['enter-boundary', { width: 540, height: 500, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'compact' }],
      ['enter-after', { width: 541, height: 500, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'compact' }],
      ['keep', { width: 579, height: 500, previousLayout: 'top', previousDensity: 'mini' }, { show: true, layout: 'top', density: 'mini' }],
      ['exit-boundary', { width: 580, height: 500, previousLayout: 'top', previousDensity: 'mini' }, { show: true, layout: 'top', density: 'compact' }],
      ['exit-after', { width: 581, height: 500, previousLayout: 'top', previousDensity: 'mini' }, { show: true, layout: 'top', density: 'compact' }],
    ],
  },
  {
    scenario: topTrend,
    boundary: 'top-mini-height',
    cases: [
      ['enter', { width: 600, height: 409, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'mini' }],
      ['enter-boundary', { width: 600, height: 410, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'compact' }],
      ['enter-after', { width: 600, height: 411, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'compact' }],
      ['keep', { width: 600, height: 449, previousLayout: 'top', previousDensity: 'mini' }, { show: true, layout: 'top', density: 'mini' }],
      ['exit-boundary', { width: 600, height: 450, previousLayout: 'top', previousDensity: 'mini' }, { show: true, layout: 'top', density: 'compact' }],
      ['exit-after', { width: 600, height: 451, previousLayout: 'top', previousDensity: 'mini' }, { show: true, layout: 'top', density: 'compact' }],
    ],
  },
  {
    scenario: sideSummary,
    boundary: 'side-mini-width',
    cases: [
      ['enter', { width: 739, height: 500, previousLayout: 'side', previousDensity: 'compact' }, { show: true, layout: 'side', density: 'mini' }],
      ['enter-boundary', { width: 740, height: 500, previousLayout: 'side', previousDensity: 'compact' }, { show: true, layout: 'side', density: 'compact' }],
      ['enter-after', { width: 741, height: 500, previousLayout: 'side', previousDensity: 'compact' }, { show: true, layout: 'side', density: 'compact' }],
      ['keep', { width: 779, height: 500, previousLayout: 'side', previousDensity: 'mini' }, { show: true, layout: 'side', density: 'mini' }],
      ['exit-boundary', { width: 780, height: 500, previousLayout: 'side', previousDensity: 'mini' }, { show: true, layout: 'side', density: 'compact' }],
      ['exit-after', { width: 781, height: 500, previousLayout: 'side', previousDensity: 'mini' }, { show: true, layout: 'side', density: 'compact' }],
    ],
  },
  {
    scenario: sideSummary,
    boundary: 'side-mini-height',
    cases: [
      ['enter', { width: 1000, height: 309, previousLayout: 'side', previousDensity: 'compact' }, { show: true, layout: 'side', density: 'mini' }],
      ['enter-boundary', { width: 1000, height: 310, previousLayout: 'side', previousDensity: 'compact' }, { show: true, layout: 'side', density: 'compact' }],
      ['enter-after', { width: 1000, height: 311, previousLayout: 'side', previousDensity: 'compact' }, { show: true, layout: 'side', density: 'compact' }],
      ['keep', { width: 1000, height: 349, previousLayout: 'side', previousDensity: 'mini' }, { show: true, layout: 'side', density: 'mini' }],
      ['exit-boundary', { width: 1000, height: 350, previousLayout: 'side', previousDensity: 'mini' }, { show: true, layout: 'side', density: 'compact' }],
      ['exit-after', { width: 1000, height: 351, previousLayout: 'side', previousDensity: 'mini' }, { show: true, layout: 'side', density: 'compact' }],
    ],
  },
  {
    scenario: sideSummary,
    boundary: 'side-compact-width',
    cases: [
      ['enter', { width: 879, height: 500, previousLayout: 'side', previousDensity: 'regular' }, { show: true, layout: 'side', density: 'compact' }],
      ['enter-boundary', { width: 880, height: 500, previousLayout: 'side', previousDensity: 'regular' }, { show: true, layout: 'side', density: 'regular' }],
      ['enter-after', { width: 881, height: 500, previousLayout: 'side', previousDensity: 'regular' }, { show: true, layout: 'side', density: 'regular' }],
      ['keep', { width: 919, height: 500, previousLayout: 'side', previousDensity: 'compact' }, { show: true, layout: 'side', density: 'compact' }],
      ['exit-boundary', { width: 920, height: 500, previousLayout: 'side', previousDensity: 'compact' }, { show: true, layout: 'side', density: 'regular' }],
      ['exit-after', { width: 921, height: 500, previousLayout: 'side', previousDensity: 'compact' }, { show: true, layout: 'side', density: 'regular' }],
    ],
  },
  {
    scenario: sideSummary,
    boundary: 'side-compact-height',
    cases: [
      ['enter', { width: 1000, height: 369, previousLayout: 'side', previousDensity: 'regular' }, { show: true, layout: 'side', density: 'compact' }],
      ['enter-boundary', { width: 1000, height: 370, previousLayout: 'side', previousDensity: 'regular' }, { show: true, layout: 'side', density: 'regular' }],
      ['enter-after', { width: 1000, height: 371, previousLayout: 'side', previousDensity: 'regular' }, { show: true, layout: 'side', density: 'regular' }],
      ['keep', { width: 1000, height: 409, previousLayout: 'side', previousDensity: 'compact' }, { show: true, layout: 'side', density: 'compact' }],
      ['exit-boundary', { width: 1000, height: 410, previousLayout: 'side', previousDensity: 'compact' }, { show: true, layout: 'side', density: 'regular' }],
      ['exit-after', { width: 1000, height: 411, previousLayout: 'side', previousDensity: 'compact' }, { show: true, layout: 'side', density: 'regular' }],
    ],
  },
  {
    scenario: richBar,
    boundary: 'rich-width',
    cases: [
      ['before-enter', { width: 499, height: 500, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'mini' }],
      ['enter', { width: 500, height: 500, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'compact' }],
      ['enter-after', { width: 501, height: 500, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'compact' }],
      ['keep', { width: 639, height: 500, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'compact' }],
      ['exit-boundary', { width: 640, height: 500, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'regular' }],
      ['exit-after', { width: 641, height: 500, previousLayout: 'top', previousDensity: 'compact' }, { show: true, layout: 'top', density: 'regular' }],
    ],
  },
]

for (const { scenario, boundary, cases } of boundaryCases) {
  for (const [phase, params, expected] of cases) {
    assertDensityTransition(scenario, boundary, phase, params, expected)
  }
}

for (const wideScenario of scenarios.filter((scenario) =>
  ['wide-day-trend', 'wide-area-trend'].includes(scenario.name)
)) {
  for (const [phase, height, layout] of [
    ['enter', 499, 'side'],
    ['keep', 500, 'side'],
    ['exit', 501, 'top'],
  ]) {
    assertDensityTransition(
      wideScenario,
      `${wideScenario.name}-aspect-ratio`,
      phase,
      { width: 1100, height, previousLayout: 'top', previousDensity: 'compact' },
      { show: true, layout }
    )
  }
}

for (const scenario of scenarios) {
  for (const width of frameWidths) {
    for (const height of frameHeights) {
      for (const controlsBlock of [0, 30, 36, 66]) {
        const frame = resolveCanonicalInsightFrame(geometryForFrame(width, height, controlsBlock))
        assert.ok(frame, `${scenario.name} 应生成正规范化尺寸`)
        assert.deepEqual(frame, { width, height })
        for (const history of initialHistories) {
          assertConverges(scenario, frame, history)
        }
      }
    }
  }
}

for (const boundary of requiredHysteresisBoundaries) {
  assert.ok(
    exercisedHysteresisBoundaries.has(boundary),
    `稳定性扫描必须覆盖 ${boundary} 的进入、保持与退出边界`
  )
}
assert.deepEqual(
  [...exercisedBoundarySamples].sort(),
  [...requiredBoundarySamples].sort(),
  '每个迟滞调整后的进入和退出边界都必须命中 -1、精确值与 +1'
)

console.log('insight frame stability tests passed')
