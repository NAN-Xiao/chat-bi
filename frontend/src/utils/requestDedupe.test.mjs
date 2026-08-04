import assert from 'node:assert/strict'
import test from 'node:test'
import { cachedRequest, clearRequestCache } from './requestDedupe.ts'

test('清理进行中请求后旧 Promise 不能重新写回缓存', async () => {
  clearRequestCache()
  let resolveFirst
  let calls = 0
  const first = cachedRequest(
    'agent-selector:tenant-a|user-a',
    () =>
      new Promise((resolve) => {
        resolveFirst = resolve
      })
  )

  clearRequestCache('agent-selector:')
  resolveFirst('old-user-value')
  await first

  const second = await cachedRequest('agent-selector:tenant-a|user-a', async () => {
    calls += 1
    return 'new-user-value'
  })

  assert.equal(calls, 1)
  assert.equal(second, 'new-user-value')
})
