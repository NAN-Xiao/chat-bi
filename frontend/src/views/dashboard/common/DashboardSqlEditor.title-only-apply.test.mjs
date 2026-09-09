import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const source = readFileSync(
  fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url)),
  'utf8'
)

test('allows applying a title-only edit without rerunning the query', () => {
  assert.match(
    source,
    /const titleOnlyChange = computed\([\s\S]*?form\.title !== initialChartTitle\.value[\s\S]*?currentEditorSignature\(\) === initialEditorSignature\.value/
  )

  const validationBody = source.match(/function validateBeforeApply\(\) \{([\s\S]*?)\n\}/)?.[1] || ''
  assert.match(validationBody, /const requiresPreview = !titleOnlyChange\.value/)
  assert.match(validationBody, /if \(requiresPreview && sqlChangedAfterPreview\.value\)/)
  assert.match(validationBody, /if \(requiresPreview && !hasCurrentPreviewData\(\)\)/)
})

test('records the initial chart title for title-only change detection', () => {
  assert.match(source, /initialChartTitle\.value = form\.title/)
  assert.match(source, /const \{ title: _title, \.\.\.formState \} = form/)
  assert.match(source, /const \{ activeTab: _activeTab, \.\.\.builderState \} = sqlBuilder/)
})

test('rebases editor baseline after metadata normalization without hiding edits', () => {
  assert.match(source, /const signatureBeforeSchemaSanitize = currentEditorSignature\(\)/)
  assert.match(
    source,
    /if \(signatureBeforeSchemaSanitize === initialEditorSignature\.value\) \{[\s\S]*?initialEditorSignature\.value = currentEditorSignature\(\)/
  )
})

test('title-only apply updates the chart title without writing query state', () => {
  assert.match(source, /if \(titleOnlyChange\.value\) \{[\s\S]*?props\.viewInfo\.chart = \{[\s\S]*?title: form\.title/)
  assert.match(source, /if \(!validateBeforeApply\(\)\) return\n  writeEditorStateToViewInfo\(/)
})

test('preview signature includes time range and execution datasource changes', () => {
  assert.match(source, /datasource: selectedExecutionDatasourceId\.value/)
  assert.match(source, /time: hasSqlSource\.value[\s\S]*?range: sqlBuilder\.timeRange[\s\S]*?customRange: \[\.\.\.sqlBuilder\.timeCustomRange\]/)
})
