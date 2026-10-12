import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as dates from './dashboardDateFilter.ts'

const week = { version: 1, mode: 'preset', preset: 'past_7_days' }
const month = { version: 1, mode: 'preset', preset: 'past_30_days' }
function view() {
  return {
    id: 'chart-a', sql: 'SELECT dt FROM facts', datasource: 7,
    dateFilter: { enabled: true, parameterType: 'yyyymmdd_number', expression: week },
    dateFilterCapability: { status: 'available', parameterType: 'yyyymmdd_number',
      expression: week, resolvedStart: '2026-10-05', resolvedEnd: '2026-10-11' },
    pivot: { date_expression: week, range: 'custom', custom_start: '2026-10-05', custom_end: '2026-10-11' },
    sourceConfig: { sql: { builder: { timeRange: 'expression', timeExpression: week, timeCustomRange: [] } } },
    data: { fields: ['dt'], data: [{ dt: '2026-10-05' }] }, fields: ['dt'],
    status: 'success', dataState: 'ready', snapshotRefreshedAt: 123,
  }
}
async function implementation() {
  const module = await import('./dashboardDateFilterPersistence.ts').catch(() => ({}))
  assert.equal(typeof module.applyDashboardDateExpressionTransaction, 'function',
    'Date application must refresh and persist before committing the selected expression')
  return module.applyDashboardDateExpressionTransaction
}
function refreshed(v) {
  v.data.data = [{ dt: '2026-09-12' }, { dt: '2026-10-11' }]
  v.dateFilterCapability = { ...v.dateFilterCapability, expression: month,
    resolvedStart: '2026-09-12', resolvedEnd: '2026-10-11' }
}

test('preset refresh requests do not turn the old resolved range into an override', () => {
  const v = view()
  dates.getOrCreateDashboardDateFilterState(v, v.dateFilterCapability)
  v.dateFilter.expression = month
  assert.equal(typeof dates.buildDashboardDateFilterRequestForRefresh, 'function')
  const request = dates.buildDashboardDateFilterRequestForRefresh(v)
  assert.deepEqual(request.expression, month)
  assert.equal(request.custom_start, '')
  assert.equal(request.custom_end, '')
})

test('successful date application saves only the chart date and survives reopening', async () => {
  const apply = await implementation()
  const v = view()
  const saved = []
  v.data.source_data = [{ dt: '2026-10-05' }]
  v.data.source_fields = ['dt']
  const success = await apply(v, month, {
    refresh: async (request) => {
      assert.deepEqual(request.expression, month)
      assert.equal(request.custom_start, '')
      refreshed(v)
      return true
    },
    persist: async (payload) => { saved.push(payload) },
  })
  assert.equal(success, true)
  assert.equal(saved.length, 1)
  assert.equal(saved[0].chart_id, 'chart-a')
  assert.equal(saved[0].expected_sql, v.sql)
  assert.equal(saved[0].expected_datasource, 7)
  assert.deepEqual(saved[0].date_filter.expression, month)
  assert.deepEqual(v.dateFilter.expression, month)
  assert.deepEqual(v.sourceConfig.sql.builder.timeExpression, month)
  assert.deepEqual(v.pivot.date_expression, month)
  assert.equal(v.pivot.range, 'source')
  assert.equal(v.pivot.custom_start, '')
  assert.equal(v.data.source_data, undefined)
  assert.equal(v.data.source_fields, undefined)
  const state = dates.getOrCreateDashboardDateFilterState(v, v.dateFilterCapability)
  assert.deepEqual(state.appliedRange, ['2026-09-12', '2026-10-11'])
  assert.deepEqual(state.draftRange, state.appliedRange)
  const reopened = JSON.parse(JSON.stringify(v))
  assert.deepEqual(dates.buildDashboardDateFilterRequestForRefresh(reopened).expression, month)
  assert.equal(dates.buildDashboardDateFilterRequestForRefresh(reopened).custom_start, '')
})

test('failed query never saves or commits a different date or result', async () => {
  const apply = await implementation()
  const v = view()
  const before = JSON.parse(JSON.stringify(v))
  let saves = 0
  assert.equal(await apply(v, month, {
    refresh: async () => { refreshed(v); return false },
    persist: async () => { saves++ },
  }), false)
  assert.equal(saves, 0)
  assert.deepEqual(v.dateFilter, before.dateFilter)
  assert.deepEqual(v.data, before.data)
  assert.deepEqual(v.dateFilterCapability, before.dateFilterCapability)
})

test('save rejection rolls back the label, results and resolved range together', async () => {
  const apply = await implementation()
  const v = view()
  const before = JSON.parse(JSON.stringify(v))
  await assert.rejects(apply(v, month, {
    refresh: async () => { refreshed(v); return true },
    persist: async () => { throw new Error('日期未保存') },
  }), /日期未保存/)
  assert.deepEqual(v.dateFilter, before.dateFilter)
  assert.deepEqual(v.data, before.data)
  assert.deepEqual(v.dateFilterCapability, before.dateFilterCapability)
  assert.equal(dates.getOrCreateDashboardDateFilterState(v, v.dateFilterCapability).applying, false)
})

test('background refresh cannot query the old range while the new date is saving', async () => {
  const apply = await implementation()
  const v = view()
  let finishSave
  let saving
  const reachedSave = new Promise(resolve => { saving = resolve })
  const result = apply(v, month, {
    refresh: async () => { refreshed(v); return true },
    persist: async () => { saving(); await new Promise(resolve => { finishSave = resolve }) },
  })
  await reachedSave
  assert.equal(dates.beginDashboardChartRequest(v, 'background'), null)
  assert.equal(dates.getOrCreateDashboardDateFilterState(v, v.dateFilterCapability).applying, true)
  finishSave()
  await result
  assert.notEqual(dates.beginDashboardChartRequest(v, 'background'), null)
})

test('a stale successful response for a different expression cannot be saved', async () => {
  const apply = await implementation()
  const v = view()
  let saves = 0
  await assert.rejects(apply(v, month, {
    refresh: async () => true,
    persist: async () => { saves++ },
  }), /日期范围|日期表达式/)
  assert.equal(saves, 0)
  assert.deepEqual(v.dateFilter.expression, week)
})
