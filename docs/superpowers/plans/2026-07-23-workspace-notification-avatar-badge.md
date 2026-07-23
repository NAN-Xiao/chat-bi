# 工作空间通知头像红点扩展 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让全局头像红点同时提示当前工作空间待审核加入申请和当前用户待响应工作空间邀请，并在刷新页面或切换工作空间后更新。

**Architecture:** 扩展 `workspaceReviewBadge.ts` 为统一的工作空间通知加载器：按上下文决定是否加载空间审核申请，普通业务用户始终加载个人邀请，两个接口分别容错并共享最新请求序号。`Person.vue` 只提供两个现有 API 函数并消费统一数量，继续复用既有红点样式和交互。

**Tech Stack:** Vue 3、TypeScript、Node.js `node:test`、Vite、`vue-tsc`

## Global Constraints

- 不新增轮询、WebSocket、服务端推送或跨标签页同步。
- 不新增通知弹窗、通知列表入口、自动跳转或红点数量。
- 不提示用户自己提交且仍在等待审核的加入申请。
- 不新增或修改后端接口。
- 平台管理员和平台工作空间代理不显示该业务通知红点。
- 保留头像点击、菜单、路由和现有红点样式。
- 只修改本计划列出的文件，不暂存或提交工作区中的其他改动。

---

### Task 1: 统一工作空间通知加载与显示判断

**Files:**
- Modify: `frontend/tests/workspaceReviewBadge.test.ts`
- Modify: `frontend/src/utils/workspaceReviewBadge.ts`

**Interfaces:**
- Consumes: `canManageWorkspaceRole(role?: string | null): boolean`
- Produces: `WorkspaceNotificationBadgeContext`
- Produces: `shouldLoadWorkspaceReviews(context: WorkspaceNotificationBadgeContext): boolean`
- Produces: `shouldLoadWorkspaceNotifications(context: WorkspaceNotificationBadgeContext): boolean`
- Produces: `shouldShowWorkspaceNotificationBadge(context: WorkspaceNotificationBadgeContext, pendingCount: number): boolean`
- Produces: `createLatestWorkspaceNotificationLoader(fetchers): (context: WorkspaceNotificationBadgeContext) => Promise<number | null>`

- [ ] **Step 1: 用测试声明通知权限、计数、独立容错与迟到响应行为**

将 `frontend/tests/workspaceReviewBadge.test.ts` 更新为以下完整测试：

```ts
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
    shouldShowWorkspaceNotificationBadge({ tenantId: '1', role: 'owner', isSystemAdminUser: true }, 1),
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
```

- [ ] **Step 2: 运行测试并确认因新接口尚不存在而失败**

Run: `cd frontend; node --test tests/workspaceReviewBadge.test.ts`

Expected: FAIL，错误包含 `does not provide an export named 'createLatestWorkspaceNotificationLoader'` 或等价的缺少新导出信息。

- [ ] **Step 3: 实现最小统一通知加载器**

将 `frontend/src/utils/workspaceReviewBadge.ts` 更新为：

```ts
import { canManageWorkspaceRole } from './workspacePermission.ts'

export interface WorkspaceNotificationBadgeContext {
  tenantId?: string | number | null
  role?: string | null
  isSystemAdminUser?: boolean
  isPlatformWorkspaceDelegate?: boolean
}

interface WorkspaceNotification {
  status?: string | null
}

type FetchPendingWorkspaceNotifications = () => Promise<
  WorkspaceNotification[] | null | undefined
>

interface WorkspaceNotificationFetchers {
  fetchPendingReviews: FetchPendingWorkspaceNotifications
  fetchPendingInvitations: FetchPendingWorkspaceNotifications
}

const isBusinessWorkspaceUser = (context: WorkspaceNotificationBadgeContext) =>
  !context.isSystemAdminUser && !context.isPlatformWorkspaceDelegate

export const shouldLoadWorkspaceReviews = (context: WorkspaceNotificationBadgeContext) =>
  Boolean(context.tenantId) &&
  isBusinessWorkspaceUser(context) &&
  canManageWorkspaceRole(context.role)

export const shouldLoadWorkspaceNotifications = (context: WorkspaceNotificationBadgeContext) =>
  isBusinessWorkspaceUser(context)

export const shouldShowWorkspaceNotificationBadge = (
  context: WorkspaceNotificationBadgeContext,
  pendingCount: number
) => shouldLoadWorkspaceNotifications(context) && pendingCount > 0

const countPending = async (fetchPending: FetchPendingWorkspaceNotifications) => {
  try {
    const rows = (await fetchPending()) || []
    return rows.filter((item) => item.status === 'pending').length
  } catch {
    return 0
  }
}

export const createLatestWorkspaceNotificationLoader = (
  fetchers: WorkspaceNotificationFetchers
) => {
  let latestRequestId = 0

  return async (context: WorkspaceNotificationBadgeContext): Promise<number | null> => {
    const requestId = ++latestRequestId
    if (!shouldLoadWorkspaceNotifications(context)) return 0

    const pendingCounts = [countPending(fetchers.fetchPendingInvitations)]
    if (shouldLoadWorkspaceReviews(context)) {
      pendingCounts.push(countPending(fetchers.fetchPendingReviews))
    }

    const total = (await Promise.all(pendingCounts)).reduce((sum, count) => sum + count, 0)
    if (requestId !== latestRequestId) return null
    return total
  }
}
```

- [ ] **Step 4: 运行相关单元测试并确认通过**

Run: `cd frontend; node --test tests/workspaceReviewBadge.test.ts`

Expected: PASS，`8` 个测试通过、`0` 个失败。

- [ ] **Step 5: 提交统一通知加载器**

```powershell
git add -- frontend/tests/workspaceReviewBadge.test.ts frontend/src/utils/workspaceReviewBadge.ts
git diff --cached --check
git diff --cached --name-only
git commit -m "功能：统一工作空间通知红点计数"
```

Expected staged files: only the two files listed above.

---

### Task 2: 将头像组件接入个人待响应邀请

**Files:**
- Modify: `frontend/src/components/layout/Person.vue`

**Interfaces:**
- Consumes: `createLatestWorkspaceNotificationLoader({ fetchPendingReviews, fetchPendingInvitations })`
- Consumes: `shouldShowWorkspaceNotificationBadge(context, pendingCount)`
- Consumes: `tenantApi.tenantApplications('pending')`
- Consumes: `tenantApi.myInvitations('pending')`
- Produces: 页面刷新或工作空间上下文变化后更新的 `pendingWorkspaceNotificationCount`

- [ ] **Step 1: 用源码契约测试声明头像组件必须接入两个通知接口**

在 `frontend/tests/workspaceReviewBadge.test.ts` 末尾追加：

```ts
import { readFile } from 'node:fs/promises'

test('头像组件接入空间审核申请和个人邀请', async () => {
  const source = await readFile(new URL('../src/components/layout/Person.vue', import.meta.url), 'utf8')

  assert.match(source, /createLatestWorkspaceNotificationLoader/)
  assert.match(source, /tenantApi\.tenantApplications\('pending'\)/)
  assert.match(source, /tenantApi\.myInvitations\('pending'\)/)
  assert.match(source, /shouldShowWorkspaceNotificationBadge/)
})
```

将 `readFile` 导入移动到测试文件顶部的其他 Node.js 导入旁，避免中段导入。

- [ ] **Step 2: 运行测试并确认头像组件尚未接入新加载器**

Run: `cd frontend; node --test tests/workspaceReviewBadge.test.ts`

Expected: FAIL，测试 `头像组件接入空间审核申请和个人邀请` 报告缺少 `createLatestWorkspaceNotificationLoader` 或 `tenantApi.myInvitations('pending')`。

- [ ] **Step 3: 在头像组件中接入统一通知加载器**

在 `frontend/src/components/layout/Person.vue` 中完成以下替换：

```ts
import {
  createLatestWorkspaceNotificationLoader,
  shouldShowWorkspaceNotificationBadge,
  type WorkspaceNotificationBadgeContext,
} from '@/utils/workspaceReviewBadge'
```

```ts
const pendingWorkspaceNotificationCount = ref(0)
const workspaceNotificationContext = computed<WorkspaceNotificationBadgeContext>(() => ({
  tenantId: userStore.getTenantId,
  role: userStore.getTenantRole,
  isSystemAdminUser: isPlatformAdmin.value,
  isPlatformWorkspaceDelegate: isPlatformWorkspaceDelegate.value,
}))
const loadPendingWorkspaceNotificationCount = createLatestWorkspaceNotificationLoader({
  fetchPendingReviews: () => tenantApi.tenantApplications('pending'),
  fetchPendingInvitations: () => tenantApi.myInvitations('pending'),
})
const showWorkspaceNotificationBadge = computed(() =>
  shouldShowWorkspaceNotificationBadge(
    workspaceNotificationContext.value,
    pendingWorkspaceNotificationCount.value
  )
)
```

```ts
watch(
  workspaceNotificationContext,
  async (context) => {
    const count = await loadPendingWorkspaceNotificationCount(context)
    if (count !== null) pendingWorkspaceNotificationCount.value = count
  },
  { immediate: true }
)
```

模板中的 `v-if="showWorkspaceReviewBadge"` 替换为：

```vue
v-if="showWorkspaceNotificationBadge"
```

保留现有 `.workspace-review-badge` 类名和样式，避免无意义视觉改动。

- [ ] **Step 4: 运行通知测试并确认通过**

Run: `cd frontend; node --test tests/workspaceReviewBadge.test.ts`

Expected: PASS，`9` 个测试通过、`0` 个失败。

- [ ] **Step 5: 运行前端构建验证类型和模板编译**

Run: `cd frontend; npm run build`

Expected: exit code `0`，`vue-tsc -b` 与 `vite build` 均成功；允许现有构建体积提示，不允许 TypeScript 或 Vue 模板错误。

- [ ] **Step 6: 检查最终差异没有扩展交互或后端改动**

Run: `git diff --check; git diff -- frontend/src/components/layout/Person.vue frontend/src/utils/workspaceReviewBadge.ts frontend/tests/workspaceReviewBadge.test.ts`

Expected: 仅统一计数、两个 API 接线、命名调整和测试变化；没有定时器、弹窗、路由、样式或后端文件修改。

- [ ] **Step 7: 提交头像接线与回归测试**

```powershell
git add -- frontend/src/components/layout/Person.vue frontend/tests/workspaceReviewBadge.test.ts
git diff --cached --check
git diff --cached --name-only
git commit -m "功能：头像红点提示待处理工作空间邀请"
```

Expected staged files: only the two files listed above.

---

### Task 3: 最终验证

**Files:**
- Verify only; no source changes expected.

**Interfaces:**
- Consumes: Task 1 and Task 2 committed behavior.
- Produces: fresh test, build, diff, and repository-status evidence.

- [ ] **Step 1: 重新运行专项测试**

Run: `cd frontend; node --test tests/workspaceReviewBadge.test.ts`

Expected: PASS，`9` 个测试通过、`0` 个失败。

- [ ] **Step 2: 重新运行前端生产构建**

Run: `cd frontend; npm run build`

Expected: exit code `0`，无 TypeScript 或 Vue 模板错误。

- [ ] **Step 3: 核对提交和剩余工作区改动**

Run: `git log -3 --oneline; git status --short`

Expected: 最上方包含本计划的两个中文功能提交；用户原有仪表板、日志和其他未跟踪文件仍保留且未被提交。
