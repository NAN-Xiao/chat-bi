# 看板无查看权限后停止自动刷新实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 看板图表在当前页面生命周期内返回 `permission_denied` 后停止自动刷新与失败重试，并在完整加载时重新判权。

**Architecture:** 预览页和编辑页各自维护仅存在于组件内存中的图表 ID 集合。缓存查询或数据库查询返回权限拒绝时记录 ID，后续自动调度和查询队列统一排除；完整加载入口清空集合，不向 `viewInfo`、草稿或数据库写入新的控制字段。

**Tech Stack:** Vue 3 `<script setup lang="ts">`、TypeScript、Node.js `node:test` / `node:assert` 源码契约测试、Vite、`vue-tsc`

## Global Constraints

- 权限拒绝只在当前页面生命周期内阻止自动刷新和失败重试。
- 用户手动刷新、切换看板或重新进入页面后必须重新向后端判定权限。
- 不修改后端权限契约，不持久化权限终止集合。
- 不改变缓存未命中、查询繁忙、网络异常等非权限错误的现有刷新策略。
- 代码注释、测试说明和 Git 提交信息使用中文。

---

## 文件结构

- `frontend/src/views/dashboard/preview/SQPreviewShow.vue`：预览页权限终止集合、自动刷新候选过滤、完整加载重置。
- `frontend/src/views/dashboard/preview/SQPreviewShow.permission-refresh.test.mjs`：预览页权限拒绝自动刷新回归测试。
- `frontend/src/views/dashboard/editor/index.vue`：编辑页权限终止集合、缓存/数据库查询终止与短时重试过滤、路由加载重置。
- `frontend/src/views/dashboard/editor/index.permission-refresh.test.mjs`：编辑页权限拒绝自动重试回归测试。

### Task 1: 预览页停止权限拒绝图表的自动刷新

**Files:**
- Create: `frontend/src/views/dashboard/preview/SQPreviewShow.permission-refresh.test.mjs`
- Modify: `frontend/src/views/dashboard/preview/SQPreviewShow.vue:69-80,343-356,587-750,767-826`

**Interfaces:**
- Consumes: `isPermissionDeniedResult(result: any): boolean`、`collectNormalizedDashboardCharts(): Array<{ component: any; viewInfo: any }>`。
- Produces: `markPermissionDeniedChart(entry): void`、`isPermissionDeniedChart(entry): boolean`、`resetPermissionDeniedCharts(): void`，仅供 `SQPreviewShow.vue` 内部调用。

- [ ] **Step 1: 编写失败的源码契约测试**

创建测试，读取 `SQPreviewShow.vue` 并断言以下完整行为：

```js
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'SQPreviewShow.vue'), 'utf8')
const autoRefresh = source.match(/function scheduleNextDashboardAutoRefresh\([\s\S]*?\n\}/)?.[0] || ''
const refreshCharts = source.match(/async function refreshDashboardCharts\([\s\S]*?\n\}/)?.[0] || ''
const loadCanvas = source.match(/const loadCanvasData = \(params: any\) => \{([\s\S]*?)\r?\n\}/)?.[0] || ''

assert.match(source, /const permissionDeniedChartIds = new Set<string>\(\)/)
assert.match(source, /function markPermissionDeniedChart\(entry: [^)]*\)/)
assert.match(source, /function isPermissionDeniedChart\(entry: [^)]*\)/)
assert.match(source, /function resetPermissionDeniedCharts\(\)/)
assert.match(autoRefresh, /filter\(\(entry\) =>[\s\S]*?!isPermissionDeniedChart\(entry\)/)
assert.match(refreshCharts, /filter\(\(entry\) =>[\s\S]*?!isPermissionDeniedChart\(entry\)/)
assert.match(
  refreshCharts,
  /isPermissionDeniedResult\(cachedResult\)[\s\S]*?markPermissionDeniedChart\(entry\)[\s\S]*?applyChartResult\(viewInfo, cachedResult\)/
)
assert.match(
  refreshCharts,
  /isPermissionDeniedResult\(result\)[\s\S]*?markPermissionDeniedChart\(entry\)[\s\S]*?applyChartResult\(viewInfo, result\)/
)
assert.match(loadCanvas, /resetPermissionDeniedCharts\(\)/)
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```powershell
node --test frontend/src/views/dashboard/preview/SQPreviewShow.permission-refresh.test.mjs
```

Expected: FAIL，首个失败断言指出缺少 `permissionDeniedChartIds`。

- [ ] **Step 3: 实现预览页内存终止集合**

在刷新状态变量附近加入：

```ts
const permissionDeniedChartIds = new Set<string>()

function chartEntryId(entry: { component: any; viewInfo: any }) {
  const id = entry?.component?.id
  return id === undefined || id === null ? '' : String(id)
}

function markPermissionDeniedChart(entry: { component: any; viewInfo: any }) {
  const id = chartEntryId(entry)
  if (id) permissionDeniedChartIds.add(id)
}

function isPermissionDeniedChart(entry: { component: any; viewInfo: any }) {
  const id = chartEntryId(entry)
  return Boolean(id && permissionDeniedChartIds.has(id))
}

function resetPermissionDeniedCharts() {
  permissionDeniedChartIds.clear()
}
```

在 `scheduleNextDashboardAutoRefresh` 中先过滤条目，再映射 `viewInfo`：

```ts
const refreshableViewInfos = collectNormalizedDashboardCharts()
  .filter(
    (entry) =>
      entry.viewInfo &&
      canLookupChartCache(entry.viewInfo) &&
      !isPermissionDeniedChart(entry)
  )
  .map((entry) => entry.viewInfo)
```

在 `refreshDashboardCharts` 的查询队列入口使用相同终止条件：

```ts
const chartEntries = allChartEntries.filter(
  (entry) => canLookupChartCache(entry.viewInfo) && !isPermissionDeniedChart(entry)
)
```

缓存结果先处理权限拒绝，不再加入数据库刷新队列：

```ts
if (isPermissionDeniedResult(cachedResult)) {
  markPermissionDeniedChart(entry)
  applyChartResult(viewInfo, cachedResult)
} else if (
  isDashboardCacheMiss(cachedResult) ||
  cachedResult?.status === 'failed' ||
  !hasUsableResultSnapshot(cachedResult)
) {
  databaseRefreshEntries.push(entry)
} else {
  if (isMixedChart(viewInfo)) {
    applyMixedChartResult(viewInfo, cachedResult)
    markChartSnapshotRefreshed(viewInfo, resultRefreshedAt(cachedResult))
  } else {
    applyChartResult(viewInfo, cachedResult)
  }
}
```

数据库结果返回权限拒绝时先记录组件 ID：

```ts
if (isPermissionDeniedResult(result)) {
  markPermissionDeniedChart(entry)
  applyChartResult(viewInfo, result)
}
```

在 `loadCanvasData` 接受新一轮完整加载并调用 `cancelDashboardWork()` 后清空集合：

```ts
cancelDashboardWork()
resetPermissionDeniedCharts()
chartRefreshRetryCount = 0
```

- [ ] **Step 4: 运行预览页测试并确认通过**

Run:

```powershell
node --test frontend/src/views/dashboard/preview/SQPreviewShow.permission-refresh.test.mjs frontend/src/views/dashboard/preview/SQPreviewShow.loading-state.test.mjs
```

Expected: PASS，2 个测试文件均无失败。

- [ ] **Step 5: 提交预览页修复**

```powershell
git add frontend/src/views/dashboard/preview/SQPreviewShow.vue frontend/src/views/dashboard/preview/SQPreviewShow.permission-refresh.test.mjs
git commit -m "修复：无查看权限图表停止自动刷新"
```

### Task 2: 编辑页停止权限拒绝图表的自动重试

**Files:**
- Create: `frontend/src/views/dashboard/editor/index.permission-refresh.test.mjs`
- Modify: `frontend/src/views/dashboard/editor/index.vue:52-61,449-605,643-648`

**Interfaces:**
- Consumes: Task 1 相同命名和语义的组件内私有帮助函数，但编辑页维护独立集合，不跨组件共享状态。
- Produces: 编辑页缓存查询与数据库查询的权限终止行为；不导出公共 API。

- [ ] **Step 1: 编写失败的编辑页源码契约测试**

```js
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'index.vue'), 'utf8')
const refreshCharts = source.match(/async function refreshEditorCharts\([\s\S]*?\n\}/)?.[0] || ''
const loadCanvas = source.match(/const loadCanvasFromRoute = async \(\) => \{([\s\S]*?)\r?\n\}/)?.[0] || ''

assert.match(source, /const permissionDeniedChartIds = new Set<string>\(\)/)
assert.match(refreshCharts, /filter\(\(entry\) =>[\s\S]*?!isPermissionDeniedChart\(entry\)/)
assert.match(
  refreshCharts,
  /isPermissionDeniedResult\(cachedResult\)[\s\S]*?markPermissionDeniedChart\(entry\)[\s\S]*?applyChartResult\(viewInfo, cachedResult\)/
)
assert.match(
  refreshCharts,
  /isPermissionDeniedResult\(result\)[\s\S]*?markPermissionDeniedChart\(entry\)[\s\S]*?applyChartResult\(viewInfo, result\)/
)
const permissionBranch = refreshCharts.match(
  /if \(isPermissionDeniedResult\(result\)\) \{([\s\S]*?)\} else \{/
)?.[1] || ''
assert.doesNotMatch(permissionBranch, /transientPendingCount \+= 1/)
assert.match(loadCanvas, /resetPermissionDeniedCharts\(\)/)
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```powershell
node --test frontend/src/views/dashboard/editor/index.permission-refresh.test.mjs
```

Expected: FAIL，首个失败断言指出缺少 `permissionDeniedChartIds`。

- [ ] **Step 3: 实现编辑页终止集合与权限分支**

在编辑页加入独立集合和四个私有帮助函数：

```ts
const permissionDeniedChartIds = new Set<string>()

function chartEntryId(entry: { component: any; viewInfo: any }) {
  const id = entry?.component?.id
  return id === undefined || id === null ? '' : String(id)
}

function markPermissionDeniedChart(entry: { component: any; viewInfo: any }) {
  const id = chartEntryId(entry)
  if (id) permissionDeniedChartIds.add(id)
}

function isPermissionDeniedChart(entry: { component: any; viewInfo: any }) {
  const id = chartEntryId(entry)
  return Boolean(id && permissionDeniedChartIds.has(id))
}

function resetPermissionDeniedCharts() {
  permissionDeniedChartIds.clear()
}
```

查询队列过滤增加：

```ts
const chartEntries = collectDashboardCharts(componentData.value).filter(
  (entry) =>
    !isPermissionDeniedChart(entry) &&
    Boolean(
      isMixedChart(entry.viewInfo)
        ? canRefreshMixedChart(entry.viewInfo)
        : !isExternalSnapshotChart(entry.viewInfo) &&
          entry.viewInfo?.datasource &&
          entry.viewInfo?.sql?.trim()
    )
)
```

缓存权限拒绝使用 `withAutoChartUpdate` 写回展示状态，但不加入数据库队列：

```ts
if (isPermissionDeniedResult(cachedResult)) {
  markPermissionDeniedChart(entry)
  withAutoChartUpdate(() => applyChartResult(viewInfo, cachedResult))
} else if (
  isDashboardCacheMiss(cachedResult) ||
  cachedResult?.status === 'failed' ||
  !hasUsableResultSnapshot(cachedResult)
) {
  if (isMixedChart(viewInfo) || !hasChartSnapshot(viewInfo)) {
    databaseRefreshEntries.push(entry)
  }
} else {
  withAutoChartUpdate(() => {
    if (isMixedChart(viewInfo)) {
      applyMixedChartResult(viewInfo, cachedResult)
      markChartSnapshotRefreshed(viewInfo, resultRefreshedAt(cachedResult))
    } else {
      applyChartResult(viewInfo, cachedResult)
    }
  })
}
```

数据库失败分支只给非权限失败累计短时重试：

```ts
if (result?.status === 'failed') {
  if (isPermissionDeniedResult(result)) {
    markPermissionDeniedChart(entry)
    applyChartResult(viewInfo, result)
  } else {
    keepChartSnapshotOrLoading(viewInfo)
    if (!hasChartSnapshot(viewInfo)) {
      transientPendingCount += 1
    }
  }
} else {
  if (isMixedChart(viewInfo)) {
    applyMixedChartResult(viewInfo, result)
    markChartSnapshotRefreshed(viewInfo, resultRefreshedAt(result))
  } else {
    applyChartResult(viewInfo, result)
  }
}
```

在 `loadCanvasFromRoute` 创建新加载版本并取消旧刷新后清空集合：

```ts
const loadVersion = ++routeLoadVersion
persistCanvasDraft()
cancelDashboardChartRefresh()
resetPermissionDeniedCharts()
chartRefreshRetryCount = 0
```

- [ ] **Step 4: 运行编辑页测试并确认通过**

Run:

```powershell
node --test frontend/src/views/dashboard/editor/index.permission-refresh.test.mjs frontend/src/views/dashboard/preview/SQPreviewShow.permission-refresh.test.mjs
```

Expected: PASS，编辑页与预览页权限终止契约均通过。

- [ ] **Step 5: 运行完整前端验证**

Run:

```powershell
node --test frontend/src/views/dashboard/preview/*.test.mjs frontend/src/views/dashboard/editor/*.test.mjs
npm --prefix frontend run build
git diff --check
```

Expected: 所有 Node 测试 PASS；`vue-tsc -b && vite build` 退出码为 0；`git diff --check` 无输出。

- [ ] **Step 6: 提交编辑页修复**

```powershell
git add frontend/src/views/dashboard/editor/index.vue frontend/src/views/dashboard/editor/index.permission-refresh.test.mjs
git commit -m "修复：编辑页权限拒绝后停止重试"
```
