import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync('src/views/dashboard/common/DashboardSqlEditor.vue', 'utf8')

test('passes path step metadata to the sankey preview', () => {
  assert.match(
    source,
    /const chartPreviewColumns = computed\(\(\) => \{[\s\S]*?form\.chartType === 'sankey' \? form\.columns : \[\]/
  )
  assert.match(source, /:columns="toAxes\(chartPreviewColumns\)"/)
})

test('persists path step metadata in the saved sankey chart', () => {
  assert.match(
    source,
    /if \(form\.chartType === 'sankey'\) \{\s*chart\.columns = toAxes\(form\.columns\)\s*\}/
  )
})

console.log('Dashboard SQL editor path sankey tests passed')
