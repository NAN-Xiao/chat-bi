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
