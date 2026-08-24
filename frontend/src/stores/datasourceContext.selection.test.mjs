import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import assert from 'node:assert/strict'

const source = readFileSync(
  fileURLToPath(new URL('./datasourceContext.ts', import.meta.url)),
  'utf8'
)

test('the sole datasource returned for a workspace becomes its active datasource', () => {
  const selectionBranch = source.slice(
    source.indexOf('const currentDatasource ='),
    source.indexOf('if (datasource) {')
  )
  assert.match(selectionBranch, /this\.datasources\.length === 1 \? this\.datasources\[0\]/)
})

test('an absent selection does not discard the loaded workspace datasource list', () => {
  const selectionBranch = source.slice(
    source.indexOf('if (datasource) {'),
    source.indexOf('this.tenantScopeId = requestTenantId')
  )
  assert.match(selectionBranch, /this\.clearDatasourceSelection\(\)/)
  assert.doesNotMatch(selectionBranch, /this\.clear\(false\)/)
})

test('clearing a selection preserves the loaded workspace state', () => {
  const clearSelection = source.slice(
    source.indexOf('clearDatasourceSelection()'),
    source.indexOf('async activateDatasourceById')
  )
  assert.match(clearSelection, /this\.datasourceId = undefined/)
  assert.doesNotMatch(clearSelection, /this\.datasources = \[\]/)
  assert.doesNotMatch(clearSelection, /this\.initialized = false/)
})
