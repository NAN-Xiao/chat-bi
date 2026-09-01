import assert from 'node:assert/strict'
import test from 'node:test'

import {
  shapeDistributionTableResult,
} from '../src/views/dashboard/utils/distributionTable.ts'

const countContext = {
  analysisModel: 'distribution',
  distribution: { metric: { kind: 'count' } },
}

test('次数分布按日期展开为动态次数列', () => {
  const result = shapeDistributionTableResult({
    fields: [
      'distribution_date',
      'total_entities',
      'interval_order',
      'interval_label',
      'entity_count',
      'entity_rate',
    ],
    data: [
      { distribution_date: 20260830, total_entities: 10, interval_order: 1, interval_label: '1-1', entity_count: 6, entity_rate: 60 },
      { distribution_date: 20260830, total_entities: 10, interval_order: 2, interval_label: '2', entity_count: 4, entity_rate: 40 },
      { distribution_date: 20260831, total_entities: 8, interval_order: 1, interval_label: '1', entity_count: 8, entity_rate: 100 },
    ],
  }, countContext)

  assert.deepEqual(result.fields, ['事件发生时间', '全部用户', '1次', '2次'])
  assert.deepEqual(result.data, [
    { 事件发生时间: '2026-08-30', 全部用户: 10, '1次': 6, '2次': 4 },
    { 事件发生时间: '2026-08-31', 全部用户: 8, '1次': 8, '2次': 0 },
  ])
})

test('属性聚合分布保留 SQL 返回的区间标签', () => {
  const result = shapeDistributionTableResult({
    fields: ['distribution_date', 'region', 'total_entities', 'interval_order', 'interval_label', 'entity_count'],
    data: [
      { distribution_date: '2026-08-31', region: '东区', total_entities: 12, interval_order: 2, interval_label: '100-199', entity_count: 5 },
      { distribution_date: '2026-08-31', region: '东区', total_entities: 12, interval_order: 1, interval_label: '0-99', entity_count: 7 },
    ],
  }, {
    analysisModel: 'distribution',
    distribution: { metric: { kind: 'property', aggregation: 'sum' } },
  })

  assert.deepEqual(result.fields, ['事件发生时间', 'region', '全部用户', '0-99', '100-199'])
  assert.deepEqual(result.data, [{
    事件发生时间: '2026-08-31',
    region: '东区',
    全部用户: 12,
    '0-99': 7,
    '100-199': 5,
  }])
})

test('同一日期和分组的重复区间会显式报错', () => {
  const row = {
    distribution_date: 20260831,
    total_entities: 10,
    interval_order: 1,
    interval_label: '1',
    entity_count: 5,
  }
  const result = shapeDistributionTableResult({
    fields: Object.keys(row),
    data: [row, { ...row, entity_count: 6 }],
  }, countContext)

  assert.equal(result.status, 'failed')
  assert.match(result.message, /出现多条记录/)
})
