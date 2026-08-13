import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const component = readFileSync('src/views/chat/component/ChartComponent.vue', 'utf8')
const radialValidation = readFileSync('src/views/chat/component/charts/radialPartition.ts', 'utf8')

test('chart validation errors carry a stable code', async () => {
  const source = readFileSync('src/views/chat/component/chartValidation.ts', 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
  const { ChartValidationError, isChartValidationError } = await import(moduleUrl)
  const error = new ChartValidationError('invalid_value')

  assert.equal(error.code, 'invalid_value')
  assert.equal(isChartValidationError(error), true)
  assert.equal(isChartValidationError(new Error('invalid_value')), false)
})

test('radial validation errors use the shared chart validation contract', () => {
  assert.match(radialValidation, /extends ChartValidationError/)
})

test('validation failure clears the old chart and skips render retries', () => {
  assert.match(component, /if \(isChartValidationError\(error\)\) \{[\s\S]*?clearActiveChart\(\)[\s\S]*?chartValidationErrorCode\.value = error\.code[\s\S]*?return/)

  const validationBranch = component.match(/if \(isChartValidationError\(error\)\) \{([\s\S]*?)\n\s*\}/)
  assert.ok(validationBranch)
  assert.doesNotMatch(validationBranch[1], /scheduleRenderChart/)
  assert.match(component, /if \(retry < maxRenderRetries\) \{\s*scheduleRenderChart\(160, retry \+ 1\)/)
})

test('validation failure renders a localized explicit error state', () => {
  assert.match(component, /const chartValidationMessage = computed/)
  assert.match(component, /v-if="chartValidationErrorCode"[\s\S]*?role="alert"[\s\S]*?chartValidationMessage/)
})
