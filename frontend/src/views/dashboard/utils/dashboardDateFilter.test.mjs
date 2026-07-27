import assert from 'node:assert/strict'

import {
  beginDashboardDateApply,
  buildDashboardDatePivot,
  canShowDashboardDateFilter,
  commitDashboardDateRange,
  createDashboardDateFilterState,
  defaultDashboardDateRange,
  failDashboardDateRange,
  isDashboardDateApplyDisabled,
  getOrCreateDashboardDateFilterState,
  registerDashboardDateFilterState,
} from './dashboardDateFilter.ts'

assert.deepEqual(defaultDashboardDateRange('2026-07-27'), ['2026-07-13', '2026-07-26'])
assert.equal(canShowDashboardDateFilter({ status: 'available' }), true)
assert.equal(canShowDashboardDateFilter({ status: 'realtime' }), false)

const capability = {
  status: 'available',
  defaultStart: '2026-07-13',
  defaultEnd: '2026-07-26',
  maxEnd: '2026-07-26',
}
const state = createDashboardDateFilterState(capability, '2026-07-30')
assert.deepEqual(state.draftRange, ['2026-07-13', '2026-07-26'])
assert.notEqual(state.draftRange, state.appliedRange)
assert.equal(isDashboardDateApplyDisabled(state, capability), true)

state.draftRange = ['2026-07-01', '2026-07-14']
assert.equal(isDashboardDateApplyDisabled(state, capability), false)
assert.deepEqual(
  buildDashboardDatePivot(
    { pivot: { enabled: true, time_field: 'dt', range: 'source' } },
    state.draftRange
  ),
  {
    enabled: true,
    time_field: 'dt',
    range: 'custom',
    custom_start: '2026-07-01',
    custom_end: '2026-07-14',
  }
)

beginDashboardDateApply(state)
assert.equal(state.applying, true)
assert.deepEqual(state.pendingRange, ['2026-07-01', '2026-07-14'])
commitDashboardDateRange(state)
assert.equal(state.applying, false)
assert.deepEqual(state.appliedRange, ['2026-07-01', '2026-07-14'])

state.draftRange = ['2026-06-01', '2026-06-14']
beginDashboardDateApply(state)
failDashboardDateRange(state, '查询失败')
assert.equal(state.applying, false)
assert.equal(state.pendingRange, null)
assert.equal(state.applyError, '查询失败')
assert.deepEqual(state.appliedRange, ['2026-07-01', '2026-07-14'])
assert.deepEqual(state.draftRange, ['2026-06-01', '2026-06-14'])

for (const invalidRange of [
  ['', '2026-07-14'],
  ['2026/07/01', '2026-07-14'],
  ['2026-07-15', '2026-07-14'],
  ['2026-07-01', '2026-07-27'],
]) {
  state.draftRange = invalidRange
  assert.equal(isDashboardDateApplyDisabled(state, capability), true)
}

const viewInfo = { id: 'chart-1', pivot: {} }
const sharedState = getOrCreateDashboardDateFilterState(viewInfo, capability, '2026-07-30')
sharedState.appliedRange = ['2026-06-01', '2026-06-14']
assert.equal(getOrCreateDashboardDateFilterState(viewInfo, capability), sharedState)

const replacementState = createDashboardDateFilterState(capability, '2026-07-30')
registerDashboardDateFilterState(viewInfo, replacementState)
assert.equal(getOrCreateDashboardDateFilterState(viewInfo, capability), replacementState)
