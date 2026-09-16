import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('../src/api/dashboard.ts', import.meta.url), 'utf8')
  .replace(/^import .*$/gm, '').replace('export const dashboardApi', 'globalThis.dashboardApi')

function api(request) {
  const context = vm.createContext({ request, DOMException })
  vm.runInContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context)
  return context.dashboardApi
}

test('generation derives HTTP timeout from server budget and disables replay', async () => {
  const controller = new AbortController()
  const calls = []
  const client = api({
    get: async (url, config) => {
      calls.push({ url, config })
      return { total_timeout_seconds: 900 }
    },
    post: async (url, data, config) => {
      calls.push({ url, data, config })
      return { sql: 'SELECT 1' }
    },
  })
  const result = await client.generate_ai_sql({ datasource: 7 }, {
    signal: controller.signal, timeout: 180000, requestOptions: { silent: true, retryCount: 4 },
  })
  assert.equal(result.sql, 'SELECT 1')
  assert.equal(calls.length, 2)
  assert.equal(calls[0].url, '/dashboard/ai_sql_generation_limits')
  assert.equal(calls[0].config.signal, controller.signal)
  assert.equal(calls[0].config.requestOptions.retryCount, 0)
  assert.equal(calls[1].config.timeout, 905000)
  assert.equal(calls[1].config.signal, controller.signal)
  assert.equal(calls[1].config.requestOptions.retryCount, 0)
})

test('invalid server budget fails explicitly before starting generation', async () => {
  for (const budget of [undefined, 0, -1, '900', Infinity]) {
    let posts = 0
    const client = api({
      get: async () => ({ total_timeout_seconds: budget }),
      post: async () => { posts++; return {} },
    })
    await assert.rejects(client.generate_ai_sql({ datasource: 7 }), /超时配置/)
    assert.equal(posts, 0)
  }
})

test('cancellation while loading limits never starts generation', async () => {
  const controller = new AbortController()
  let posts = 0
  const client = api({
    get: async () => { controller.abort(); return { total_timeout_seconds: 900 } },
    post: async () => { posts++; return {} },
  })
  await assert.rejects(client.generate_ai_sql({}, { signal: controller.signal }), { name: 'AbortError' })
  assert.equal(posts, 0)
})
