# 工作空间待审核通知头像红点实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 当当前工作空间存在待审核成员申请时，仅为空间拥有者或管理员在全局顶部头像右上角展示纯红点。

**Architecture:** 将权限、显示条件和“仅接受最新请求”逻辑放入独立纯 TypeScript 工具，使用 Node 内置测试运行器完成 TDD；`Person.vue` 只负责监听当前工作空间上下文、调用现有接口并渲染局部红点样式。通用 `UserAvatar` 保持业务无关。

**Tech Stack:** Vue 3、TypeScript、Pinia、Element Plus Secondary、Node.js `node:test`、Less。

## Global Constraints

- 仅工作空间角色 `owner` 或 `admin` 可展示红点。
- 平台管理员、平台工作空间代理、普通成员和无工作空间用户不展示红点。
- 红点不显示数字，不改变头像点击或菜单行为。
- 不新增后端接口，不引入轮询、WebSocket 或全局通知 Store。
- 请求失败时隐藏红点且不弹出错误消息。
- 快速切换工作空间时，旧请求不得覆盖新工作空间状态。
- 不执行 Git 提交，除非用户明确要求。

---

### Task 1: 待审核红点状态工具

**Files:**
- Create: `frontend/src/utils/workspaceReviewBadge.ts`
- Create: `frontend/tests/workspaceReviewBadge.test.ts`

**Interfaces:**
- Consumes: `canManageWorkspaceRole(role?: string | null): boolean` from `frontend/src/utils/workspacePermission.ts`。
- Produces: `WorkspaceReviewBadgeContext`、`shouldLoadWorkspaceReviews(context): boolean`、`shouldShowWorkspaceReviewBadge(context, pendingCount): boolean`、`createLatestWorkspaceReviewLoader(fetchPending): (context) => Promise<number | null>`。

- [x] **Step 1: 编写失败的权限与显示条件测试**

```ts
import assert from 'node:assert/strict'
import test from 'node:test'

import {
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
    shouldLoadWorkspaceReviews({ tenantId: '1', role: 'admin', isPlatformWorkspaceDelegate: true }),
    false
  )
})

test('仅管理角色存在待审核申请时显示红点', () => {
  assert.equal(shouldShowWorkspaceReviewBadge(owner, 1), true)
  assert.equal(shouldShowWorkspaceReviewBadge(admin, 2), true)
  assert.equal(shouldShowWorkspaceReviewBadge(owner, 0), false)
  assert.equal(shouldShowWorkspaceReviewBadge({ tenantId: '1', role: 'member' }, 1), false)
})
```

- [x] **Step 2: 运行测试确认因模块缺失而失败**

Run: `cd frontend; node --test tests/workspaceReviewBadge.test.ts`

Expected: FAIL，错误包含 `ERR_MODULE_NOT_FOUND` 或找不到 `workspaceReviewBadge.ts`。

- [x] **Step 3: 实现最小权限与显示判断**

```ts
import { canManageWorkspaceRole } from './workspacePermission.ts'

export interface WorkspaceReviewBadgeContext {
  tenantId?: string | number | null
  role?: string | null
  isSystemAdminUser?: boolean
  isPlatformWorkspaceDelegate?: boolean
}

export const shouldLoadWorkspaceReviews = (context: WorkspaceReviewBadgeContext) =>
  Boolean(context.tenantId) &&
  !context.isSystemAdminUser &&
  !context.isPlatformWorkspaceDelegate &&
  canManageWorkspaceRole(context.role)

export const shouldShowWorkspaceReviewBadge = (
  context: WorkspaceReviewBadgeContext,
  pendingCount: number
) => shouldLoadWorkspaceReviews(context) && pendingCount > 0
```

- [x] **Step 4: 运行测试确认权限与显示判断通过**

Run: `cd frontend; node --test tests/workspaceReviewBadge.test.ts`

Expected: PASS，2 个测试通过。

- [x] **Step 5: 编写失败的加载、异常和竞态测试**

```ts
import { createLatestWorkspaceReviewLoader } from '../src/utils/workspaceReviewBadge.ts'

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
```

- [x] **Step 6: 运行测试确认加载器尚未实现而失败**

Run: `cd frontend; node --test tests/workspaceReviewBadge.test.ts`

Expected: FAIL，错误指出 `createLatestWorkspaceReviewLoader` 未导出。

- [x] **Step 7: 实现仅接受最新结果的加载器**

```ts
interface WorkspaceReviewApplication {
  status?: string | null
}

type FetchPendingWorkspaceReviews = () => Promise<WorkspaceReviewApplication[] | null | undefined>

export const createLatestWorkspaceReviewLoader = (fetchPending: FetchPendingWorkspaceReviews) => {
  let latestRequestId = 0

  return async (context: WorkspaceReviewBadgeContext): Promise<number | null> => {
    const requestId = ++latestRequestId
    if (!shouldLoadWorkspaceReviews(context)) return 0

    try {
      const rows = (await fetchPending()) || []
      if (requestId !== latestRequestId) return null
      return rows.filter((item) => item.status === 'pending').length
    } catch {
      if (requestId !== latestRequestId) return null
      return 0
    }
  }
}
```

- [x] **Step 8: 运行完整工具测试确认通过**

Run: `cd frontend; node --test tests/workspaceReviewBadge.test.ts`

Expected: PASS，4 个测试通过且无警告。

---

### Task 2: 顶部头像接入待审核红点

**Files:**
- Modify: `frontend/src/components/layout/Person.vue:1`
- Verify: `frontend/src/components/layout/LayoutDsl.vue:277`

**Interfaces:**
- Consumes: `tenantApi.tenantApplications('pending')`、`createLatestWorkspaceReviewLoader(...)`、`shouldShowWorkspaceReviewBadge(...)`。
- Produces: `showWorkspaceReviewBadge` 计算状态以及 `.avatar-badge-wrapper`、`.workspace-review-badge` 局部样式。

- [x] **Step 1: 在 `Person.vue` 接入监听与加载逻辑**

```ts
import { ref, computed, onMounted, watch } from 'vue'
import { tenantApi, type TenantInfo } from '@/api/tenant'
import {
  createLatestWorkspaceReviewLoader,
  shouldShowWorkspaceReviewBadge,
  type WorkspaceReviewBadgeContext,
} from '@/utils/workspaceReviewBadge'

const pendingWorkspaceReviewCount = ref(0)
const workspaceReviewContext = computed<WorkspaceReviewBadgeContext>(() => ({
  tenantId: userStore.getTenantId,
  role: userStore.getTenantRole,
  isSystemAdminUser: isPlatformAdmin.value,
  isPlatformWorkspaceDelegate: isPlatformWorkspaceDelegate.value,
}))
const loadPendingWorkspaceReviewCount = createLatestWorkspaceReviewLoader(() =>
  tenantApi.tenantApplications('pending')
)
const showWorkspaceReviewBadge = computed(() =>
  shouldShowWorkspaceReviewBadge(workspaceReviewContext.value, pendingWorkspaceReviewCount.value)
)

watch(
  workspaceReviewContext,
  async (context) => {
    const count = await loadPendingWorkspaceReviewCount(context)
    if (count !== null) pendingWorkspaceReviewCount.value = count
  },
  { immediate: true }
)
```

- [x] **Step 2: 包裹顶部头像并渲染纯红点**

```vue
<span class="avatar-badge-wrapper">
  <UserAvatar :name="name" :account="account" :uid="userStore.getUid" :size="32" />
  <span
    v-if="showWorkspaceReviewBadge"
    class="workspace-review-badge"
    role="status"
    :aria-label="t('tenant_overview.todo_pending_member_application_count')"
  ></span>
</span>
```

- [x] **Step 3: 添加不拦截点击的局部样式**

```less
.avatar-badge-wrapper {
  position: relative;
  display: inline-flex;
  flex: 0 0 auto;
}

.workspace-review-badge {
  position: absolute;
  top: -1px;
  right: -1px;
  width: 8px;
  height: 8px;
  border: 2px solid var(--theme-panel-bg);
  border-radius: 50%;
  background: var(--ed-color-danger, #f56c6c);
  pointer-events: none;
  box-sizing: content-box;
  z-index: 1;
}
```

- [x] **Step 4: 运行工具测试防止逻辑回归**

Run: `cd frontend; node --test tests/workspaceReviewBadge.test.ts`

Expected: PASS，4 个测试通过。

- [x] **Step 5: 运行 TypeScript 与生产构建验证**

Run: `cd frontend; npm run build`

Expected: exit code 0，`vue-tsc -b` 与 `vite build` 均成功。

- [x] **Step 6: 检查最终差异与格式问题**

Run: `git diff --check -- frontend/src/utils/workspaceReviewBadge.ts frontend/tests/workspaceReviewBadge.test.ts frontend/src/components/layout/Person.vue`

Expected: exit code 0，无空白错误。
