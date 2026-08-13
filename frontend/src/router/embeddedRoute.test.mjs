import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const routerSource = readFileSync(new URL('./index.ts', import.meta.url), 'utf8')

test('embedded management route uses the current assistant management view', () => {
  assert.match(
    routerSource,
    /import SystemEmbedded from ['"]@\/views\/system\/embedded\/index\.vue['"]/
  )
  assert.doesNotMatch(
    routerSource,
    /import SystemEmbedded from ['"]@\/views\/system\/embedded\/Page\.vue['"]/
  )
})
