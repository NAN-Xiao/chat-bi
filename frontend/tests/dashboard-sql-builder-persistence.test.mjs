import assert from 'node:assert/strict'
import esbuild from 'esbuild'

const build = await esbuild.build({
  entryPoints: ['src/views/dashboard/common/formulaMetricUtils.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})

const bundledSource = build.outputFiles[0].text
const moduleUrl = `data:text/javascript;base64,${Buffer.from(bundledSource).toString('base64')}`
const { normalizeFormulaAtomicMetricDisplay, normalizeFormulaTokens } = await import(moduleUrl)

const tokens = normalizeFormulaTokens([
  {
    type: 'atomicMetric',
    metric: {
      id: 'metric-1',
      field: 'event.recharge',
      metric: 'event.amount',
      aggregation: 'sum',
      alias: 'recharge_amount',
      label: '后端充值',
      filterLogic: 'or',
      filters: [
        {
          id: 'filter-1',
          type: 'rule',
          field: 'event.channel',
          operator: 'eq',
          value: 'ios',
          logic: 'or',
          extra: 'drop-me',
        },
        {
          id: 'empty-rule',
          type: 'rule',
          field: '',
          operator: 'eq',
          value: '',
        },
        {
          id: 'group-1',
          type: 'group',
          field: '',
          operator: '',
          value: '',
          logic: 'or',
          children: [
            {
              id: 'filter-2',
              field: 'event.country',
              operator: 'in',
              value: 'US',
              logic: 'and',
              transient: true,
            },
          ],
        },
      ],
    },
  },
])

assert.deepEqual(tokens, [
  {
    type: 'atomicMetric',
    metric: {
      id: 'metric-1',
      field: 'event.recharge',
      metric: 'event.amount',
      aggregation: 'sum',
      alias: 'recharge_amount',
      label: '后端充值',
      filterLogic: 'or',
      filters: [
        {
          id: 'filter-1',
          type: 'rule',
          field: 'event.channel',
          operator: 'eq',
          value: 'ios',
          logic: 'or',
        },
        {
          id: 'group-1',
          type: 'group',
          field: '',
          operator: '',
          value: '',
          logic: 'or',
          children: [
            {
              id: 'filter-2',
              type: 'rule',
              field: 'event.country',
              operator: 'in',
              value: 'US',
              logic: 'and',
            },
          ],
        },
      ],
    },
  },
])

const restoredMetric = normalizeFormulaAtomicMetricDisplay(
  {
    id: 'metric-2',
    field: 'tracking-event:event.event:ServerPayLog',
    metric: 'tracking-property:event.event:ServerPayLog:personal.money',
    aggregation: 'sum',
    alias: 'GVG副本阶段战斗结果统计_总次数',
    label: 'GVG副本阶段战斗结果统计.总次数',
    filterLogic: 'and',
    filters: [],
  },
  {
    label: '后端充值.求和',
    alias: '后端充值_求和',
  }
)

assert.equal(restoredMetric.label, '后端充值.求和')
assert.equal(restoredMetric.alias, '后端充值_求和')

console.log('dashboard sql builder persistence tests passed')
