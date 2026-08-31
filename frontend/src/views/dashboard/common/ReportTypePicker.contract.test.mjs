import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import ts from 'typescript'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'reportTypes.ts'), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
})
const tempDir = mkdtempSync(join(tmpdir(), 'report-types-'))
const compiledPath = join(tempDir, 'reportTypes.mjs')
writeFileSync(compiledPath, compiled.outputText, 'utf8')

try {
  const { REPORT_TYPES, createDefaultReportConfig } = await import(pathToFileURL(compiledPath).href)
  assert.deepEqual(
    REPORT_TYPES.map((item) => item.key),
    [
      'event',
      'retention',
      'funnel',
      'distribution',
      'interval',
      'path',
      'property',
      'attribution',
      'heatmap',
      'ranking',
      'revenue',
    ]
  )
  assert.deepEqual(createDefaultReportConfig('retention').fields, {
    initialEvent: '',
    returnEvent: '',
  })
  assert.deepEqual(createDefaultReportConfig('funnel').analysisWindow, {
    mode: 'duration',
    value: 1,
    unit: 'day',
  })

  const pickerSource = readFileSync(join(currentDir, 'ReportTypePicker.vue'), 'utf8')
  const resourceTreeSource = readFileSync(join(currentDir, 'ResourceTree.vue'), 'utf8')
  const editorSource = readFileSync(join(currentDir, '..', 'editor', 'index.vue'), 'utf8')
  const toolbarSource = readFileSync(join(currentDir, '..', 'editor', 'Toolbar.vue'), 'utf8')

  assert.match(pickerSource, /v-for="item in REPORT_TYPES"/)
  assert.match(pickerSource, /<FunnelWindowPicker v-model="config\.analysisWindow"/)
  assert.doesNotMatch(pickerSource, /analysisWindowDays/)
  assert.match(pickerSource, /reportMeta:\s*\{[\s\S]*?type:\s*selectedType\.value/)
  assert.match(resourceTreeSource, /dashboardStore\.setCanvasStyleData\(\{ reportMeta \}\)/)
  assert.match(resourceTreeSource, /<ReportTypePicker[^>]*@confirm="handleReportTypeConfirm"/)
  assert.match(editorSource, /reportMeta:\s*\(canvasStyleData\.value as any\)\?\.reportMeta \|\| null/)
  assert.match(toolbarSource, /baseParams\?\.reportMeta\?\.label/)
} finally {
  rmSync(tempDir, { recursive: true, force: true })
}

console.log('Report type picker contract tests passed')
