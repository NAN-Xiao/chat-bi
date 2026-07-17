import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createLatestWorkspaceReviewLoader,
  shouldLoadWorkspaceReviews,
  shouldShowWorkspaceReviewBadge,
} from '../src/utils/workspaceReviewBadge.ts'

const owner = { tenantId: '1', role: 'owner' }
const admin = { tenantId: '1', role: 'admin' }

test('仅工作空间拥有者和管理员加载待审核申请', () => {
  assert.equal(shouldLoadWorkspaceReviews(owner), true)
  assert.equal(shouldLoadWorkspaceReviews(admin), true)
  assert.equal(shouldLoadWorkspaceReviews({ tenantId: '1', role: 'member' }), false)
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

test('仅管理角色存在待审核申请时显示红点', () => {
  assert.equal(shouldShowWorkspaceReviewBadge(owner, 1), true)
  assert.equal(shouldShowWorkspaceReviewBadge(admin, 2), true)
  assert.equal(shouldShowWorkspaceReviewBadge(owner, 0), false)
  assert.equal(shouldShowWorkspaceReviewBadge({ tenantId: '1', role: 'member' }, 1), false)
})

test('加载器统计待审核申请并在失败时降级为零', async () => {
  const loadCount = createLatestWorkspaceReviewLoader(async () => [
    { status: 'pending' },
    { status: 'approved' },
    { status: 'pending' },
  ])
  assert.equal(await loadCount(owner), 2)

  const failedLoad = createLatestWorkspaceReviewLoader(async () => {
    throw new Error('network')
  })
  assert.equal(await failedLoad(owner), 0)
  assert.equal(await failedLoad({ tenantId: '1', role: 'member' }), 0)
})

test('加载器忽略快速切换空间产生的旧请求结果', async () => {
  let resolveFirst: (rows: Array<{ status?: string }>) => void = () => undefined
  const firstRequest = new Promise<Array<{ status?: string }>>((resolve) => {
    resolveFirst = resolve
  })
  let callCount = 0
  const loadCount = createLatestWorkspaceReviewLoader(() => {
    callCount += 1
    return callCount === 1 ? firstRequest : Promise.resolve([])
  })

  const oldResult = loadCount(owner)
  const currentResult = loadCount({ tenantId: '2', role: 'admin' })
  assert.equal(await currentResult, 0)
  resolveFirst([{ status: 'pending' }])
  assert.equal(await oldResult, null)
})
