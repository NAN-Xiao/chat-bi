import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const systemApiPath = resolve(root, 'src/api/system.ts')
const editorPath = resolve(root, 'src/views/dashboard/common/DashboardSqlEditor.vue')
const pickerPath = resolve(root, 'src/views/dashboard/common/BuilderFieldPicker.vue')

const systemApiSource = readFileSync(systemApiPath, 'utf8')
const editorSource = readFileSync(editorPath, 'utf8')
const pickerSource = readFileSync(pickerPath, 'utf8')

assert.match(
  systemApiSource,
  /eventCatalog:\s*\(\)\s*=>\s*request\.get\('\/system\/tracking-config\/event-catalog'\)/,
  'trackingConfigApi should expose eventCatalog endpoint'
)
assert.match(
  editorSource,
  /trackingEventCatalogOptions/,
  'DashboardSqlEditor should build event catalog options for analysis field picker'
)
assert.match(
  editorSource,
  /:options="analysisFieldOptions"/,
  'analysis metric field picker should use event catalog options'
)
assert.match(
  editorSource,
  /trackingEventPropertyOptionsByEvent/,
  'DashboardSqlEditor should build filter field options from event catalog properties'
)
assert.match(
  editorSource,
  /:field-options="metricFilterFieldOptions\(item\)"/,
  'metric filter field picker should use properties of the selected event'
)
assert.match(
  editorSource,
  /property_display_name|propertyDisplayName|display_name/,
  'event property options should use property display name as the visible label'
)
assert.match(
  pickerSource,
  /tracking-event/,
  'BuilderFieldPicker should support tracking event mode'
)
assert.match(
  pickerSource,
  /builder-event-picker-columns/,
  'BuilderFieldPicker should render event catalog as left category and right event list'
)
