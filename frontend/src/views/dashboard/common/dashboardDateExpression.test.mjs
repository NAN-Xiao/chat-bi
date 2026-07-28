import assert from 'node:assert/strict'
import esbuild from 'esbuild'

const build = await esbuild.build({
  entryPoints: ['src/views/dashboard/common/dashboardDateExpression.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const {
  ALL_TIME_END,
  ALL_TIME_START,
  buildDashboardDateExpressionPivot,
  cloneDashboardDateExpression,
  formatDashboardDateExpression,
  normalizeDashboardDateExpression,
  resolveDashboardDateExpression,
  validateDashboardDateExpression,
} = await import(moduleUrl)

const now = '2026-07-28T12:00:00+08:00'
const expected = new Map([
  ['yesterday', ['2026-07-27', '2026-07-27']],
  ['today', ['2026-07-28', '2026-07-28']],
  ['previous_week', ['2026-07-20', '2026-07-26']],
  ['current_week', ['2026-07-27', '2026-07-28']],
  ['previous_month', ['2026-06-01', '2026-06-30']],
  ['current_month', ['2026-07-01', '2026-07-28']],
  ['past_7_days', ['2026-07-21', '2026-07-27']],
  ['recent_7_days', ['2026-07-22', '2026-07-28']],
  ['past_30_days', ['2026-06-28', '2026-07-27']],
  ['recent_30_days', ['2026-06-29', '2026-07-28']],
  ['past_90_days', ['2026-04-29', '2026-07-27']],
  ['all_time', [ALL_TIME_START, ALL_TIME_END]],
])

for (const [preset, range] of expected) {
  assert.deepEqual(
    resolveDashboardDateExpression({ version: 1, mode: 'preset', preset }, now, 'Asia/Shanghai'),
    { start: range[0], end: range[1] }
  )
}

assert.deepEqual(
  resolveDashboardDateExpression(
    {
      version: 1,
      mode: 'range',
      start: { mode: 'static', date: '2026-01-01' },
      end: { mode: 'dynamic', unit: 'day', offset: 0 },
    },
    now,
    'Asia/Shanghai'
  ),
  { start: '2026-01-01', end: '2026-07-28' }
)

const fixedToToday = {
  version: 1,
  mode: 'range',
  start: { mode: 'static', date: '2026-01-01' },
  end: { mode: 'dynamic', unit: 'day', offset: 0 },
}
assert.equal(validateDashboardDateExpression(fixedToToday, now, 'Asia/Shanghai').valid, true)
assert.equal(formatDashboardDateExpression({ version: 1, mode: 'preset', preset: 'past_30_days' }), '过去30天')
assert.deepEqual(normalizeDashboardDateExpression(fixedToToday), fixedToToday)
assert.notEqual(cloneDashboardDateExpression(fixedToToday), fixedToToday)

for (const invalid of [
  null,
  { version: 2, mode: 'preset', preset: 'today' },
  { version: 1, mode: 'preset', preset: 'unknown' },
  {
    version: 1,
    mode: 'range',
    start: { mode: 'static', date: '2026/01/01' },
    end: { mode: 'dynamic', unit: 'day', offset: 0 },
  },
  {
    version: 1,
    mode: 'range',
    start: { mode: 'static', date: '2026-08-01' },
    end: { mode: 'static', date: '2026-07-01' },
  },
  {
    version: 1,
    mode: 'range',
    start: { mode: 'dynamic', unit: 'day', offset: 1 },
    end: { mode: 'dynamic', unit: 'day', offset: 1 },
  },
]) {
  assert.equal(validateDashboardDateExpression(invalid, now, 'Asia/Shanghai').valid, false)
}

const cloned = cloneDashboardDateExpression(fixedToToday)
cloned.start.date = '2025-01-01'
assert.equal(fixedToToday.start.date, '2026-01-01')

const cardOverride = buildDashboardDateExpressionPivot(
  {
    enabled: false,
    time_field: 'dt',
    date_parameter_type: 'yyyymmdd_number',
    range: 'custom',
    custom_start: '2026-07-01',
    custom_end: '2026-07-27',
  },
  { version: 1, mode: 'preset', preset: 'today' }
)
assert.deepEqual(cardOverride.date_expression, {
  version: 1,
  mode: 'preset',
  preset: 'today',
})
assert.equal(cardOverride.range, 'source')
assert.equal(cardOverride.custom_start, '')
assert.equal(cardOverride.custom_end, '')
assert.equal(cardOverride.time_field, 'dt')
assert.equal(cardOverride.date_parameter_type, 'yyyymmdd_number')

console.log('dashboard date expression tests passed')
