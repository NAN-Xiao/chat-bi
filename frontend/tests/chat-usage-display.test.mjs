import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import ts from 'typescript'

const source = fs.readFileSync(path.resolve('src/views/chat/chatUsageDisplay.ts'), 'utf8')
const output = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
}).outputText
const module = { exports: {} }
vm.runInNewContext(output, { exports: module.exports, module })
const { resolveChatUsageDisplay } = module.exports

assert.deepEqual(
  { ...resolveChatUsageDisplay(undefined, 51917) },
  { showContainer: true, showDuration: false, showTotalTokens: true }
)
assert.deepEqual(
  { ...resolveChatUsageDisplay(106.45, undefined) },
  { showContainer: true, showDuration: true, showTotalTokens: false }
)
assert.deepEqual(
  { ...resolveChatUsageDisplay(undefined, undefined) },
  { showContainer: false, showDuration: false, showTotalTokens: false }
)
assert.deepEqual(
  { ...resolveChatUsageDisplay(0, 0) },
  { showContainer: true, showDuration: true, showTotalTokens: true }
)

console.log('chat usage display tests passed')
