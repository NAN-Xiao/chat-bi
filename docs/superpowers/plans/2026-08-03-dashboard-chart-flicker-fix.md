# Dashboard Chart Flicker Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent default-dashboard charts from repeatedly showing an empty-axis frame while preserving a full loading state before first data and a non-blocking refresh state after data exists.

**Architecture:** Keep the current asynchronous `includeData: false` loading pipeline and its request-version protection. Deduplicate resize notifications at the preview boundary, make card frame measurement report whether dimensions actually changed, and preserve the existing loading-state contract. For non-table charts, render each replacement into a hidden component-owned staging layer and atomically reveal the completed layer before destroying the previous instance and layer. Keep the table on its own stable layer so S2 continues to resize in place and cannot destroy a newly mounted G2 chart during type changes.

**Tech Stack:** Vue 3 Composition API, TypeScript, browser `ResizeObserver`, Node.js built-in test runner, Vite.

## Global Constraints

- The fix is datasource-agnostic and contains no business-field, metric, or dashboard-ID special cases.
- No silent field, axis, datasource, or semantic fallback is introduced.
- First load without usable data shows the complete loading state and does not mount an empty chart.
- Background refresh with usable data keeps the current chart visible until the new result is applied.
- Permission and permanent failures remain explicit failures.
- Existing unrelated worktree changes are not staged, reverted, or reformatted.

---

### Task 1: Deduplicate Preview Resize Broadcasts

**Files:**
- Modify: `frontend/src/views/dashboard/preview/SQPreview.vue`
- Create: `frontend/src/views/dashboard/preview/SQPreview.resize-observer.test.mjs`

**Interfaces:**
- Consumes: `previewCanvas: Ref<HTMLElement | undefined>` and `useEmittLazy('view-render-all')`.
- Produces: `sizeInit(force?: boolean): boolean`, returning whether the measured width or height changed.

- [x] **Step 1: Write the failing source-contract test**

Assert that `SQPreview.vue` stores the previous viewport dimensions, returns early for an unchanged measurement, emits only after a changed measurement, uses one native `ResizeObserver`, and no longer imports or initializes `element-resize-detector`.

- [x] **Step 2: Run the test to verify it fails**

Run: `node --test src/views/dashboard/preview/SQPreview.resize-observer.test.mjs`

Expected: FAIL because the component still has duplicate observer paths and unconditional broadcasting.

- [x] **Step 3: Implement the minimal preview resize guard**

Add a `lastPreviewSize` record. Make the initial `sizeInit(true)` initialize layout, and make later callbacks compare rounded `offsetWidth` and `offsetHeight` before updating grid values and broadcasting. Remove `element-resize-detector` setup and teardown from this component.

- [x] **Step 4: Run the focused test**

Run: `node --test src/views/dashboard/preview/SQPreview.resize-observer.test.mjs`

Expected: PASS.

### Task 2: Skip Card Redraws When Frame Size Is Unchanged

**Files:**
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs`

**Interfaces:**
- Consumes: `chartShowAreaRef`, `frameSize`, `scheduleRenderChart()`.
- Produces: `measureFrame(): boolean`, returning `true` only after a real width or height change.

- [x] **Step 1: Add a failing regression assertion**

Assert that `measureFrame()` returns `false` without an element or for unchanged dimensions, returns `true` after updating dimensions, and the observer calls `scheduleRenderChart()` only when `measureFrame()` returned `true`.

- [x] **Step 2: Run the test to verify it fails**

Run: `node --test src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs`

Expected: FAIL because the observer currently schedules every callback.

- [x] **Step 3: Implement the boolean measurement contract**

Return `false` on missing or unchanged measurements and `true` after assigning `frameSize`. Store the callback result and gate non-table redraw scheduling on it.

- [x] **Step 4: Run the focused test**

Run: `node --test src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs`

Expected: PASS.

### Task 3: Lock Loading Versus Background Refresh Rendering

**Files:**
- Modify: `frontend/src/views/dashboard/components/sq-view/index.state-machine.test.mjs`
- Modify: `frontend/src/views/dashboard/preview/SQPreviewShow.loading-state.test.mjs`
- Modify only if the tests expose a gap: `frontend/src/views/dashboard/components/sq-view/index.vue`
- Modify only if the tests expose a gap: `frontend/src/views/dashboard/preview/SQPreviewShow.vue`

**Interfaces:**
- Consumes: `showFullChartLoading`, `showChartContent`, `prepareChartPreviewState()`, `prepareChartDatabaseRefreshState()`.
- Produces: an enforced contract where no-data pending state blocks chart mounting and existing-data refresh preserves the chart.

- [x] **Step 1: Add loading-state contract assertions**

Assert that full loading is selected when loading or pending has no rendered data, chart content explicitly excludes full loading, initial preview preparation enters `loading/waiting`, and database refresh preserves `success/ready` when a usable snapshot exists.

- [x] **Step 2: Run the tests and observe whether production code already satisfies them**

Run: `node --test src/views/dashboard/components/sq-view/index.state-machine.test.mjs src/views/dashboard/preview/SQPreviewShow.loading-state.test.mjs`

Expected: PASS if the existing state machine already implements the approved behavior; otherwise FAIL at the missing contract.

- [x] **Step 3: If required, make the smallest state-machine correction**

Do not change backend payload semantics. Correct only the failing condition so first-load pending state blocks chart content while snapshot-backed refresh remains non-blocking.

- [x] **Step 4: Run all focused regression tests**

Run: `node --test src/views/dashboard/preview/SQPreview.resize-observer.test.mjs src/views/dashboard/preview/SQPreviewShow.loading-state.test.mjs src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs src/views/dashboard/components/sq-view/index.state-machine.test.mjs`

Expected: PASS with zero failures.

### Task 4: Make G2 Redraws Atomic

**Files:**
- Modify: `frontend/src/views/chat/component/ChartComponent.vue`
- Create: `frontend/src/views/chat/component/ChartComponent.atomic-render.test.mjs`
- Modify: `frontend/src/views/chat/component/ChartComponent.resize.test.mjs`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.state-machine.test.mjs`

**Interfaces:**
- Consumes: `getChartInstance()`, asynchronous `BaseChart.render()`, chart prop watcher, and the dashboard render scheduler.
- Produces: one visible active layer plus at most one hidden staging layer per chart; stale or failed staging renders never clear the active layer.

- [x] **Step 1: Add failing atomic-render regression assertions**

Assert that the chart renders into a hidden staging layer, commits only after the render promise resolves, preserves the active layer on stale/error paths, shows a loading indicator before the first commit, and never destroys the visible chart before starting an asynchronous replacement.

- [x] **Step 2: Verify the tests fail for the old destroy-then-render path**

Run: `node src/views/chat/component/ChartComponent.atomic-render.test.mjs` and `node src/views/dashboard/components/sq-view/index.state-machine.test.mjs`.

Expected: FAIL because `ChartComponent` calls `destroyChart(false)` before `render()` and `sq-view` explicitly destroys/remounts the chart.

- [x] **Step 3: Implement complete-layer swapping**

Mount the next non-table chart into a hidden full-size layer, await its render, reveal that complete layer, then destroy and remove the previous instance and layer. Give S2 its own active layer and retain its in-place resize behavior. Remove `chartRenderVersion` from the Vue key and remove explicit outer `destroyChart()` calls.

- [x] **Step 4: Verify redraw and type-change contracts**

Run the atomic, resize, state-machine, preview resize, editor lifecycle, responsive layout, and loading-state tests. Verify that G2 DOM children remain in the mount layer owned by their chart instance.

### Task 5: Build and Browser Verification

**Files:**
- Verify: `frontend` build output only; do not commit generated artifacts.

**Interfaces:**
- Consumes: the completed frontend implementation and running local stack.
- Produces: fresh evidence that compilation succeeds and the real dashboard remains visually stable.

- [x] **Step 1: Run the frontend build**

Run: `npm run build`

Expected: exit code 0 from `vue-tsc -b && vite build`.

- [x] **Step 2: Verify the exact dashboard behavior**

Open the real default-dashboard URL, reload it, and sample loading, active-layer, staging-layer, and rendered-output state through initial load and beyond the configured refresh boundary. Trigger a real viewport resize while sampling every animation frame. Verify that first load shows loading until the initial commit and that every staging frame retains the previous active output until the replacement commits.

- [x] **Step 3: Inspect browser errors**

Read console errors for the verified tab. Existing unrelated warnings may be reported, but new chart or resize exceptions fail verification.

- [x] **Step 4: Review the final diff**

Run: `git diff -- frontend/src/views/chat/component/ChartComponent.vue frontend/src/views/chat/component/ChartComponent.atomic-render.test.mjs frontend/src/views/chat/component/ChartComponent.resize.test.mjs frontend/src/views/dashboard/preview/SQPreview.vue frontend/src/views/dashboard/preview/SQPreview.resize-observer.test.mjs frontend/src/views/dashboard/preview/SQPreviewShow.loading-state.test.mjs frontend/src/views/dashboard/components/sq-view/index.vue frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs frontend/src/views/dashboard/components/sq-view/index.state-machine.test.mjs`

Expected: only the scoped resize and loading-state changes.
