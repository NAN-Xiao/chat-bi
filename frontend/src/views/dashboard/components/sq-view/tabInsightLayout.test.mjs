import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const moduleUrl = new URL('./tabInsightLayout.ts', import.meta.url)
assert.equal(existsSync(fileURLToPath(moduleUrl)), true, '需要独立的 Tab 布局协调器')

const {
  createTabInsightLayoutState,
  resolveTabInsightControlsReserve,
  resolveTabInsightControlsVariant,
  transitionTabInsightLayout,
} = await import(moduleUrl.href)

assert.equal(resolveTabInsightControlsVariant({ pivot: false, date: false }), 'none')
assert.equal(resolveTabInsightControlsVariant({ pivot: true, date: false }), 'pivot')
assert.equal(resolveTabInsightControlsVariant({ pivot: false, date: true }), 'date')
assert.equal(resolveTabInsightControlsVariant({ pivot: true, date: true }), 'combined')
assert.deepEqual(
  ['none', 'pivot', 'date', 'combined'].map(resolveTabInsightControlsReserve),
  [0, 30, 36, 36]
)

const baseInput = {
  frame: { width: 620, height: 420 },
  viewId: 'chart-1',
  chartType: 'line',
  data: [
    { date: '2026-08-01', value: 10 },
    { date: '2026-08-02', value: 12 },
  ],
  x: [{ value: 'date' }],
  y: [{ value: 'value' }],
  series: [],
  insight: { enabled: true },
  controlsVariant: 'none',
}

let result = transitionTabInsightLayout(createTabInsightLayoutState(), baseInput)
assert.equal(result.processed, true)
assert.ok(result.display)

const stableState = result.state
let repeatedResolverCalls = 0
result = transitionTabInsightLayout(stableState, {
  ...baseInput,
  data: [
    { date: '2026-08-01', value: 99 },
    { date: '2026-08-02', value: 101 },
  ],
}, () => {
  repeatedResolverCalls += 1
  return stableState.display
})
assert.equal(result.processed, false, '同结构数据刷新不能重新执行布局转换')
assert.equal(result.state, stableState)
assert.equal(repeatedResolverCalls, 0)

const frameB = { ...baseInput, frame: { width: 619, height: 420 } }
const toB = transitionTabInsightLayout(stableState, frameB)
const backToA = transitionTabInsightLayout(toB.state, baseInput)
assert.equal(toB.processed, true)
assert.equal(backToA.processed, true, 'A -> B -> A 必须按连续签名重新计算')

const fiveGroups = {
  ...baseInput,
  frame: { width: 800, height: 420 },
  series: [{ value: 'group' }],
  data: ['A', 'B', 'C', 'D', 'E'].map((group) => ({ date: '2026-08-01', value: 1, group })),
}
const sixGroups = {
  ...fiveGroups,
  data: ['A', 'B', 'C', 'D', 'E', 'F'].map((group) => ({ date: '2026-08-01', value: 1, group })),
}
const fiveResult = transitionTabInsightLayout(createTabInsightLayoutState(), fiveGroups)
const sixResult = transitionTabInsightLayout(fiveResult.state, sixGroups)
assert.equal(sixResult.processed, true, 'series 从 5 组到 6 组必须产生一次结构转换')
assert.notEqual(sixResult.display?.layout, fiveResult.display?.layout)

const summaryOff = transitionTabInsightLayout(stableState, {
  ...baseInput,
  insight: { enabled: false },
})
assert.equal(summaryOff.processed, true)
assert.equal(summaryOff.display?.show, false)
assert.equal(summaryOff.display?.maxStats, 0)

for (const chartType of [
  'line',
  'area',
  'column',
  'bar',
  'pie',
  'funnel',
  'table',
  'metric',
  'sankey',
  'treemap',
]) {
  const chartResult = transitionTabInsightLayout(createTabInsightLayoutState(), {
    ...baseInput,
    chartType,
  })
  assert.equal(chartResult.processed, true, `${chartType} 应产生稳定策略`)
  assert.ok(chartResult.display)
}

const invalidFrame = transitionTabInsightLayout(stableState, {
  ...baseInput,
  frame: null,
})
assert.equal(invalidFrame.processed, false)
assert.equal(invalidFrame.state, stableState)
assert.equal(invalidFrame.display, stableState.display)
const nonPositiveFrame = transitionTabInsightLayout(stableState, {
  ...baseInput,
  frame: { width: 0, height: 420 },
})
assert.equal(nonPositiveFrame.processed, false)
assert.equal(nonPositiveFrame.state, stableState)

let failingCalls = 0
const failingResolver = () => {
  failingCalls += 1
  throw new Error('resolver failed')
}
const failed = transitionTabInsightLayout(stableState, frameB, failingResolver)
const failedAgain = transitionTabInsightLayout(failed.state, frameB, failingResolver)
assert.equal(failed.processed, false)
assert.equal(failed.state.display, stableState.display)
assert.equal(failedAgain.processed, false)
assert.equal(failingCalls, 1, '同一失败签名不得自动重试')

console.log('tab insight layout tests passed')
