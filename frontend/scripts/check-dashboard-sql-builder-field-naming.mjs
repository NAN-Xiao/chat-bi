import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const editorPath = resolve(root, 'src/views/dashboard/common/DashboardSqlEditor.vue')
const pickerPath = resolve(root, 'src/views/dashboard/common/BuilderFieldPicker.vue')
const aiSqlGeneratorPath = resolve(root, '../backend/apps/dashboard/crud/ai_sql_generator.py')
const source = [
  readFileSync(editorPath, 'utf8'),
  readFileSync(pickerPath, 'utf8'),
  readFileSync(aiSqlGeneratorPath, 'utf8'),
].join('\n')

const forbiddenPatterns = [
  { pattern: /\bitem\.event\b/, label: 'metric item should use item.field instead of item.event' },
  { pattern: /\beventField\b/, label: 'AI context should not send legacy eventField' },
  { pattern: /placeholder="事件\/字段"/, label: 'builder picker placeholder should be generic field wording' },
  { pattern: /^\s*event:\s*item\.event/m, label: 'saved builder config should not write legacy event key' },
  { pattern: /mode="event"/, label: 'field picker mode should not use legacy event mode' },
  { pattern: /PickerMode = 'event'/, label: 'field picker type should not expose legacy event mode' },
  { pattern: /事件名\s+event\.event/, label: 'AI prompt examples should not use legacy event table examples' },
]

for (const { pattern, label } of forbiddenPatterns) {
  assert.equal(pattern.test(source), false, label)
}
