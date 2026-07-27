import assert from 'node:assert/strict'

import {
  applyDashboardDateFilterCapability,
  beginDashboardChartRequest,
  beginDashboardDateApply,
  buildAppliedDashboardDatePivot,
  buildDashboardDatePivot,
  buildDashboardDateSourcePreviewPivot,
  canShowDashboardDateFilter,
  commitDashboardDateRange,
  createDashboardDateFilterState,
  dashboardDateFilterContext,
  defaultDashboardDateRange,
  failDashboardDateRange,
  finishDashboardChartRequest,
  isDashboardDateApplyDisabled,
  isDashboardChartRequestCurrent,
  getOrCreateDashboardDateFilterState,
  registerDashboardDateFilterState,
  scanDashboardDateParameterTokens,
  shouldInitializeDashboardDateFilterState,
  shouldResetDashboardDateFilterState,
} from './dashboardDateFilter.ts'

const requestViewInfo = {}
const firstRequestVersion = beginDashboardChartRequest(requestViewInfo)
assert.equal(beginDashboardChartRequest(requestViewInfo, 'background'), null)
finishDashboardChartRequest(requestViewInfo, firstRequestVersion)
const backgroundRequestVersion = beginDashboardChartRequest(requestViewInfo, 'background')
assert.equal(backgroundRequestVersion, firstRequestVersion)
const secondRequestVersion = beginDashboardChartRequest(requestViewInfo)
assert.equal(isDashboardChartRequestCurrent(requestViewInfo, firstRequestVersion), false)
assert.equal(isDashboardChartRequestCurrent(requestViewInfo, secondRequestVersion), true)
assert.equal(isDashboardChartRequestCurrent({}, secondRequestVersion), false)
finishDashboardChartRequest(requestViewInfo, secondRequestVersion)

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

assert.deepEqual(
  buildDashboardDateSourcePreviewPivot({
    enabled: true,
    time_field: 'dt',
    range_enabled: true,
    range: 'source',
    date_parameter_type: 'date',
    metric_fields: ['amount'],
  }),
  {
    enabled: false,
    time_field: 'dt',
    range_enabled: true,
    range: 'source',
    date_parameter_type: 'date',
    metric_fields: ['amount'],
  }
)

replacementState.appliedRange = ['2026-05-01', '2026-05-14']
viewInfo.dateFilterCapability = capability
assert.deepEqual(
  buildAppliedDashboardDatePivot(
    viewInfo,
    { enabled: true, time_field: 'dt', date_parameter_type: 'date', range: 'source' }
  ),
  {
    enabled: true,
    time_field: 'dt',
    date_parameter_type: 'date',
    range: 'custom',
    custom_start: '2026-05-01',
    custom_end: '2026-05-14',
  }
)

assert.deepEqual(
  scanDashboardDateParameterTokens(
    `select $$ {{dashboard_start_timestamp}} $$ as note, dt from orders
     where dt between {{dashboard_start_date}} and {{dashboard_end_date}}
     -- {{dashboard_start_yyyymmdd}}
     /* {{dashboard_end_yyyymmdd}} */`
  ),
  ['{{dashboard_start_date}}', '{{dashboard_end_date}}']
)

const previousContext = dashboardDateFilterContext(
  { id: 'chart-1', sql: 'select 1' },
  { status: 'available', defaultStart: '2026-07-13', defaultEnd: '2026-07-26' }
)
const nextDefaultContext = dashboardDateFilterContext(
  { id: 'chart-1', sql: 'select 1' },
  { status: 'available', defaultStart: '2026-07-14', defaultEnd: '2026-07-27' }
)
assert.equal(shouldInitializeDashboardDateFilterState(previousContext, nextDefaultContext), false)
assert.equal(
  shouldInitializeDashboardDateFilterState(
    dashboardDateFilterContext({ id: 'chart-1', sql: 'select 1' }, { status: 'forbidden' }),
    nextDefaultContext
  ),
  true
)
assert.equal(shouldResetDashboardDateFilterState(previousContext, nextDefaultContext, true), false)
assert.equal(
  shouldResetDashboardDateFilterState(
    previousContext,
    dashboardDateFilterContext({ id: 'chart-1', sql: 'select 2' }, { status: 'available' }),
    true
  ),
  true
)
assert.equal(
  shouldResetDashboardDateFilterState(
    previousContext,
    dashboardDateFilterContext({ id: 'chart-2', sql: 'select 1' }, { status: 'available' }),
    false
  ),
  false
)

applyDashboardDateFilterCapability(viewInfo, {
  date_filter_capability: {
    ...capability,
    defaultStart: '2026-07-14',
    defaultEnd: '2026-07-27',
    maxEnd: '2026-07-27',
  },
})
assert.equal(viewInfo.dateFilterCapability.defaultEnd, '2026-07-27')
assert.deepEqual(getOrCreateDashboardDateFilterState(viewInfo, viewInfo.dateFilterCapability).appliedRange, [
  '2026-05-01',
  '2026-05-14',
])
assert.equal(
  shouldInitializeDashboardDateFilterState(
    previousContext,
    dashboardDateFilterContext({ id: 'chart-2', sql: 'select 1' }, { status: 'available' })
  ),
  true
)
