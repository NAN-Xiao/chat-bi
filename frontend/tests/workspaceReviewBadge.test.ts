import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createLatestWorkspaceNotificationLoader,
  shouldLoadWorkspaceNotifications,
  shouldLoadWorkspaceReviews,
  shouldShowWorkspaceNotificationBadge,
} from '../src/utils/workspaceReviewBadge.ts'

const owner = { tenantId: '1', role: 'owner' }
const admin = { tenantId: '1', role: 'admin' }
const member = { tenantId: '1', role: 'member' }

test('仅当前工作空间拥有者和管理员加载待审核加入申请', () => {
  assert.equal(shouldLoadWorkspaceReviews(owner), true)
  assert.equal(shouldLoadWorkspaceReviews(admin), true)
  assert.equal(shouldLoadWorkspaceReviews(member), false)
  assert.equal(shouldLoadWorkspaceReviews({ tenantId: '', role: 'owner' }), false)
  assert.equal(
    shouldLoadWorkspaceReviews({ tenantId: '1', role: 'owner', isSystemAdminUser: true }),
    false
  )
  assert.equal(
    shouldLoadWorkspaceReviews({
      tenantId: '1',
      role: 'admin',
      isPlatformWorkspaceDelegate: true,
    }),
    false
  )
})

test('普通业务用户即使没有当前工作空间也加载个人邀请', () => {
  assert.equal(shouldLoadWorkspaceNotifications(member), true)
  assert.equal(shouldLoadWorkspaceNotifications({ tenantId: '', role: '' }), true)
  assert.equal(shouldLoadWorkspaceNotifications({ isSystemAdminUser: true }), false)
  assert.equal(shouldLoadWorkspaceNotifications({ isPlatformWorkspaceDelegate: true }), false)
})

test('任一待处理通知存在时显示红点', () => {
  assert.equal(shouldShowWorkspaceNotificationBadge(owner, 1), true)
  assert.equal(shouldShowWorkspaceNotificationBadge(member, 1), true)
  assert.equal(shouldShowWorkspaceNotificationBadge({ tenantId: '', role: '' }, 1), true)
  assert.equal(shouldShowWorkspaceNotificationBadge(owner, 0), false)
  assert.equal(
    shouldShowWorkspaceNotificationBadge(
      { tenantId: '1', role: 'owner', isSystemAdminUser: true },
      1
    ),
    false
  )
})

test('管理员通知数合并待审核加入申请和个人邀请', async () => {
  const loadCount = createLatestWorkspaceNotificationLoader({
    fetchPendingReviews: async () => [
      { status: 'pending' },
      { status: 'approved' },
      { status: 'pending' },
    ],
    fetchPendingInvitations: async () => [
      { status: 'pending' },
      { status: 'rejected' },
    ],
  })

  assert.equal(await loadCount(owner), 3)
})

test('普通成员只加载个人邀请', async () => {
  let reviewCalls = 0
  const loadCount = createLatestWorkspaceNotificationLoader({
    fetchPendingReviews: async () => {
      reviewCalls += 1
      return [{ status: 'pending' }]
    },
    fetchPendingInvitations: async () => [{ status: 'pending' }],
  })

  assert.equal(await loadCount(member), 1)
  assert.equal(reviewCalls, 0)
})

test('一个通知接口失败时仍保留另一个接口的计数', async () => {
  const invitationOnly = createLatestWorkspaceNotificationLoader({
    fetchPendingReviews: async () => {
      throw new Error('review network')
    },
    fetchPendingInvitations: async () => [{ status: 'pending' }],
  })
  assert.equal(await invitationOnly(owner), 1)

  const reviewOnly = createLatestWorkspaceNotificationLoader({
    fetchPendingReviews: async () => [{ status: 'pending' }],
    fetchPendingInvitations: async () => {
      throw new Error('invitation network')
    },
  })
  assert.equal(await reviewOnly(owner), 1)
})

test('平台上下文不调用业务通知接口', async () => {
  let calls = 0
  const loadCount = createLatestWorkspaceNotificationLoader({
    fetchPendingReviews: async () => {
      calls += 1
      return [{ status: 'pending' }]
    },
    fetchPendingInvitations: async () => {
      calls += 1
      return [{ status: 'pending' }]
    },
  })

  assert.equal(await loadCount({ isSystemAdminUser: true }), 0)
  assert.equal(await loadCount({ isPlatformWorkspaceDelegate: true }), 0)
  assert.equal(calls, 0)
})

test('加载器忽略快速切换空间产生的旧请求结果', async () => {
  let resolveFirst: (rows: Array<{ status?: string }>) => void = () => undefined
  const firstRequest = new Promise<Array<{ status?: string }>>((resolve) => {
    resolveFirst = resolve
  })
  let invitationCalls = 0
  const loadCount = createLatestWorkspaceNotificationLoader({
    fetchPendingReviews: async () => [],
    fetchPendingInvitations: () => {
      invitationCalls += 1
      return invitationCalls === 1 ? firstRequest : Promise.resolve([])
    },
  })

  const oldResult = loadCount(owner)
  const currentResult = loadCount({ tenantId: '2', role: 'admin' })
  assert.equal(await currentResult, 0)
  resolveFirst([{ status: 'pending' }])
  assert.equal(await oldResult, null)
})
