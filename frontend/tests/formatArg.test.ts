import assert from 'node:assert/strict'
import test from 'node:test'

import { formatArg } from '../src/utils/formatArg.ts'

test('parses boolean-like values case-insensitively', () => {
  assert.equal(formatArg('False'), false)
  assert.equal(formatArg('TRUE'), true)
})

test('ignores surrounding whitespace for boolean-like values', () => {
  assert.equal(formatArg(' false '), false)
  assert.equal(formatArg(' TRUE '), true)
})

test('preserves numeric and plain-text behavior', () => {
  assert.equal(formatArg('1'), 1)
  assert.equal(formatArg('0'), 0)
  assert.equal(formatArg('plain text'), 'plain text')
  assert.equal(formatArg(' Plain Text '), ' Plain Text ')
  assert.equal(formatArg(''), false)
})
