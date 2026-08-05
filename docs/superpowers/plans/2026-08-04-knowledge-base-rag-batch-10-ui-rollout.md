# Knowledge Base RAG Batch 10 UI and Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the unified knowledge management page, metadata permission controls, safe citations on AI surfaces, and the gated shared-environment cutover/runtime rollout.

**Architecture:** Keep `index.vue` as page orchestration only and split toolbar, table, drawers, validation, versions, retrieval preview, and four payload editors into focused components. Render the V2 page only from server capabilities, extend the existing permission page rather than creating another one, and perform cutover only after backend compatibility, backfill, projection, dual-read, backup, and local integration gates pass.

**Tech Stack:** Vue 3, TypeScript, Element Plus Secondary, vue-i18n, markdown-it, node:test, Vite, FastAPI, local four-service stack.

## Global Constraints

- Preserve the existing Skills page, platform/workspace/personal scopes, editing, enable/disable behavior, and current routes.
- Preserve existing tracking/data-dictionary page/API/write behavior.
- Use the existing system-management visual language and theme variables; do not add a knowledge-specific design system.
- Use a compact table for the main management surface; details, editing, validation, versions, and preview use drawers without nested decorative cards.
- Reuse current icons and tooltips; status colors follow existing semantic colors; card/drawer internal radius does not exceed 8px.
- Keep light theme default and do not bypass `COLOR_THEME_SWITCHING_ENABLED=false`.
- All copy uses `vue-i18n` in simplified Chinese, traditional Chinese, English, and Korean.
- Simplified Chinese never displays machine codes, HTTP English phrases, exception names, or third-party English errors.
- Verify 1366x768, 1440x900, and 1920x1080 with no overlap, clipped stable keys, toolbar collisions, or drawer footer occlusion.
- Shared-environment phase changes require an explicit backup and every cutover gate in Task 6.

---

### Task 1: Typed Frontend API and Capability Routing

**Files:**
- Modify: `frontend/src/api/knowledgeBase.ts`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/views/knowledge-base/index.vue`
- Create: `frontend/src/views/knowledge-base/KnowledgePayload.serialization.test.mjs`
- Create: `frontend/src/views/knowledge-base/KnowledgeCapabilities.test.mjs`

**Interfaces:**
- Consumes: V2 backend resources and `KnowledgeCapabilities`.
- Produces: discriminated payload union, typed V2 API methods, and capability-driven LEGACY/UPGRADING/V2/MAINTENANCE page state.

- [ ] **Step 1: Write serialization and capability tests**

```javascript
test('business payload preserves question and SQL without term', () => {
  const payload = serializeKnowledgeDraft({
    knowledge_type: 'BUSINESS',
    term: null,
    definition: '',
    examples: [{ name: '收入', question: '收入是多少', sql: 'select sum(amount) from orders' }]
  })
  assert.equal(payload.examples[0].question, '收入是多少')
})

test('V2 page state comes only from server capability', () => {
  assert.equal(resolveKnowledgePageMode({ management_mode: 'V2' }), 'V2')
  assert.equal(resolveKnowledgePageMode({ management_mode: 'MAINTENANCE' }), 'MAINTENANCE')
})
```

- [ ] **Step 2: Run and confirm types/helpers are absent**

Run: `Set-Location frontend; node --test src/views/knowledge-base/KnowledgePayload.serialization.test.mjs src/views/knowledge-base/KnowledgeCapabilities.test.mjs`

Expected: FAIL on missing serializers/capability resolver.

- [ ] **Step 3: Add exact TypeScript contracts and API methods**

Define `DocumentPayload | BusinessKnowledgePayload | EventKnowledgePayload | JsonFieldKnowledgePayload` with `knowledge_type` discrimination, draft/version/job/citation/validation DTOs, and methods for capabilities/list/detail/create/update/validate/publish/job/versions/source-file/rollback/workspace-enabled/retrieval-preview/delete. Preserve existing `save()` for the legacy mode only.

- [ ] **Step 4: Render page mode from `/capabilities`**

Keep the old component behavior for `LEGACY`, show non-editable Chinese upgrading/maintenance state for `UPGRADING` and `MAINTENANCE`, and mount V2 orchestration only for `V2`. Do not infer phase from build-time environment values.

- [ ] **Step 5: Run frontend API tests**

Run: `Set-Location frontend; node --test src/views/knowledge-base/KnowledgePayload.serialization.test.mjs src/views/knowledge-base/KnowledgeCapabilities.test.mjs`

Expected: PASS.

- [ ] **Step 6: Commit frontend API and capability routing**

```powershell
git add frontend/src/api/knowledgeBase.ts frontend/src/router/index.ts frontend/src/views/knowledge-base/index.vue frontend/src/views/knowledge-base/KnowledgePayload.serialization.test.mjs frontend/src/views/knowledge-base/KnowledgeCapabilities.test.mjs
git commit -m "feat: 增加知识库 V2 前端类型与能力路由"
```

### Task 2: Management Table and Focused Drawers

**Files:**
- Create: `frontend/src/views/knowledge-base/components/KnowledgeToolbar.vue`
- Create: `frontend/src/views/knowledge-base/components/KnowledgeTable.vue`
- Create: `frontend/src/views/knowledge-base/components/KnowledgeDetailDrawer.vue`
- Create: `frontend/src/views/knowledge-base/components/KnowledgeEditorDrawer.vue`
- Create: `frontend/src/views/knowledge-base/components/KnowledgeValidationPanel.vue`
- Create: `frontend/src/views/knowledge-base/components/KnowledgeVersionDrawer.vue`
- Create: `frontend/src/views/knowledge-base/components/KnowledgeRetrievalPreview.vue`
- Modify: `frontend/src/views/knowledge-base/index.vue`
- Create: `frontend/src/views/knowledge-base/KnowledgePage.state.test.mjs`

**Interfaces:**
- Consumes: typed API and page mode.
- Produces: list/filter/detail/edit/validate/publish/job polling/version/rollback/override/preview orchestration.

- [ ] **Step 1: Write operation-state and conflict-preservation tests**

```javascript
test('publishing disables every mutating action', () => {
  const state = knowledgeActionState({ status: 'PUBLISHING', can_manage: true })
  assert.deepEqual(state, { save: false, validate: false, publish: false, archive: false, rollback: false })
})

test('draft conflict preserves local editor value', () => {
  const result = applySaveError(localDraft, { code: 'KNOWLEDGE_DRAFT_CONFLICT', message: '该知识已被其他用户更新，请刷新后重新编辑。' })
  assert.deepEqual(result.draft, localDraft)
  assert.equal(result.canRefresh, true)
})
```

- [ ] **Step 2: Run and confirm orchestration helpers/components are missing**

Run: `Set-Location frontend; node --test src/views/knowledge-base/KnowledgePage.state.test.mjs`

Expected: FAIL before component state implementation.

- [ ] **Step 3: Build the compact management surface**

Toolbar filters type/scope/status/keyword and places the primary new action at the right. Table columns show name, type, scope, state, stable key, updater/time, applicability summary, and actions with ellipsis/tooltips. Detail/editor/validation/version/preview are sibling drawers controlled by `index.vue`; no drawer nests a card or another drawer.

- [ ] **Step 4: Implement lifecycle interactions**

Use a fixed footer action order: cancel, save draft, validate, publish. Submit `draft_version_id` and `revision`; preserve local state on conflict and offer explicit refresh. Poll the database publish-job endpoint, not Redis task state. Version drawer downloads through the authenticated version URL and confirms rollback. Platform records expose the current-workspace enable switch/reason only to workspace admins.

- [ ] **Step 5: Run state tests**

Run: `Set-Location frontend; node --test src/views/knowledge-base/KnowledgePage.state.test.mjs`

Expected: PASS for status/button rules, polling, conflict, rollback, download, and override behavior.

- [ ] **Step 6: Commit the management surface**

```powershell
git add frontend/src/views/knowledge-base/index.vue frontend/src/views/knowledge-base/components frontend/src/views/knowledge-base/KnowledgePage.state.test.mjs
git commit -m "feat: 建立知识库统一管理表格与抽屉"
```

### Task 3: Four Structured Editors

**Files:**
- Create: `frontend/src/views/knowledge-base/components/editors/DocumentEditor.vue`
- Create: `frontend/src/views/knowledge-base/components/editors/BusinessKnowledgeEditor.vue`
- Create: `frontend/src/views/knowledge-base/components/editors/EventKnowledgeEditor.vue`
- Create: `frontend/src/views/knowledge-base/components/editors/JsonFieldKnowledgeEditor.vue`
- Modify: `frontend/src/views/knowledge-base/components/KnowledgeEditorDrawer.vue`
- Modify: `frontend/src/views/knowledge-base/KnowledgePayload.serialization.test.mjs`

**Interfaces:**
- Consumes: four payload DTOs, datasource schema metadata API, tracking event catalog, and source-file API.
- Produces: typed payload emits with no `any` structured payload.

- [ ] **Step 1: Extend serialization tests for all editors**

```javascript
test('event and JSON editors preserve stable source fields', () => {
  assert.deepEqual(serializeEvent(eventForm()).parameters[0].value_mappings, { paid: '已付费' })
  assert.equal(serializeJsonField(jsonForm()).json_path, '$.order.amount')
})

test('document reupload replaces draft markdown instead of merging', () => {
  assert.equal(applyParsedUpload('# New', '# Old\nremoved'), '# New')
})
```

- [ ] **Step 2: Run and confirm editor serializers are incomplete**

Run: `Set-Location frontend; node --test src/views/knowledge-base/KnowledgePayload.serialization.test.mjs`

Expected: FAIL for missing event/JSON/document behavior.

- [ ] **Step 3: Implement editors with established controls**

DOCUMENT uses textarea, `markdown-it` preview, and Markdown/Word upload without a new editor dependency. BUSINESS has term/alias/definition/formula/constraints plus repeatable SQL example rows and allows question+SQL only. EVENT has event fields and editable parameter table. JSON_FIELD uses catalog/schema/table/field selectors, static JSON path, type, expression, aliases, description, and value mappings. Manual physical identifiers show unresolved state and cannot publish until server validation resolves them.

- [ ] **Step 4: Run editor tests**

Run: `Set-Location frontend; node --test src/views/knowledge-base/KnowledgePayload.serialization.test.mjs`

Expected: PASS for round-trip serialization and replacement semantics.

- [ ] **Step 5: Commit the structured editors**

```powershell
git add frontend/src/views/knowledge-base/components/editors frontend/src/views/knowledge-base/components/KnowledgeEditorDrawer.vue frontend/src/views/knowledge-base/KnowledgePayload.serialization.test.mjs
git commit -m "feat: 增加四类知识逐条结构化编辑器"
```

### Task 4: Extend the Existing Permission Page

**Files:**
- Modify: `frontend/src/api/permissions.ts`
- Modify: `frontend/src/views/system/permission/index.vue`
- Create: `frontend/src/views/system/permission/MetadataPermission.test.mjs`

**Interfaces:**
- Consumes: backend permission types and stable catalog/tracking keys.
- Produces: Schema, event, and event-property choices inside the existing permission page.

- [ ] **Step 1: Write stable-key and inheritance-state tests**

```javascript
test('metadata permission payload omits display names and foreign tenant identifiers', () => {
  const payload = serializeMetadataPermission(schemaSelection())
  assert.deepEqual(Object.keys(payload.target).sort(), ['catalog_key', 'schema_key'])
})

test('single schema datasource renders inherited state without redundant rule', () => {
  assert.equal(schemaPermissionMode([{ key: 'public' }]), 'INHERITED')
})
```

- [ ] **Step 2: Run and confirm permission API types are limited**

Run: `Set-Location frontend; node --test src/views/system/permission/MetadataPermission.test.mjs`

Expected: FAIL because `PermissionType` supports only row/column/table.

- [ ] **Step 3: Add metadata types and selectors to the current page**

Extend `PermissionType` to `row | column | table | schema | event | event_property`. Use catalog/schema selector, workspace tracking event selector, and event-linked stable property selector. Submit only stable IDs/keys; display source summaries as non-authoritative labels. A single valid schema displays inherited datasource access and does not create a redundant record.

- [ ] **Step 4: Run permission frontend regressions**

Run: `Set-Location frontend; node --test src/views/system/permission/MetadataPermission.test.mjs src/views/system/permission/Permission.roi.test.mjs`

Expected: PASS with existing row/column/table/ROI behavior unchanged.

- [ ] **Step 5: Commit metadata permission controls**

```powershell
git add frontend/src/api/permissions.ts frontend/src/views/system/permission/index.vue frontend/src/views/system/permission/MetadataPermission.test.mjs
git commit -m "feat: 在现有权限页配置 Schema 与事件权限"
```

### Task 5: Safe Knowledge Citations and Localized Error Mapping

**Files:**
- Create: `frontend/src/components/knowledge/KnowledgeCitationList.vue`
- Modify: `frontend/src/views/chat/answer/ChartAnswer.vue`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`
- Modify: `frontend/src/api/analysisAssistant.ts`
- Modify: `frontend/src/views/analysis-assistant/AnalysisAssistantDock.vue`
- Modify: `frontend/src/i18n/zh-CN.json`
- Modify: `frontend/src/i18n/zh-TW.json`
- Modify: `frontend/src/i18n/en.json`
- Modify: `frontend/src/i18n/ko-KR.json`
- Create: `frontend/src/components/knowledge/KnowledgeCitationList.test.mjs`

**Interfaces:**
- Consumes: safe citation DTOs, retrieval warnings, backend error code/message/request ID.
- Produces: reusable collapsed citation list and localized error resolver.

- [ ] **Step 1: Write redaction and Chinese fallback tests**

```javascript
test('citation renderer accepts only safe display fields', () => {
  assert.deepEqual(toCitationViewModel(rawCitation), {
    name: rawCitation.name,
    knowledge_type: rawCitation.knowledge_type,
    section_path: rawCitation.section_path,
    version_number: rawCitation.version_number
  })
})

test('unknown code falls back to backend Chinese message then generic Chinese', () => {
  assert.equal(resolveKnowledgeError({ code: 'NEW_CODE', message: '安全中文提示' }, 'zh-CN'), '安全中文提示')
  assert.match(resolveKnowledgeError({ code: 'NEW_CODE' }, 'zh-CN'), /操作失败/)
})
```

- [ ] **Step 2: Run and confirm citation/error helpers are absent**

Run: `Set-Location frontend; node --test src/components/knowledge/KnowledgeCitationList.test.mjs`

Expected: FAIL before component helpers exist.

- [ ] **Step 3: Add reusable citations to all four surfaces**

Display a collapsed “知识来源” section showing name, type, section, and version. Do not show chunk ID as primary copy, file/storage identifiers, physical paths, other workspace names, or denied-object warnings. Smart Q&A, dashboard SQL, analysis assistant, and report interpretation use the same component/DTO.

- [ ] **Step 4: Map expected errors in all four locale files**

Map the approved knowledge codes and metadata permission changes. Missing mapping falls back to backend safe Chinese `message`; absent/unsafe message falls back to generic localized failure plus request ID. Never render code or raw HTTP status as user copy.

- [ ] **Step 5: Run citation tests and frontend build**

Run: `Set-Location frontend; node --test src/components/knowledge/KnowledgeCitationList.test.mjs`

Expected: PASS.

Run: `Set-Location frontend; npm run build`

Expected: `vue-tsc -b && vite build` exits 0.

- [ ] **Step 6: Commit citations and localization**

```powershell
git add frontend/src/components/knowledge frontend/src/views/chat/answer/ChartAnswer.vue frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/api/analysisAssistant.ts frontend/src/views/analysis-assistant/AnalysisAssistantDock.vue frontend/src/i18n/zh-CN.json frontend/src/i18n/zh-TW.json frontend/src/i18n/en.json frontend/src/i18n/ko-KR.json
git commit -m "feat: 展示安全知识引用并统一错误文案"
```

### Task 6: Visual QA, Full Regression, Shared Cutover, and Runtime Gray Release

**Files:**
- Create: `frontend/src/views/knowledge-base/KnowledgePage.layout.test.mjs`
- Create: `docs/knowledge_base_rag_rollout_runbook.md`
- Modify: `docs/knowledge_base_rag_development_design.md`

**Interfaces:**
- Consumes: all batches, capability matrix, migration CLI, local four-service runbook, and backup script.
- Produces: viewport evidence, release checklist, shared `V2_ACTIVE` transition, V2 management capability, and independently controlled runtime-context rollout.

- [ ] **Step 1: Add source-level layout and original-entry regression checks**

```javascript
test('knowledge page keeps editors split and existing Skills route intact', () => {
  assert.ok(source('views/knowledge-base/index.vue').includes('KnowledgeEditorDrawer'))
  assert.ok(routerSource().includes("path: 'data-skills'"))
  assert.ok(routerSource().includes("path: 'knowledge-base'"))
})
```

- [ ] **Step 2: Run all backend feature and permission regressions**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_*.py backend/tests/test_permission_scope_service.py backend/tests/test_metadata_permission_service.py backend/tests/test_data_skill_context_integration.py backend/tests/test_data_skill_sql_validation.py backend/tests/test_tracking_excel.py backend/tests/test_dashboard_ai_sql_generator.py backend/tests/test_analysis_assistant_sql_generation.py -q`

Expected: PASS.

- [ ] **Step 3: Run frontend tests and production build**

Run: `Set-Location frontend; node --test src/views/knowledge-base/*.test.mjs src/views/system/permission/MetadataPermission.test.mjs src/components/knowledge/KnowledgeCitationList.test.mjs`

Expected: PASS.

Run: `Set-Location frontend; npm run build`

Expected: exit code 0.

- [ ] **Step 4: Start and verify the complete local stack**

Run from repository root: `.\tools\stack-local.ps1 -Action restart -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx`

Run from `frontend`: `npm run dev`

Run: `.\tools\stack-local.ps1 -Action status -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx`

Run: `Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess`

Expected: frontend 5173, API 8000, MCP process 8001, and one Worker on the same `local-*` queue are running; backend and Worker logs report `LLM_REQUEST_TIMEOUT=120`, `LLM_TASK_MAX_WAIT_SECONDS=900`, and `LLM_MAX_RETRIES=1`. `MCP_ENABLED=false` remains set, and this health check adds no knowledge-base MCP route, tool, model, prompt, or permission behavior.

- [ ] **Step 5: Perform browser visual and interaction QA**

Use the in-app browser control skill against `http://127.0.0.1:5173/` with an authenticated test user. Capture screenshots at 1366x768, 1440x900, and 1920x1080 for the list, each editor, validation panel, version drawer, retrieval preview, permission types, and citation list. Verify no overlap/overflow, fixed drawer footer remains visible, long stable keys truncate with tooltip, filters wrap coherently, and styling matches the system permission/settings pages.

- [ ] **Step 6: Write and execute the pre-cutover checklist**

The runbook must require: all API/Worker builds support the phase protocol; storage probe current generation is ready for every active publishing Worker; backfill has zero remaining/failed items; all published versions are `index_status=READY`; Skill projections are current; dual-read mismatches are zero; queue reconciliation has no overdue job; feature tests/build pass; and rollback contacts/window are recorded.

Run: `.\tools\postgres-backup-local.ps1`

Expected: a new backup exists under `.codex-runtime/pg-backups` and is not staged by Git.

- [ ] **Step 7: Perform the only shared-environment phase transition**

Run: `backend\.venv\Scripts\python.exe backend/scripts/knowledge_base_migrate.py verify`

Expected: `ready_for_cutover=true`, zero mismatches, zero pending index/projection jobs, compatible builds only.

Run: `backend\.venv\Scripts\python.exe backend/scripts/knowledge_base_migrate.py enter-barrier`

Expected: `phase=CUTOVER_BARRIER`; both old and V2 writes return “知识库升级中，请稍后重试。”.

Run: `backend\.venv\Scripts\python.exe backend/scripts/knowledge_base_migrate.py activate-v2`

Expected: `phase=V2_ACTIVE`; old `/knowledge-base/save` returns HTTP 410 with “知识库已升级，请刷新页面后重新操作。”.

- [ ] **Step 8: Enable management, then independently gray-release runtime context**

Deploy `KNOWLEDGE_MANAGEMENT_V2_ENABLED=true` and verify `/knowledge-base/capabilities` reports `management_mode=V2` before exposing the page. Keep `KNOWLEDGE_RUNTIME_CONTEXT_ENABLED=false` for the first management-only observation window; then enable it for the approved workspace cohort, monitor publish/retrieval/applicability/permission rejection metrics, and expand only when warnings and error rates meet the runbook thresholds. Disabling runtime context returns AI surfaces to existing tracking/Skill behavior without reopening legacy writes or deleting V2 data.

- [ ] **Step 9: Commit QA and rollout documentation before deployment execution**

```powershell
git add frontend/src/views/knowledge-base/KnowledgePage.layout.test.mjs docs/knowledge_base_rag_rollout_runbook.md docs/knowledge_base_rag_development_design.md
git commit -m "docs: 固化知识库上线验收与灰度流程"
```
