# 报表解读历史隔离实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将报表解读历史按工作空间、用户、看板和解读目标隔离，消除跨用户、跨看板及跨图表串记录问题。

**Architecture:** 保留现有浏览器 `localStorage` 存储，将历史工具改为必须接收显式作用域并生成 v2 独立键；组件从用户 Store、看板数据和当前组件状态构造作用域。旧 v1 全局键在新版逻辑首次运行时直接清除，必需标识不完整时失败关闭。

**Tech Stack:** Vue 3、TypeScript、Pinia、Node.js `assert`、esbuild。

## Global Constraints

- 每个隔离范围最多保留 4 条历史，TTL 固定为 3 天。
- 旧版全局历史不迁移，直接删除。
- 不新增后端模型、数据库迁移或接口。
- 不修改报表解读提示词、数据上下文和流式接口。
- 代码注释和新增文档使用中文。

---

### Task 1: 历史存储作用域

**Files:**
- Modify: `frontend/src/views/dashboard/preview/reportPromptHistory.ts`
- Test: `frontend/src/views/dashboard/preview/reportPromptHistory.test.mjs`

**Interfaces:**
- Produces: `ReportPromptHistoryScope`，包含 `tenantId`、`userUid`、`dashboardUid`、`targetScope`。
- Produces: `buildReportPromptHistoryStorageKey(scope): string | null`。
- Changes: `loadReportPromptHistory(storage, scope, now?)`。
- Changes: `saveReportPromptHistory(storage, scope, input, now?)`。

- [ ] **Step 1: 编写隔离行为的失败测试**

在测试中构造用户、看板和目标不同的作用域，断言：

```javascript
const dashboardScope = {
  tenantId: 'tenant-1',
  userUid: 'user-a',
  dashboardUid: 'dashboard-1',
  targetScope: 'dashboard',
}
const otherUserScope = { ...dashboardScope, userUid: 'user-b' }
const chartScope = { ...dashboardScope, targetScope: 'chart:chart-1' }

saveReportPromptHistory(storage, dashboardScope, '整板问题', now)
assert.deepEqual(loadReportPromptHistory(storage, dashboardScope, now).map((item) => item.text), ['整板问题'])
assert.deepEqual(loadReportPromptHistory(storage, otherUserScope, now), [])
assert.deepEqual(loadReportPromptHistory(storage, chartScope, now), [])
```

补充断言：不同工作空间、不同看板相互隔离；缺失 UID 时不写入；调用 v2 逻辑后 v1 键被删除。

- [ ] **Step 2: 运行测试并确认因接口尚未支持作用域而失败**

Run: `node src/views/dashboard/preview/reportPromptHistory.test.mjs`（工作目录：`frontend`）

Expected: FAIL，现有函数把作用域对象当作旧的时间参数，或不同作用域读到同一份全局历史。

- [ ] **Step 3: 实现 v2 隔离键和失败关闭**

在历史工具中新增：

```typescript
export type ReportPromptHistoryScope = {
  tenantId: string | number | null | undefined
  userUid: string | number | null | undefined
  dashboardUid: string | number | null | undefined
  targetScope: string | null | undefined
}

export const REPORT_PROMPT_HISTORY_STORAGE_KEY = 'dashboard_report_prompt_history:v1'
export const REPORT_PROMPT_HISTORY_STORAGE_PREFIX = 'dashboard_report_prompt_history:v2'

export function buildReportPromptHistoryStorageKey(
  scope: ReportPromptHistoryScope
): string | null {
  const parts = [scope.tenantId, scope.userUid, scope.dashboardUid, scope.targetScope]
    .map((value) => `${value ?? ''}`.trim())
  if (parts.some((value) => !value)) return null
  return `${REPORT_PROMPT_HISTORY_STORAGE_PREFIX}:${parts.map(encodeURIComponent).join(':')}`
}
```

`loadReportPromptHistory` 和 `saveReportPromptHistory` 每次先删除 v1 键，只对构造成功的 v2 键读写；空作用域返回空数组且不创建键。原有解析、TTL、去重和数量限制逻辑保持不变。

- [ ] **Step 4: 运行历史工具测试并确认通过**

Run: `node src/views/dashboard/preview/reportPromptHistory.test.mjs`（工作目录：`frontend`）

Expected: PASS，输出 `report prompt history tests passed`。

### Task 2: 看板和图表入口接入作用域

**Files:**
- Modify: `frontend/src/views/dashboard/preview/SQPreviewHead.vue`
- Modify: `frontend/src/views/dashboard/preview/SQComponentWrapper.vue`
- Test: `frontend/src/views/dashboard/preview/reportPromptHistory.test.mjs`

**Interfaces:**
- Consumes: Task 1 的 `ReportPromptHistoryScope`、`loadReportPromptHistory`、`saveReportPromptHistory`。
- Produces: 整板目标 `dashboard`、单图目标 `chart:<configItem.id>`、Tab 目标 `tab:<configItem.id>:<activeTabName>`。

- [ ] **Step 1: 编写两个入口显式传入作用域的失败测试**

扩展组件源码断言，要求两个入口的加载和保存均传入 `reportHistoryScope.value`，并要求目标规则存在：

```javascript
assert.match(component.source, /loadReportPromptHistory\(window\.localStorage, reportHistoryScope\.value\)/)
assert.match(component.source, /saveReportPromptHistory\(window\.localStorage, reportHistoryScope\.value,/)
```

整板入口断言包含 `targetScope: 'dashboard'`；图表入口断言包含 `chart:` 和 `tab:` 两种目标构造。

- [ ] **Step 2: 运行测试并确认因组件仍使用旧接口而失败**

Run: `node src/views/dashboard/preview/reportPromptHistory.test.mjs`（工作目录：`frontend`）

Expected: FAIL，提示入口未传入 `reportHistoryScope.value`。

- [ ] **Step 3: 接入用户、看板和目标作用域**

两个组件引入 `useUserStore` 与 `ReportPromptHistoryScope`，创建用户 Store。整板入口使用：

```typescript
const reportHistoryScope = computed<ReportPromptHistoryScope>(() => ({
  tenantId: userStore.getTenantId,
  userUid: userStore.getUid,
  dashboardUid: props.dashboardInfo?.id,
  targetScope: 'dashboard',
}))
```

图表入口根据组件类型使用：

```typescript
const reportHistoryTargetScope = computed(() => {
  if (props.configItem?.component === 'SQTab') {
    return `tab:${props.configItem?.id || ''}:${props.configItem?.activeTabName || ''}`
  }
  return `chart:${props.configItem?.id || ''}`
})
```

加载和保存函数统一传入 `reportHistoryScope.value`。目标字段缺失时由历史工具失败关闭。

- [ ] **Step 4: 运行专项测试和类型检查**

Run: `node src/views/dashboard/preview/reportPromptHistory.test.mjs`（工作目录：`frontend`）

Expected: PASS。

Run: `npm run typecheck`（工作目录：`frontend`）

Expected: PASS；如果仓库没有 `typecheck` 脚本，则运行 `npm run lint` 并记录替代验证结果。

- [ ] **Step 5: 检查变更范围**

Run: `git diff --check -- frontend/src/views/dashboard/preview/reportPromptHistory.ts frontend/src/views/dashboard/preview/reportPromptHistory.test.mjs frontend/src/views/dashboard/preview/SQPreviewHead.vue frontend/src/views/dashboard/preview/SQComponentWrapper.vue`

Expected: 无输出且退出码为 0；变更不包含后端接口、提示词或用户已有的无关文件。
