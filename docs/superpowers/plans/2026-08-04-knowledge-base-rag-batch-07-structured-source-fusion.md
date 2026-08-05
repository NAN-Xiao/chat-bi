# Knowledge Base RAG Batch 07 Structured Source Fusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present one deduplicated, permission-safe read model for tracking configuration plus published EVENT and JSON_FIELD knowledge while preserving all existing tracking, data-dictionary, and Skills write paths.

**Architecture:** Adapt existing `sys_tenant_tracking_*` authorities into immutable structured records, then union them with current published knowledge through explicit source identity and stable-key conflict checks. Platform structured knowledge is resolved and applicability-checked against the consuming workspace's bound datasource before joining the read model.

**Tech Stack:** SQLAlchemy, existing tracking services, knowledge applicability/resolution, permission snapshots, pytest.

## Global Constraints

- Existing tracking import/export/edit APIs and pages remain unchanged.
- Existing Data Skills API/page/storage remain unchanged.
- Tracking remains authoritative for its existing records; source references are read-only and cannot write back.
- EVENT names are unique within a workspace tracking specification, not globally and not by table namespace.
- Platform mappings use the datasource bound to the consuming workspace.
- Conflicts are explicit and never resolved by similarity, first match, or silent priority.

---

### Task 1: Read-Only Tracking Adapter and Source Identity

**Files:**
- Modify: `backend/apps/knowledge_base/source_references.py`
- Modify: `backend/apps/system/crud/tracking_config.py`
- Test: `backend/tests/test_knowledge_base_source_references.py`
- Test: `backend/tests/test_tracking_context_projection.py`

**Interfaces:**
- Consumes: current tracking config/event/table/field records and permission snapshot.
- Produces: `StructuredEventRecord`, `StructuredJsonFieldRecord`, and `load_tracking_structured_records()`.

- [ ] **Step 1: Write read-only identity and permission tests**

```python
def test_tracking_adapter_has_stable_source_identity(session, tracking_event):
    records = load_tracking_structured_records(session, tenant_id=2, datasource_id=9, snapshot=allowed_snapshot())
    event = next(item for item in records.events if item.event_name == tracking_event.event_name)
    assert event.source_identity == ("TRACKING_CONFIG", tracking_event.id)


def test_adapter_does_not_expose_denied_event_or_property(session):
    records = load_tracking_structured_records(session, tenant_id=2, datasource_id=9, snapshot=denied_event_snapshot())
    assert records.events == []
    assert records.json_fields == []
```

- [ ] **Step 2: Run and confirm adapter is missing**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_source_references.py backend/tests/test_tracking_context_projection.py -q`

Expected: FAIL on missing structured-record adapter.

- [ ] **Step 3: Implement a pure read adapter**

Map event names, table/event/time fields, parameters, JSON host/path/type/expression, stable IDs, and source hashes without mutating tracking rows. Apply the current tenant/datasource binding and permission snapshot before returning names or source summaries.

- [ ] **Step 4: Run tracking adapter tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_source_references.py backend/tests/test_tracking_context_projection.py backend/tests/test_tracking_event_catalog.py -q`

Expected: PASS and tracking rows remain byte-for-byte unchanged.

- [ ] **Step 5: Commit tracking adapter**

```powershell
git add backend/apps/knowledge_base/source_references.py backend/apps/system/crud/tracking_config.py backend/tests/test_knowledge_base_source_references.py backend/tests/test_tracking_context_projection.py
git commit -m "feat: 提供 tracking 结构化知识只读适配"
```

### Task 2: Deduplicated Structured Knowledge Read Model

**Files:**
- Create: `backend/apps/knowledge_base/structured_context.py`
- Modify: `backend/apps/knowledge_base/source_references.py`
- Test: `backend/tests/test_business_semantic_context.py`
- Test: `backend/tests/test_knowledge_base_source_references.py`

**Interfaces:**
- Consumes: tracking adapter, current published EVENT/JSON_FIELD versions, source references, overrides, applicability, resolution, and permissions.
- Produces: `StructuredKnowledgeContextService.load()` and `StructuredKnowledgeContext`.

- [ ] **Step 1: Write dedupe, conflict, override, and platform-consumer tests**

```python
def test_same_source_reference_is_returned_once(service, mirrored_event):
    result = service.load(tenant_id=2, datasource_id=9, permission_snapshot=allowed_snapshot())
    assert [item.event_name for item in result.events].count(mirrored_event.event_name) == 1


def test_platform_mapping_uses_each_consuming_workspace_datasource(service, platform_json_mapping):
    left = service.load(tenant_id=2, datasource_id=9, permission_snapshot=snapshot(2, 9))
    right = service.load(tenant_id=3, datasource_id=10, permission_snapshot=snapshot(3, 10))
    assert applicability(left, platform_json_mapping.id).datasource_id == 9
    assert applicability(right, platform_json_mapping.id).datasource_id == 10
```

- [ ] **Step 2: Run and confirm unified service is missing**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_business_semantic_context.py backend/tests/test_knowledge_base_source_references.py -q`

Expected: FAIL on missing structured context service.

- [ ] **Step 3: Implement explicit source dedupe and conflict reporting**

Deduplicate exact source references by `(source_type, source_id, source_hash)` and exact stable identities only. Exclude disabled platform entries, invalid applicability, unresolved objects, and denied references. If tracking and independently authored knowledge claim the same event/stable JSON field with different hashes, return a conflict warning and exclude the knowledge record until corrected; do not pick one silently.

- [ ] **Step 4: Run structured fusion tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_business_semantic_context.py backend/tests/test_knowledge_base_source_references.py backend/tests/test_knowledge_base_workspace_override.py backend/tests/test_knowledge_base_applicability.py -q`

Expected: PASS for dedupe, conflict, workspace override, per-consumer platform resolution, and permission exclusion.

- [ ] **Step 5: Commit structured read model**

```powershell
git add backend/apps/knowledge_base/structured_context.py backend/apps/knowledge_base/source_references.py backend/tests/test_business_semantic_context.py backend/tests/test_knowledge_base_source_references.py
git commit -m "feat: 融合事件与 JSON 结构化知识来源"
```

### Task 3: Existing Tracking, Dictionary, and Skills Regression Gate

**Files:**
- Modify: `backend/tests/test_business_semantic_context.py`
- Modify: `backend/tests/test_tracking_excel.py`
- Create: `backend/tests/test_data_skill_context_integration.py`

**Interfaces:**
- Consumes: structured read model.
- Produces: a regression gate proving no original write or selection logic changed.

- [ ] **Step 1: Add non-mutation regression assertions**

```python
def test_structured_reads_do_not_change_tracking_import_export_or_skill_rows(session, run_structured_reads):
    before_tracking = tracking_authority_snapshot(session)
    before_skills = data_skill_authority_snapshot(session)
    run_structured_reads()
    assert tracking_authority_snapshot(session) == before_tracking
    assert data_skill_authority_snapshot(session) == before_skills
```

- [ ] **Step 2: Run the complete source regression set**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_business_semantic_context.py backend/tests/test_tracking_excel.py backend/tests/test_tracking_event_catalog.py backend/tests/test_tracking_event_groups.py backend/tests/test_data_skill_context_integration.py backend/tests/test_custom_prompt_datasource_scope.py -q`

Expected: PASS; Excel import/export, tracking editing, Skills scope/edit/enable, personal Skills, and current selection remain unchanged.

- [ ] **Step 3: Run diff check**

Run: `git diff --check`

Expected: no output and exit code 0.

- [ ] **Step 4: Commit the compatibility gate**

```powershell
git add backend/tests/test_business_semantic_context.py backend/tests/test_tracking_excel.py backend/tests/test_data_skill_context_integration.py
git commit -m "test: 固化结构化知识融合兼容边界"
```
