import assert from 'node:assert/strict'
import test from 'node:test'

import {
  WorkspaceContextStaleError,
  createWorkspaceContextCore,
} from './workspaceContextCore.ts'

const memoryStorage = () => {
  const values = new Map()
  return {
    getItem(key) {
      return values.get(key) ?? null
    },
    setItem(key, value) {
      values.set(key, String(value))
    },
    removeItem(key) {
      values.delete(key)
    },
  }
}

const readyContext = (tenantId = 'tenant-a') => {
  const context = createWorkspaceContextCore(memoryStorage())
  context.completeBootstrap(tenantId)
  return context
}

test('两个标签页拥有独立的活动工作空间', () => {
  const tabA = createWorkspaceContextCore(memoryStorage())
  const tabB = createWorkspaceContextCore(memoryStorage())

  tabA.completeBootstrap('tenant-a')
  tabB.completeBootstrap('tenant-b')

  assert.equal(tabA.state.activeTenantId, 'tenant-a')
  assert.equal(tabB.state.activeTenantId, 'tenant-b')
})

test('刷新只从当前标签页 sessionStorage 恢复工作空间', () => {
  const storage = memoryStorage()
  const first = createWorkspaceContextCore(storage)
  first.completeBootstrap('tenant-a')

  const refreshed = createWorkspaceContextCore(storage)
  assert.equal(refreshed.state.activeTenantId, 'tenant-a')
  assert.equal(refreshed.state.phase, 'bootstrapping')
})

test('A 到 B 到 C 的乱序结果只允许 C 提交', () => {
  const context = readyContext('A')
  const toB = context.beginSwitch('B')
  const toC = context.beginSwitch('C')

  assert.ok(toB)
  assert.ok(toC)
  assert.equal(context.commitSwitch(toB), false)
  assert.equal(context.finishSwitch(toB), false)
  assert.equal(context.commitSwitch(toC), true)
  assert.equal(context.state.phase, 'switching')
  assert.equal(context.finishSwitch(toC), true)
  assert.equal(context.state.activeTenantId, 'C')
  assert.equal(context.state.pendingTenantId, '')
  assert.equal(context.state.phase, 'ready')
})

test('只有最新事务失败时才能恢复原工作空间', () => {
  const context = readyContext('A')
  const toB = context.beginSwitch('B')
  const toC = context.beginSwitch('C')

  assert.ok(toB)
  assert.ok(toC)
  assert.equal(context.rollbackSwitch(toB), false)
  assert.equal(context.rollbackSwitch(toC), true)
  assert.equal(context.state.activeTenantId, 'A')
  assert.equal(context.state.phase, 'ready')
})

test('旧普通请求在切换开始后不可消费', () => {
  const context = readyContext('A')
  const snapshot = context.captureRequest('normal')

  context.beginSwitch('B')

  assert.throws(
    () => context.assertConsumable(snapshot, 'A'),
    WorkspaceContextStaleError
  )
})

test('普通请求拒绝租户不一致的响应', () => {
  const context = readyContext('A')
  const snapshot = context.captureRequest('normal')

  assert.throws(
    () => context.assertConsumable(snapshot, 'B'),
    WorkspaceContextStaleError
  )
})

test('switching 阶段拒绝新的普通请求但允许当前显式验证请求', () => {
  const context = readyContext('A')
  const transaction = context.beginSwitch('B')

  assert.ok(transaction)
  assert.throws(() => context.captureRequest('normal'), WorkspaceContextStaleError)

  const snapshot = context.captureRequest('switch', 'B', transaction.switchId)
  assert.equal(snapshot.tenantId, 'B')
  assert.doesNotThrow(() => context.assertConsumable(snapshot, 'B'))
})

test('新的切换使旧显式验证请求过期', () => {
  const context = readyContext('A')
  const toB = context.beginSwitch('B')
  assert.ok(toB)
  const snapshot = context.captureRequest('switch', 'B', toB.switchId)

  context.beginSwitch('C')

  assert.throws(
    () => context.assertConsumable(snapshot, 'B'),
    WorkspaceContextStaleError
  )
})
