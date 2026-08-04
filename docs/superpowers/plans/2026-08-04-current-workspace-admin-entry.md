# 当前工作空间管理入口权限 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让“工作空间管理”入口只在当前工作空间可管理时显示，并删除跨工作空间静默回退。

**Architecture:** `workspaceAdminEntry.ts` 复用 `canManageCurrentWorkspace(state)` 作为当前上下文权限边界，并封装解析与进入策略。`Menu.vue` 和 `MenuItem.vue` 共同使用该策略，不再从全部可管理工作空间中挑选目标或执行跨空间切换。

**Tech Stack:** Vue 3、TypeScript、Pinia、Node.js test runner

## Global Constraints

- 当前工作空间角色仅 `owner` 或 `admin` 可以显示管理入口。
- 不得自动替换为其他工作空间。
- 保留平台工作空间代理的当前代理空间管理能力。
- 不覆盖或提交工作区中已有的未提交修改。

---

### Task 1: 按当前工作空间权限生成管理入口

**Files:**
- Create: `frontend/src/components/layout/Menu.workspace-admin-permission.test.mjs`
- Create: `frontend/src/utils/workspaceAdminEntry.ts`
- Modify: `frontend/src/components/layout/Menu.vue:8`
- Modify: `frontend/src/components/layout/Menu.vue:100`
- Modify: `frontend/src/components/layout/MenuItem.vue:243`

**Interfaces:**
- Consumes: `canManageCurrentWorkspace(state) -> boolean`。
- Produces: `resolveCurrentWorkspaceAdminTenant(state)` 和 `enterCurrentWorkspaceAdmin(state, actions)`。
- Produces: `workspaceAdminMenu`，仅在当前工作空间可管理时返回菜单配置。

- [ ] **Step 1: Write the failing test**

```js
assert.equal(resolveCurrentWorkspaceAdminTenant(memberState), null)
assert.equal(resolveCurrentWorkspaceAdminTenant(adminState)?.id, 'tenant-current')
assert.doesNotMatch(source, /adminWorkspaceTenants\.value\[0\]/)
assert.equal(await enterCurrentWorkspaceAdmin(adminState, actions), true)
assert.equal(switchCount, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --experimental-strip-types --test src/components/layout/Menu.workspace-admin-permission.test.mjs`

Expected: FAIL with `ERR_MODULE_NOT_FOUND` because `workspaceAdminEntry.ts` does not exist.

- [ ] **Step 3: Write minimal implementation**

```ts
export const resolveCurrentWorkspaceAdminTenant = (state) => {
  const tenantId = String(state.getTenantId || '').trim()
  if (!tenantId || !canManageCurrentWorkspace(state)) return null
  return { id: tenantId, public_id: state.getTenantPublicId, name: state.getTenantName, role: state.getTenantRole }
}
```

Use the resolver in `workspaceAdminMenu`; use `enterCurrentWorkspaceAdmin` in `MenuItem.vue` so the click path records and navigates only the current workspace without calling `switchTenant()`.

- [ ] **Step 4: Run focused tests**

Run: `cd frontend && node --experimental-strip-types --test src/components/layout/Menu.workspace-admin-permission.test.mjs src/components/layout/Menu.layout.test.mjs`

Expected: both tests PASS with zero failures.

- [ ] **Step 5: Run frontend verification**

Run: `cd frontend && npx vue-tsc -b --pretty false`

Expected: exit code 0.

- [ ] **Step 6: Review the final diff**

Run: `git diff --check` and `git diff -- frontend/src/components/layout/Menu.vue frontend/src/components/layout/MenuItem.vue frontend/src/utils/workspaceAdminEntry.ts frontend/src/components/layout/Menu.workspace-admin-permission.test.mjs`

Expected: no whitespace errors and no unrelated changes in the implementation files.
