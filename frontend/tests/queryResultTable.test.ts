import assert from 'node:assert/strict'
import test from 'node:test'
import { needsQueryResultTable, restoreQueryResultTable } from '../src/views/chat/answer/queryResultTable.ts'

test('历史趋势图失败记录加载数据后显示全部原始列，不替换空日期', () => {
  const record: any = {
    analysis_notice: { reason: 'chart_dimension_unavailable' }, analysis: '请调整维度',
    data: { fields: ['日期', '金额'], data: [{ 日期: null, 金额: 56 }] },
  }
  assert.equal(needsQueryResultTable(record), true)
  restoreQueryResultTable(record)
  assert.deepEqual(JSON.parse(record.chart), {
    type: 'table', title: '查询结果', columns: [{ value: '日期' }, { value: '金额' }],
  })
  assert.deepEqual(record.data.data, [{ 日期: null, 金额: 56 }])
  assert.equal(record.analysis_notice, undefined)
  assert.equal(record.analysis, '')
})

test('没有加载数据时保留恢复条件；权限失败时不生成结果表', () => {
  const record: any = { analysis_notice: { reason: 'chart_dimension_unavailable' } }
  restoreQueryResultTable(record)
  assert.equal(record.chart, undefined)
  assert.equal(needsQueryResultTable(record), true)
  record.data = { status: 'failed', error_type: 'permission_denied', fields: ['金额'], data: [{ 金额: 56 }] }
  restoreQueryResultTable(record)
  assert.equal(record.chart, undefined)
})

test('不覆盖已有图表，也不改变其它提示', () => {
  const record: any = { chart: '{"type":"line"}', analysis_notice: { reason: 'chart_dimension_unavailable' }, data: { fields: ['金额'], data: [] } }
  restoreQueryResultTable(record)
  assert.equal(record.chart, '{"type":"line"}')
  const other: any = { analysis_notice: { reason: 'missing_event' }, data: record.data }
  restoreQueryResultTable(other)
  assert.equal(other.chart, undefined)
  assert.equal(other.analysis_notice.reason, 'missing_event')
})

test('终态恢复重复带回旧提示时保留表格并清除旧提示', () => {
  const record: any = { analysis_notice: { reason: 'chart_dimension_unavailable' },
    data: JSON.stringify({ fields: ['日期', '金额'], data: [{ 日期: null, 金额: 0 }] }) }
  restoreQueryResultTable(record)
  const chart = record.chart
  Object.assign(record, { analysis: '旧提示', analysis_notice: { reason: 'chart_dimension_unavailable' } })
  restoreQueryResultTable(record)
  assert.equal(record.chart, chart)
  assert.equal(record.analysis_notice, undefined)
  assert.equal(record.analysis, '')
})
