import assert from 'node:assert/strict'
import { test } from 'node:test'

async function implementation() {
  const module = await import('./dashboardChartSnapshot.ts').catch(() => ({}))
  assert.equal(typeof module.queryDashboardChartWithPersistence, 'function')
  return module
}

test('manual refresh queries and saves once through its owning dashboard', async () => {
  const { queryDashboardChartWithPersistence: query } = await implementation()
  const calls = []
  const result = await query({ datasource: 7, sql: 'SELECT 1' }, true,
    async () => { throw new Error('must use saved refresh') },
    async payload => { calls.push(payload); return { status: 'success', data: [{ value: 1 }], snapshot_saved: true } },
    'chart-a')
  assert.equal(calls.length, 1)
  assert.equal(calls[0].chart_id, 'chart-a')
  assert.equal(result.snapshot_saved, true)
})

test('background queries and unsaved editor previews preserve the existing query flow', async () => {
  const { queryDashboardChartWithPersistence: query } = await implementation()
  let previews = 0
  const preview = async () => { previews++; return { status: 'success' } }
  await query({ sql: 'SELECT 1' }, false, preview, async () => { throw new Error('must not save') }, 'a')
  await query({ sql: 'SELECT 1' }, true, preview, undefined, 'draft')
  assert.equal(previews, 2)
})

test('date application is included in the same server refresh and save operation', async () => {
  const { queryDashboardChartWithPersistence: query } = await implementation()
  const dates = { parameter_type: 'yyyymmdd_number', expression: { version: 1, mode: 'preset', preset: 'past_30_days' } }
  await query({ date_filter: dates }, true, async () => assert.fail(), async payload => {
    assert.deepEqual(payload.date_filter, dates)
    assert.equal(payload.apply_date_filter, true)
    return { status: 'success', snapshot_saved: true }
  }, 'a', true)
})

test('a successful refresh without a confirmed save is reported as a failure', async () => {
  const { queryDashboardChartWithPersistence: query } = await implementation()
  await assert.rejects(query({}, true, async () => assert.fail(), async () => ({ status: 'success' }), 'a'), /未保存/)
})

test('saved empty results are restored but unvalidated and failed results are not', async () => {
  const { hasSavedDashboardChartSnapshot: hasSaved } = await implementation()
  const saved = { snapshotContext: { version: 1, fingerprint: 'server-verified' },
    status: 'success', dataState: 'ready', data: { data: [] } }
  assert.equal(hasSaved(saved), true)
  assert.equal(hasSaved({ ...saved, status: 'failed' }), false)
  assert.equal(hasSaved({ ...saved, snapshotContext: undefined }), false)
})

test('a saved refresh replaces old source rows used by the chart renderer', async () => {
  const { applySavedDashboardSnapshotMetadata: apply } = await implementation()
  assert.equal(typeof apply, 'function')
  const view = { data: { data: [{ value: 2 }], source_data: [{ value: 1 }], source_fields: ['value'] } }
  const context = { version: 1, fingerprint: 'latest' }
  apply(view, { snapshot_saved: true, snapshot_context: context })
  assert.deepEqual(view.data.data, [{ value: 2 }])
  assert.equal(view.data.source_data, undefined)
  assert.equal(view.data.source_fields, undefined)
  assert.deepEqual(view.snapshotContext, context)
})
