import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const requestSource = readFileSync(new URL('./request.ts', import.meta.url), 'utf8')
const knowledgeApiSource = readFileSync(new URL('../api/knowledgeBase.ts', import.meta.url), 'utf8')

test('blob error responses are hydrated before shared or caller-owned error handling', () => {
  assert.match(requestSource, /const hydrateBlobErrorResponse = async/)
  assert.match(requestSource, /response\.data instanceof Blob/)
  assert.match(requestSource, /const text = await response\.data\.text\(\)/)
  assert.match(requestSource, /response\.data = JSON\.parse\(text\)/)
  assert.ok(
    requestSource.indexOf('await hydrateBlobErrorResponse(error)') <
      requestSource.indexOf('// Unified error handling')
  )
})

test('knowledge source downloads let the caller own the actionable error message', () => {
  assert.match(
    knowledgeApiSource,
    /request\.download\([\s\S]*requestOptions: \{ customError: true \}/
  )
})
