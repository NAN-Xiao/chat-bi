# 看板编辑页返回上下文修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 看板编辑页点击返回时，恢复当前编辑看板的 `resourceId`、所属 `dashboardMode` 和侧栏选中状态。

**Architecture:** 继续以路由查询参数作为页面上下文唯一来源。在现有 `dashboardRouteMode.ts` 中提供普通看板查询参数构造函数，详情页编辑入口、资源树编辑入口和编辑器返回按钮共享该函数；编辑器负责读取并规范化当前模式，再通过 `baseParams` 传给工具栏。

**Tech Stack:** Vue 3、Vue Router 4、TypeScript、Node.js `node:test`/`assert`

## Global Constraints

- 普通看板路由上下文必须显式包含 `resourceId` 和 `dashboardMode`。
- 缺失或非法 `dashboardMode` 必须沿用现有规则解析为 `my`，不得静默替换为其他看板。
- 平台模板编辑继续返回 `/system/dashboard-template`，不得附加普通看板模式。
- 不依赖浏览器历史、Pinia 或会话存储保存来源页。
- 不改动看板权限、数据源绑定或模板管理逻辑。

---

### Task 1: 固化普通看板编辑与返回路由契约

**Files:**
- Modify: `frontend/src/views/dashboard/utils/dashboardRouteMode.ts`
- Create: `frontend/src/views/dashboard/utils/dashboardEditorNavigation.test.mjs`
- Modify: `frontend/src/views/dashboard/preview/SQPreviewHead.vue`
- Modify: `frontend/src/views/dashboard/common/ResourceTree.vue`
- Modify: `frontend/src/views/dashboard/editor/index.vue`
- Modify: `frontend/src/views/dashboard/editor/Toolbar.vue`

**Interfaces:**
- Consumes: `resolveOrdinaryDashboardMode(value: unknown, defaultMode?: boolean): 'default' | 'my'`
- Produces: `buildOrdinaryDashboardQuery(resourceId: string | number, dashboardMode: unknown): { resourceId: string | number; dashboardMode: 'default' | 'my' }`
- Produces: `baseParams.dashboardMode: 'default' | 'my'` for `Toolbar.vue`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/views/dashboard/utils/dashboardEditorNavigation.test.mjs`. Transpile and import `dashboardRouteMode.ts`, then assert:

```js
assert.deepEqual(buildOrdinaryDashboardQuery('dashboard-1', 'my'), {
  resourceId: 'dashboard-1',
  dashboardMode: 'my',
})
assert.deepEqual(buildOrdinaryDashboardQuery('dashboard-2', 'default'), {
  resourceId: 'dashboard-2',
  dashboardMode: 'default',
})
assert.deepEqual(buildOrdinaryDashboardQuery('dashboard-3', 'unknown'), {
  resourceId: 'dashboard-3',
  dashboardMode: 'my',
})
```

Read the four Vue sources and assert their wiring:

```js
assert.match(previewHeadSource, /buildOrdinaryDashboardQuery/)
assert.match(resourceTreeSource, /buildOrdinaryDashboardQuery/)
assert.match(editorSource, /dashboardMode:\s*resolveOrdinaryDashboardMode/)
assert.match(editorSource, /dashboardMode:\s*state\.dashboardMode/)
assert.match(toolbarSource, /buildOrdinaryDashboardQuery/)
assert.match(toolbarSource, /baseParams\?\.dashboardMode/)
assert.match(toolbarSource, /path:\s*['"]\/system\/dashboard-template['"]/)
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```powershell
Set-Location frontend
node src/views/dashboard/utils/dashboardEditorNavigation.test.mjs
```

Expected: FAIL because `buildOrdinaryDashboardQuery` is not exported and the Vue entry/return paths do not use it yet.

- [ ] **Step 3: Implement the shared query builder**

Append to `dashboardRouteMode.ts`:

```ts
export const buildOrdinaryDashboardQuery = (
  resourceId: string | number,
  dashboardMode: unknown
) => ({
  resourceId,
  dashboardMode: resolveOrdinaryDashboardMode(dashboardMode),
})
```

- [ ] **Step 4: Preserve the mode at both edit entrances**

In `SQPreviewHead.vue`, import `buildOrdinaryDashboardQuery` and replace the ordinary branch query with the mode already resolved by `SQPreviewShow.vue`:

```ts
buildOrdinaryDashboardQuery(
  props.dashboardInfo.id,
  props.dashboardInfo.dashboardMode
)
```

This source is required because `/default-dashboard/index` intentionally does not include `dashboardMode` in its URL.

In `ResourceTree.vue`, import the same helper and change `resourceEdit` to use:

```ts
query: buildOrdinaryDashboardQuery(resourceId, currentRouteDashboardScope())
```

- [ ] **Step 5: Carry the normalized mode through the editor**

In `editor/index.vue`, import `OrdinaryDashboardMode` and `resolveOrdinaryDashboardMode`. Add the state field:

```ts
dashboardMode: 'my' as OrdinaryDashboardMode,
```

Set it whenever route state is synchronized:

```ts
state.dashboardMode = resolveOrdinaryDashboardMode(query.dashboardMode)
```

Expose it to the toolbar:

```ts
dashboardMode: state.dashboardMode,
```

- [ ] **Step 6: Return with the current ID and original mode**

In `Toolbar.vue`, import `buildOrdinaryDashboardQuery`. Use it when a newly-created resource replaces the canvas route and when a normal dashboard returns to its detail page:

```ts
query: buildOrdinaryDashboardQuery(result.resourceId, props.baseParams?.dashboardMode)
```

```ts
query: dashboardInfo.value.id
  ? buildOrdinaryDashboardQuery(dashboardInfo.value.id, props.baseParams?.dashboardMode)
  : undefined,
```

Keep the existing platform-template branch unchanged.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run:

```powershell
Set-Location frontend
node src/views/dashboard/utils/dashboardEditorNavigation.test.mjs
node src/views/dashboard/utils/dashboardRouteMode.test.mjs
```

Expected: both commands print their pass messages and exit `0`.

- [ ] **Step 8: Run type and production build verification**

Run:

```powershell
Set-Location frontend
npm run build
```

Expected: `vue-tsc -b` and Vite production build exit `0` without TypeScript errors.

- [ ] **Step 9: Review the scoped diff**

Run:

```powershell
Set-Location ..
git diff --check -- frontend/src/views/dashboard/utils/dashboardRouteMode.ts frontend/src/views/dashboard/utils/dashboardEditorNavigation.test.mjs frontend/src/views/dashboard/preview/SQPreviewHead.vue frontend/src/views/dashboard/common/ResourceTree.vue frontend/src/views/dashboard/editor/index.vue frontend/src/views/dashboard/editor/Toolbar.vue
git diff -- frontend/src/views/dashboard/utils/dashboardRouteMode.ts frontend/src/views/dashboard/utils/dashboardEditorNavigation.test.mjs frontend/src/views/dashboard/preview/SQPreviewHead.vue frontend/src/views/dashboard/common/ResourceTree.vue frontend/src/views/dashboard/editor/index.vue frontend/src/views/dashboard/editor/Toolbar.vue
```

Expected: `git diff --check` has no output; diff contains only route-context propagation and its regression test. Do not stage or commit because the user did not request Git submission and the worktree already contains unrelated changes.
