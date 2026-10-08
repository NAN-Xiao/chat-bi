import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync, existsSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
const sourcePath = 'src/views/chat/component/chartThemeLifecycle.ts'
function load() {
  assert.ok(existsSync(sourcePath), 'theme changes require a serial, disposable scheduler')
  const exports = {}
  vm.runInNewContext(
    ts.transpileModule(readFileSync(sourcePath, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS },
    }).outputText,
    { exports, Promise }
  )
  return exports.createChartThemeLifecycle
}
test('coalesces pending revisions without concurrent updates', async () => {
  const create = load()
  let release
  const seen = []
  const gate = new Promise((r) => (release = r))
  const queue = create({
    apply: async (revision) => {
      seen.push(revision)
      if (revision === 1) await gate
    },
    onError: (e) => {
      throw e
    },
  })
  queue.request()
  queue.request()
  queue.request()
  assert.deepEqual(seen, [1])
  release()
  await queue.whenIdle()
  assert.deepEqual(seen, [1, 3])
})
test('disposing prevents pending updates and suppresses late errors', async () => {
  const create = load()
  let reject
  let calls = 0
  const errors = []
  const queue = create({
    apply: () => {
      calls++
      return new Promise((_, r) => (reject = r))
    },
    onError: (e) => errors.push(e),
  })
  queue.request()
  queue.request()
  queue.dispose()
  reject(Error('destroyed'))
  await queue.whenIdle()
  assert.equal(calls, 1)
  assert.equal(errors.length, 0)
})
test('reports live failures and accepts later requests', async () => {
  const create = load()
  let calls = 0
  const errors = []
  const queue = create({
    apply: async () => {
      if (++calls === 1) throw Error('render failed')
    },
    onError: (e) => errors.push(e.message),
  })
  queue.request()
  await queue.whenIdle()
  assert.deepEqual(errors, ['render failed'])
  queue.request()
  await queue.whenIdle()
  assert.equal(calls, 2)
})
