import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('./DataDictionary.vue', import.meta.url), 'utf8')

test('provides a workspace SQL rules editor backed by tracking config', () => {
  assert.match(source, /const sqlRulesDrawerVisible = ref\(false\)/)
  assert.match(source, /sqlRulesText\.value = String\(current\.sql_rules \|\| ''\)/)
  assert.match(source, /\{ \.\.\.current, sql_rules: sqlRulesText\.value\.trim\(\) \}/)
  assert.match(source, /trackingConfigApi\.update\(/)
  assert.match(source, /t\('data_dictionary\.sql_rules'\)/)
  assert.match(source, /v-model="sqlRulesText"/)
  assert.match(source, /maxlength="8000"/)
})
