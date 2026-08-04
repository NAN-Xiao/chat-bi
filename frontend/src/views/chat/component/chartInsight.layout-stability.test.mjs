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

assert.equal(
  resolveInsightDisplay({ ...trend, width: 520, height: 359 }).show,
  false,
  '看板顶部摘要首次测量低于可读高度时应隐藏，避免挤占图表'
)
assert.equal(
  resolveInsightDisplay({ ...trend, width: 520, height: 368, previousShow: false }).show,
  false,
  '摘要隐藏后高度小幅回升仍应保持隐藏，不能在临界尺寸反复出现'
)
assert.equal(
  resolveInsightDisplay({ ...trend, width: 520, height: 432, previousShow: false }).show,
  true,
  '摘要隐藏后高度明确恢复到 mini 可读区间才重新显示'
)
assert.equal(
  resolveInsightDisplay({ ...trend, width: 520, height: 368, previousShow: true }).show,
  true,
  '已显示摘要时高度仍在可读下界上方应保持显示，避免轻微抖动导致消失'
)
assert.equal(
  resolveInsightDisplay({ ...trend, width: 520, height: 352, previousShow: true }).show,
  false,
  '已显示摘要跌破可读下界后应隐藏'
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
