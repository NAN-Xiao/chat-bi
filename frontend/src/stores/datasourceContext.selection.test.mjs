import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import assert from 'node:assert/strict'

const source = readFileSync(fileURLToPath(new URL('./datasourceContext.ts', import.meta.url)), 'utf8')

test('loading an unselected datasource list does not clear the loaded list', () => {
  const selectionBranch = source.slice(
    source.indexOf('if (datasource) {'),
    source.indexOf('this.tenantScopeId = requestTenantId')
  )
  assert.match(selectionBranch, /this\.clearDatasourceSelection\(\)/)
  assert.doesNotMatch(selectionBranch, /this\.clear\(false\)/)
})

test('clearing a datasource selection preserves the datasource list and workspace state', () => {
  const clearSelection = source.slice(
    source.indexOf('clearDatasourceSelection()'),
    source.indexOf('async activateDatasourceById')
  )
  assert.match(clearSelection, /this\.datasourceId = undefined/)
  assert.doesNotMatch(clearSelection, /this\.datasources = \[\]/)
  assert.doesNotMatch(clearSelection, /this\.initialized = false/)
})
