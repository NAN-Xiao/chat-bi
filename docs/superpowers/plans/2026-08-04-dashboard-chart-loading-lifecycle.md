# Dashboard Chart Loading Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复看板图表卡片“数据加载中”遮罩闪回或持续显示的问题。

**Architecture:** 统一看板图表快照判断协议，让预览页、编辑页和报表包装组件都复用 `hasDashboardChartSnapshot`。同时调整 `ChartComponent` 的首帧 ready 握手，保证已经提交到 active layer 的可渲染内容不会因为连续 resize/watch 重绘而无限等待。

**Tech Stack:** Vue 3 SFC, TypeScript, Node `node:test` source contract tests.

## Global Constraints

- 修改源代码和测试必须在 linked worktree `D:\AIWork3\chat-bi\.worktrees\codex-dashboard-chart-loading-lifecycle` 的 `codex/dashboard-chart-loading-lifecycle` 分支中完成。
- 不添加业务领域特例，不硬编码 datasource、字段、图表 ID 或看板 ID。
- 不通过隐藏 fallback 替换字段或绕过权限校验；仅修正通用加载生命周期。
- 生产代码修改前先写失败测试，并确认测试因目标问题失败。

---

### Task 1: Unify Snapshot Protocol

**Files:**
- Modify: `frontend/src/views/dashboard/utils/dashboardChartLifecycle.test.mjs`
- Modify: `frontend/src/views/dashboard/preview/SQPreviewShow.vue`
- Modify: `frontend/src/views/dashboard/editor/index.vue`
- Modify: `frontend/src/views/dashboard/preview/SQComponentWrapper.vue`
- Modify: `frontend/src/views/dashboard/utils/dashboardChartLifecycle.ts`

**Interfaces:**
- Consumes: `hasDashboardChartSnapshot(viewInfo: Record<string, any>): boolean`
- Produces: all dashboard refresh callers use the same snapshot definition for rows, successful empty results, and refreshed field-only results.

- [ ] **Step 1: Write failing tests**

Add assertions that preview/editor/wrapper import and use `hasDashboardChartSnapshot`, and add direct cases proving successful refreshed empty or field-only results are snapshots.

- [ ] **Step 2: Run targeted tests and confirm RED**

Run: `node --test src/views/dashboard/utils/dashboardChartLifecycle.test.mjs`

Expected: FAIL because consumers still define local row-only `hasChartSnapshot`.

- [ ] **Step 3: Implement minimal code**

Import `hasDashboardChartSnapshot` in the affected consumers, replace local row-only snapshot checks, and update cache-result usability to treat successful field-only results as usable.

- [ ] **Step 4: Run targeted tests and confirm GREEN**

Run: `node --test src/views/dashboard/utils/dashboardChartLifecycle.test.mjs src/views/dashboard/preview/SQPreviewShow.loading-state.test.mjs`

Expected: PASS.

### Task 2: Bound Render Ready Handshake

**Files:**
- Modify: `frontend/src/views/chat/component/ChartComponent.atomic-render.test.mjs`
- Modify: `frontend/src/views/chat/component/ChartComponent.vue`

**Interfaces:**
- Consumes: committed chart active layer and existing `render-ready` event.
- Produces: a pending `render-ready` event is not cancelled merely because a resize render is queued after a valid active layer exists.

- [ ] **Step 1: Write failing tests**

Add source assertions for an `hasActiveRenderedLayer` helper and for `scheduleRenderChart` preserving pending ready when an active rendered layer exists.

- [ ] **Step 2: Run targeted tests and confirm RED**

Run: `node --test src/views/chat/component/ChartComponent.atomic-render.test.mjs`

Expected: FAIL because current `scheduleRenderChart` always cancels pending ready and `scheduleRenderReady` waits on `!renderTimer`.

- [ ] **Step 3: Implement minimal code**

Add `hasActiveRenderedLayer`, make `scheduleRenderReady` emit when the active rendered layer exists, and only cancel pending ready on new render scheduling when there is no committed rendered layer to show.

- [ ] **Step 4: Run targeted tests and confirm GREEN**

Run: `node --test src/views/chat/component/ChartComponent.atomic-render.test.mjs`

Expected: PASS.

### Task 3: Regression Verification

**Files:**
- Test only: targeted frontend tests and git diff.

- [ ] **Step 1: Run dashboard/chart regression tests**

Run: `node --test src/views/dashboard/utils/dashboardChartLifecycle.test.mjs src/views/dashboard/preview/SQPreviewShow.loading-state.test.mjs src/views/dashboard/preview/SQPreviewShow.permission-refresh.test.mjs src/views/dashboard/components/sq-view/index.state-machine.test.mjs src/views/dashboard/components/sq-view/index.empty-state.test.mjs src/views/chat/component/ChartComponent.atomic-render.test.mjs src/views/chat/component/ChartComponent.resize.test.mjs`

Expected: PASS.

- [ ] **Step 2: Inspect diff**

Run: `git diff -- frontend/src/views/dashboard frontend/src/views/chat/component docs/superpowers/plans/2026-08-04-dashboard-chart-loading-lifecycle.md`

Expected: changes are scoped to lifecycle tests, snapshot protocol consumers, render-ready handshake, and this plan.
