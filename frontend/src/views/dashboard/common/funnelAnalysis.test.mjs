import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import test from 'node:test'
import ts from 'typescript'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'funnelAnalysis.ts'), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
})
const tempDir = mkdtempSync(join(tmpdir(), 'funnel-analysis-'))
const compiledPath = join(tempDir, 'funnelAnalysis.mjs')
writeFileSync(compiledPath, compiled.outputText, 'utf8')

try {
  const {
    formatFunnelWindow,
    isValidFunnelWindow,
    maxFunnelWindowValue,
    normalizeFunnelWindow,
  } = await import(pathToFileURL(compiledPath).href)

  test('supports same-day and duration funnel windows', () => {
    assert.equal(formatFunnelWindow({ mode: 'same_day', value: 1, unit: 'day' }), '当天')
    assert.equal(formatFunnelWindow({ mode: 'duration', value: 7, unit: 'day' }), '7天')
    assert.equal(formatFunnelWindow({ mode: 'duration', value: 12, unit: 'hour' }), '12小时')
    assert.equal(formatFunnelWindow({ mode: 'duration', value: 30, unit: 'minute' }), '30分钟')
  })

  test('migrates the known legacy day-only config', () => {
    assert.deepEqual(normalizeFunnelWindow(undefined, 14), {
      mode: 'duration',
      value: 14,
      unit: 'day',
    })
  })

  test('rejects invalid and over-limit duration values', () => {
    assert.equal(isValidFunnelWindow({ mode: 'duration', value: 0, unit: 'day' }), false)
    assert.equal(isValidFunnelWindow({ mode: 'duration', value: 366, unit: 'day' }), false)
    assert.equal(isValidFunnelWindow({ mode: 'duration', value: 24, unit: 'hour' }), true)
    assert.equal(maxFunnelWindowValue('minute'), 525600)
  })
} finally {
  rmSync(tempDir, { recursive: true, force: true })
}
