import assert from 'node:assert/strict'

import {
  DASHBOARD_DATE_FILTER_MIGRATION_REQUIRED,
  normalizeDashboardChartConfig,
} from './dashboardChartConfig.ts'

const expression = {
  mode: 'relative',
  start: { amount: 13, unit: 'day' },
  end: { amount: 1, unit: 'day' },
}
const tokenSql = `select * from orders
where stat_date between {{dashboard_start_date}} and {{dashboard_end_date}}`
const startOnlySql = 'select * from orders where stat_date >= {{dashboard_start_date}}'
const endOnlySql = 'select * from orders where stat_date <= {{dashboard_end_date}}'

const v2 = normalizeDashboardChartConfig({
  sql: tokenSql,
  configVersion: 2,
  dateFilter: {
    enabled: true,
    parameterType: 'date',
    expression,
  },
  pivot: {
    enabled: true,
    time_field: 'stat_date',
    date_parameter_type: 'date',
    date_expression: expression,
  },
})
assert.equal(v2.configVersion, 2)
assert.deepEqual(v2.dateFilter, {
  enabled: true,
  parameterType: 'date',
  expression,
})
assert.deepEqual(v2.pivot, {
  enabled: true,
  time_field: 'stat_date',
})

const pivotDisabled = normalizeDashboardChartConfig({
  sql: tokenSql,
  configVersion: 2,
  dateFilter: {
    enabled: true,
    parameterType: 'date',
    expression,
  },
  pivot: {
    enabled: false,
    time_field: 'stat_date',
  },
})
assert.equal(pivotDisabled.pivot.enabled, false)
assert.deepEqual(pivotDisabled.dateFilter, {
  enabled: true,
  parameterType: 'date',
  expression,
})

const legacy = normalizeDashboardChartConfig({
  sql: tokenSql,
  pivot: {
    enabled: true,
    time_field: 'stat_date',
    date_parameter_type: 'date',
    date_expression: expression,
  },
})
assert.equal(legacy.configVersion, 2)
assert.deepEqual(legacy.dateFilter, {
  enabled: true,
  parameterType: 'date',
  expression,
})
assert.deepEqual(legacy.pivot, {
  enabled: true,
  time_field: 'stat_date',
})

const legacyPivotDisabled = normalizeDashboardChartConfig({
  sql: tokenSql,
  pivot: {
    enabled: false,
    time_field: 'stat_date',
    date_parameter_type: 'date',
    date_expression: expression,
  },
})
assert.deepEqual(legacyPivotDisabled.dateFilter, {
  enabled: true,
  parameterType: 'date',
  expression,
})
assert.deepEqual(legacyPivotDisabled.pivot, {
  enabled: false,
  time_field: 'stat_date',
})

const endOnly = normalizeDashboardChartConfig({
  sql: endOnlySql,
  configVersion: 2,
  dateFilter: {
    enabled: true,
    parameterType: 'date',
    expression,
  },
  pivot: { enabled: false },
})
assert.equal(endOnly.dateFilter.parameterType, 'date')

const startOnly = normalizeDashboardChartConfig({
  sql: startOnlySql,
  configVersion: 2,
  dateFilter: {
    enabled: true,
    parameterType: 'date',
    expression,
  },
  pivot: { enabled: false },
})
assert.equal(startOnly.dateFilter.parameterType, 'date')

assert.throws(
  () => normalizeDashboardChartConfig({
    sql: tokenSql,
    configVersion: 2,
    dateFilter: { enabled: false, parameterType: 'date', expression },
    pivot: { enabled: false },
  }),
  (error) => error?.message === DASHBOARD_DATE_FILTER_MIGRATION_REQUIRED
)

for (const pivot of [
  { enabled: true, date_parameter_type: 'date' },
  { enabled: true, date_expression: expression },
  { enabled: true, date_parameter_type: 'timestamp', date_expression: expression },
]) {
  assert.throws(
    () => normalizeDashboardChartConfig({ sql: tokenSql, pivot }),
    (error) => error?.message === DASHBOARD_DATE_FILTER_MIGRATION_REQUIRED
  )
}
