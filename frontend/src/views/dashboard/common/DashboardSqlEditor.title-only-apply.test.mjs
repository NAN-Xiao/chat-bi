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
    /const titleOnlyChange = computed\([\s\S]*?form\.title !== initialChartTitle\.value[\s\S]*?currentPreviewSignature\(\) === initialQuerySignature\.value/
  )
  assert.match(
    source,
    /currentPreviewSignature\(\) === lastPreviewSignature\.value/
  )

  const validationBody = source.match(/function validateBeforeApply\(\) \{([\s\S]*?)\n\}/)?.[1] || ''
  assert.match(validationBody, /const requiresPreview = !titleOnlyChange\.value/)
  assert.match(validationBody, /if \(requiresPreview && sqlChangedAfterPreview\.value\)/)
  assert.match(validationBody, /if \(requiresPreview && !hasCurrentPreviewData\(\)\)/)
})

test('records the initial chart title for title-only change detection', () => {
  assert.match(source, /initialChartTitle\.value = form\.title/)
})
