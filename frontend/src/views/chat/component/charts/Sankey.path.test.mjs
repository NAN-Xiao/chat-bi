import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync('src/views/chat/component/charts/Sankey.ts', 'utf8')

test('path sankey nodes include their step so repeated events cannot form a circular link', () => {
  assert.match(source, /findStepField\(/)
  assert.match(source, /layeredNodeKey\(step, datum\[source\.value\]\)/)
  assert.match(source, /layeredNodeKey\(step \+ 1, datum\[target\.value\]\)/)
  assert.match(source, /const SANKEY_NODE_SEPARATOR = '::'/)
})

test('path sankey labels hide the internal layer key', () => {
  assert.match(source, /function nodeLabel\(key: unknown\)/)
  assert.match(source, /labelText: this\.showLabel \? \(datum: any\) => nodeLabel\(datum\.key\)/)
  assert.match(
    source,
    /name: `\$\{nodeLabel\(datum\.source\.key\)\} -> \$\{nodeLabel\(datum\.target\.key\)\}`/
  )
})

console.log('Sankey path tests passed')
