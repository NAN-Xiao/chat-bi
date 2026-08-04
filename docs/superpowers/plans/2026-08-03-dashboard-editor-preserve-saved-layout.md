# Dashboard Editor Preserve Saved Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reopening a saved dashboard must preserve every component's persisted grid coordinates regardless of component array order.

**Architecture:** Add a pure saved-layout validator that reports invalid frames and overlaps without changing input data. Change `CanvasCore.init()` to assign runtime drag IDs, validate the complete saved layout, and build the occupancy grid in one pass; retain the existing incremental auto-layout behavior for newly added, dragged, resized, and deleted components.

**Tech Stack:** Vue 3, TypeScript, Node test runner

## Global Constraints

- Saved `x`, `y`, `sizeX`, and `sizeY` values are authoritative during editor initialization.
- Do not silently substitute or normalize invalid saved positions.
- Existing interactive auto-layout behavior remains unchanged outside initial loading.

---

### Task 1: Preserve Saved Canvas Coordinates

**Files:**
- Create: `frontend/src/views/dashboard/utils/savedCanvasLayout.ts`
- Create: `frontend/src/views/dashboard/utils/savedCanvasLayout.test.mjs`
- Modify: `frontend/src/views/dashboard/canvas/CanvasCore.vue`

**Interfaces:**
- Produces: `validateSavedCanvasLayout(items, maxColumns): SavedCanvasLayoutIssue[]`
- Consumes: persisted canvas items with `x`, `y`, `sizeX`, and `sizeY`

- [ ] **Step 1: Write a failing test proving array order does not mutate saved positions and invalid layouts are reported.**
- [ ] **Step 2: Run `node --test src/views/dashboard/utils/savedCanvasLayout.test.mjs` from `frontend` and verify failure because the module is absent.**
- [ ] **Step 3: Implement the pure validator and update `CanvasCore.init()` to rebuild occupancy from the complete saved layout without calling incremental `addItem()`.**
- [ ] **Step 4: Run the focused test and dashboard frontend tests.**
- [ ] **Step 5: Run `npm run build` and inspect the final diff.**
