import assert from 'node:assert/strict'
import { resolveDashboardCardInsightDisplay, resolveInsightDisplay } from './chartInsight.ts'
import { createTabInsightLayoutState, transitionTabInsightLayout } from '../../dashboard/components/sq-view/tabInsightLayout.ts'

const base = {
  data: [{ date: '2026-09-26', value: 6 }, { date: '2026-09-27', value: 11 }],
  x: [{ value: 'date' }], y: [{ value: 'value' }], series: [],
}
for (const chartType of ['line', 'area']) {
  for (const [width, height] of [[340, 250], [680, 330], [1102, 270], [1400, 400]]) {
    for (const previousLayout of ['top', 'side']) {
      const display = resolveDashboardCardInsightDisplay({ ...base, chartType, width, height, previousLayout })
      assert.equal(display.layout, 'top', '卡片趋势摘要不应因尺寸和历史切到侧边')
      assert.equal(display.featuredSide, false)
    }
  }
  const result = transitionTabInsightLayout(createTabInsightLayoutState(), {
    ...base, chartType, viewId: 'card', frame: { width: 1400, height: 400 }, controlsVariant: 'date',
  })
  assert.equal(result.display.layout, 'top', 'Tab 内的趋势卡片应使用同一顶部摘要策略')
}
const flow = resolveDashboardCardInsightDisplay({ ...base, chartType: 'sankey', width: 1000, height: 500 })
assert.equal(flow.layout, 'side', '关系图的结构布局仍可使用侧边摘要')

const reusedOutsideDashboard = { ...base, chartType: 'line', width: 1400, height: 400, dashboard: false }
assert.deepEqual(
  resolveDashboardCardInsightDisplay(reusedOutsideDashboard),
  resolveInsightDisplay(reusedOutsideDashboard),
  '复用为非看板预览时应保留调用方明确的展示上下文'
)

console.log('dashboard card layout policy passed')
