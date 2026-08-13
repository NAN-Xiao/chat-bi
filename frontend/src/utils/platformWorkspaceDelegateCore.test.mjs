import assert from 'node:assert/strict'
import test from 'node:test'

test('平台代理 generation 只接受当前上下文响应', async () => {
  const module = await import('./platformWorkspaceDelegateCore.ts').catch(() => ({}))
  assert.equal(typeof module.createPlatformWorkspaceDelegateRequestContext, 'function')

  const context = module.createPlatformWorkspaceDelegateRequestContext('')
  const inactive = context.capture()
  assert.deepEqual(inactive, { active: false, tenantId: '', generation: 0 })

  context.update('A')
  const tenantA = context.capture()
  context.update('A')
  assert.equal(context.capture().generation, tenantA.generation)

  context.update('B')
  assert.throws(() => context.assertCurrent(tenantA, 'A'), {
    name: 'WorkspaceContextStaleError',
  })

  const tenantB = context.capture()
  assert.throws(() => context.assertCurrent(tenantB, 'A'), {
    name: 'WorkspaceContextMismatchError',
  })
  assert.doesNotThrow(() => context.assertCurrent(tenantB, 'B'))

  context.update('')
  assert.throws(() => context.assertCurrent(tenantB, 'B'), {
    name: 'WorkspaceContextStaleError',
  })
})
