# Dashboard Chart Flicker Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop dashboard charts from repeatedly disappearing and re-rendering while preserving responsive category-axis label sampling.

**Architecture:** Make the G2 category-axis callback tolerant of the library's two-argument layout invocation. Separate container renderability from actual size changes so `ResizeObserver` only schedules a render when width or height changes.

**Tech Stack:** Vue 3, TypeScript, AntV G2, Node test runner

## Global Constraints

- Preserve generic, datasource-agnostic chart behavior.
- Do not add silent chart-field fallbacks.
- Bind rendering to the component-owned chart container.
- Preserve unrelated working-tree changes.

---

### Task 1: Make category-axis sampling compatible with G2 layout measurement

**Files:**
- Modify: `frontend/src/views/chat/component/charts/g2Responsive.ts`
- Test: `frontend/src/views/chat/component/charts/g2Responsive.test.mjs`

**Interfaces:**
- Consumes: `resolveCategoryAxisResponsiveOptions(responsive)`
- Produces: a `labelFilter(datum, index, array?)` callback that never throws when G2 omits `array`

- [x] Add a regression assertion that calls `labelFilter(tick, index)` with no third argument and expects `true`.
- [x] Run `node src/views/chat/component/charts/g2Responsive.test.mjs` from `frontend` and confirm the new assertion fails with the current `.length` exception.
- [x] Make the callback accept an optional array and keep the label when no complete tick array is available.
- [x] Re-run the focused test and confirm it passes.

### Task 2: Render only after a real container size change

**Files:**
- Modify: `frontend/src/views/chat/component/ChartComponent.vue`
- Test: `frontend/src/views/chat/component/ChartComponent.resize.test.mjs`

**Interfaces:**
- Produces: `measureChartContainer()` returning `{ renderable: boolean, changed: boolean }`
- Consumes: `renderable` for render eligibility and `changed` for `ResizeObserver` scheduling

- [x] Add source-contract assertions requiring separate `renderable` and `changed` results and use of `changed` in `ResizeObserver`.
- [x] Run `node src/views/chat/component/ChartComponent.resize.test.mjs` from `frontend` and confirm the new assertions fail.
- [x] Update measurement and call sites so unchanged valid dimensions do not schedule another render.
- [x] Re-run the focused test and confirm it passes.

### Task 3: Verify the regression and real dashboard

**Files:**
- Verify only; no additional files expected.

- [x] Run both focused Node regression tests.
- [x] Run the frontend type check or build command defined by `frontend/package.json`.
- [x] Reload the affected local dashboard and verify no new `array.length` or `ChartComponent` render-failure warnings appear.
- [x] Sample chart containers after settling and confirm canvases remain rendered without repeated replacement.
