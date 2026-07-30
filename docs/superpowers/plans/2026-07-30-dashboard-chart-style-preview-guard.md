# Dashboard Chart Style Preview Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent chart-only display edits from being misclassified as an unpreviewed SQL datasource change when the editor opens.

**Architecture:** Restore the chart's persisted datasource ID before capturing the initial preview signature. Keep the existing signature fields unchanged so real SQL, datasource, pivot, and date-filter changes still require preview.

**Tech Stack:** Vue 3, TypeScript, Node.js built-in test runner

## Global Constraints

- Do not remove datasource from the preview signature.
- Do not weaken preview validation for SQL, datasource, pivot, date-filter, or MCP source changes.
- Preserve unrelated working-tree changes.

---

### Task 1: Correct Initial Preview Signature

**Files:**
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`
- Test: `frontend/src/views/dashboard/common/DashboardSqlEditor.preview-signature.test.mjs`

**Interfaces:**
- Consumes: `normalizeExecutionDatasourceId(value)` and `props.viewInfo.datasource`
- Produces: an initial `lastPreviewSignature` whose datasource matches the persisted chart datasource

- [ ] **Step 1: Write the failing test**

Assert that `initEditor()` restores the normalized persisted datasource before assigning `lastPreviewSignature.value = currentPreviewSignature()`.

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test src/views/dashboard/common/DashboardSqlEditor.preview-signature.test.mjs`

Expected: FAIL because `initEditor()` currently clears the datasource before capturing the signature.

- [ ] **Step 3: Write minimal implementation**

Replace the unconditional null initialization with:

```ts
selectedExecutionDatasourceId.value = normalizeExecutionDatasourceId(viewInfo?.datasource)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test src/views/dashboard/common/DashboardSqlEditor.preview-signature.test.mjs`

Expected: PASS.

- [ ] **Step 5: Run related editor regression tests**

Run: `node --test src/views/dashboard/common/DashboardSqlEditor.*.test.mjs`

Expected: all tests pass.
