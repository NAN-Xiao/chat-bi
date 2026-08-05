import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

test('pie and donut use the shared radial partition renderer', () => {
  const base = readFileSync('src/views/chat/component/charts/RadialPartitionChart.ts', 'utf8')
  const pie = readFileSync('src/views/chat/component/charts/Pie.ts', 'utf8')
  const donut = readFileSync('src/views/chat/component/charts/Donut.ts', 'utf8')

  assert.match(base, /export class RadialPartitionChart extends BaseG2Chart/)
  assert.match(base, /prepareRadialSlices/)
  assert.match(base, /innerRadius/)
  assert.match(base, /RADIAL_PERCENTAGE_FIELD/)
  assert.match(pie, /extends RadialPartitionChart/)
  assert.match(pie, /name: 'pie'/)
  assert.match(pie, /innerRadius: 0/)
  assert.match(donut, /extends RadialPartitionChart/)
  assert.match(donut, /name: 'donut'/)
  assert.match(donut, /innerRadius: 0\.55/)
  assert.match(donut, /showPercentage: true/)
})
