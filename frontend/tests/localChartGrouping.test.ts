import assert from 'node:assert/strict'
import test from 'node:test'
import { regroupLocalChartData, resolveLocalTableData, type LocalGroupingPlan } from '../src/views/chat/component/charts/localChartGrouping.ts'
import { normalizeTableFilterValue } from '../src/views/chat/component/charts/tableFilter.ts'

const plan: LocalGroupingPlan = {
  dimensions: ['day', 'region'],
  metrics: {
    value: { kind: 'aggregate', aggregation: 'sum' },
    units: { kind: 'aggregate', aggregation: 'sum' },
    price: { kind: 'formula', expression: { op: 'divide', args: [{ field: 'value' }, { field: 'units' }] } },
    people: { kind: 'unavailable', reason: '缺少去重明细' },
  },
  summary: { field: 'day', value: 'total' },
}
const rows = [
  { day: 'total', region: null, value: 160, units: 14, price: 11.43, people: 3 },
  { day: '2026-09-01', region: 'A', value: 10, units: 1, price: 10, people: 1 },
  { day: '2026-09-01', region: 'B', value: 90, units: 9, price: 10, people: 1 },
  { day: '2026-09-02', region: null, value: 20, units: 2, price: 10, people: 1 },
  { day: '2026-09-02', region: 'B', value: 40, units: 2, price: 20, people: 1 },
]

test('取消维度分组保留日期，合计基础指标并按合计分子分母计算', () => {
  const result = regroupLocalChartData(rows, plan, new Set(['region']))
  assert.deepEqual(result.data.map(({ day, value, price }) => ({ day, value, price })), [
    { day: 'total', value: 160, price: 160 / 14 },
    { day: '2026-09-01', value: 100, price: 10 },
    { day: '2026-09-02', value: 60, price: 15 },
  ])
  assert.ok(result.data.every((row) => row.region === null))
  assert.ok(result.data.every((row) => row.people === null))
  assert.match(result.issues.people, /去重/)
})

test('清除不分组状态恢复原始数据，且不改写原数组', () => {
  const snapshot = structuredClone(rows)
  assert.deepEqual(regroupLocalChartData(rows, plan, new Set()).data, rows)
  regroupLocalChartData(rows, plan, new Set(['region']))
  assert.deepEqual(rows, snapshot)
})

test('原有汇总行不重复参与合计，取消所有分组只得到一行', () => {
  const result = regroupLocalChartData(rows, plan, new Set(['day', 'region']))
  assert.equal(result.data.length, 1)
  assert.equal(result.data[0].value, 160)
})

test('零分母保持空值，不以原比率平均兜底', () => {
  const result = regroupLocalChartData([{ day: 'a', region: 'x', value: 2, units: 0, price: 9 }], plan, new Set(['region']))
  assert.equal(result.data[0].price, null)
})

test('缺字段或非数值明确提示，不能只合计剩下的有效值', () => {
  const result = regroupLocalChartData([{ day: 'a', region: 'x', value: 1, units: 'bad' }, { day: 'a', region: 'y', units: 1 }], plan, new Set(['region']))
  assert.equal(result.data[0].value, null)
  assert.equal(result.data[0].units, null)
  assert.match(result.issues.value, /缺少/)
  assert.match(result.issues.units, /数值/)
  assert.equal(result.data[0].price, null)
})

test('保留其余维度以及值类型，不能把数值1和字符串1合为同一组', () => {
  const multi = { ...plan, dimensions: ['day', 'category', 'region'], summary: undefined }
  const result = regroupLocalChartData([
    { day: 'a', category: 1, region: 'x', value: 1, units: 1 },
    { day: 'a', category: '1', region: 'y', value: 2, units: 1 },
  ], multi, new Set(['region']))
  assert.equal(result.data.length, 2)
})

test('不把未配置的字段或已有去重数推断为可加指标', () => {
  const unknown = { ...plan, metrics: { ...plan.metrics, mystery: { kind: 'unavailable' as const, reason: '缺少聚合配置' } } }
  const result = regroupLocalChartData(rows, unknown, new Set(['region']))
  assert.ok(result.data.every((row) => row.mystery === null))
  assert.match(result.issues.mystery, /配置/)
})

test('源数据筛选后重新生成汇总行，过滤掉的行不能混回计算', () => {
  const result = regroupLocalChartData(rows.filter((row) => row.region === 'B' || row.day === 'total'), plan, new Set(['region']))
  assert.equal(result.data[0].value, 130)
})

test('指标列筛选作用于汇总后的值，不能拿明细值筛选汇总行', () => {
  const result = resolveLocalTableData(rows, {
    plan, excludedFields: new Set(['region']),
    filters: new Map([['value', new Set([normalizeTableFilterValue(100)])]]),
  })
  assert.equal(result.data.length, 1)
  assert.equal(result.data[0].day, '2026-09-01')
  assert.equal(result.groupedData.length, 3)
})

test('十进制结果相加不显示二进制浮点尾差', () => {
  const result = regroupLocalChartData([
    { day: 'a', region: 'x', value: 0.1, units: 1 },
    { day: 'a', region: 'y', value: 0.2, units: 1 },
  ], plan, new Set(['region']))
  assert.equal(result.data[0].value, 0.3)
})

test('筛选只剩原汇总行时保留该行并明确缺少明细', () => {
  const result = regroupLocalChartData([rows[0]], plan, new Set(['region']))
  assert.equal(result.data.length, 1)
  assert.equal(result.data[0].day, 'total')
  assert.match(result.issues.value, /明细/)
})

test('缺少保留维度时明确失败，不能按undefined把所有日期合并', () => {
  assert.throws(() => regroupLocalChartData([{ region: 'A', value: 10 }], plan, new Set(['region'])), /缺少分组字段/)
})

test('公式结果越过安全精度时明确提示', () => {
  const formulaPlan: LocalGroupingPlan = { dimensions: ['day', 'region'], metrics: {
    value: { kind: 'aggregate', aggregation: 'sum' },
    result: { kind: 'formula', expression: { op: 'multiply', args: [{ field: 'value' }, { value: 3 }] } },
  } }
  const result = regroupLocalChartData([{ day: 'a', region: 'b', value: 4503599627370496 }], formulaPlan, new Set(['region']))
  assert.equal(result.data[0].result, null)
  assert.match(result.issues.result, /精度/)
})

test('舍入采用十进制半值处理，保留正负值和负精度', () => {
  const rounding: LocalGroupingPlan = { dimensions: ['day', 'region'], metrics: {
    value: { kind: 'aggregate', aggregation: 'sum' },
    result: { kind: 'formula', expression: { op: 'round', args: [{ field: 'value' }, { value: 2 }] } },
  } }
  const result = regroupLocalChartData([1.005, -1.005, 2.675].map((value, i) => ({ day: i, region: 'a', value })), rounding, new Set(['region']))
  assert.deepEqual(result.data.map((row) => row.result), [1.01, -1.01, 2.68])
})
