# Knowledge Base RAG Batch 05 Publishing and RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the crash-safe publication pipeline, immutable object projections, platform applicability, permission-filtered vector retrieval, and retrieval/audit APIs.

**Architecture:** Parse, normalize, chunk, resolve references, and embed outside the final transaction while checking the database job around every external batch. Persist all derived rows idempotently and atomically switch the current version only after every artifact passes revision, hash, permission-projection, and vector-signature checks.

**Tech Stack:** Existing document parser, markdown-it-compatible Markdown, sqlglot, existing OpenAI-compatible embeddings, pgvector, Redis Worker, PostgreSQL, pytest.

## Global Constraints

- Publication uses registered Redis tasks only and never falls back to FastAPI BackgroundTask.
- The previous current version and chunks remain usable until the final transaction commits.
- Platform declarations contain no publishing administrator tenant/datasource binding.
- Every object reference must resolve under the consuming tenant/datasource/schema hash before retrieval.
- Permission filtering happens before chunk text reaches application memory or Prompt assembly.
- Vector model/dimension/signature mismatch excludes old chunks and schedules rebuild; it does not compare incompatible vectors.
- Logs and audits store IDs, hashes, scores, warnings, and timing, not full question, knowledge body, model output, or credentials.
- Use `KNOWLEDGE_RETRIEVAL_ENABLED=true`, `KNOWLEDGE_RETRIEVAL_TOP_K=5`, `KNOWLEDGE_RETRIEVAL_MAX_CONTEXT_CHARS=12000`, `KNOWLEDGE_RETRIEVAL_MIN_SCORE=0.40`, `KNOWLEDGE_CHUNK_SIZE=1200`, and `KNOWLEDGE_CHUNK_OVERLAP=150`.

---

### Task 1: Deterministic Parsing, Normalization, and Chunking

**Files:**
- Create: `backend/apps/knowledge_base/chunking.py`
- Modify: `backend/apps/knowledge_base/normalizers.py`
- Modify: `backend/apps/knowledge_base/tasks.py`
- Test: `backend/tests/test_knowledge_base_chunking.py`

**Interfaces:**
- Consumes: four payload types, immutable source file, and config `KNOWLEDGE_CHUNK_SIZE=1200`, `KNOWLEDGE_CHUNK_OVERLAP=150`.
- Produces: `ParsedKnowledge`, `KnowledgeChunkDraft`, `parse_and_normalize_version()`, and `chunk_knowledge()`.

- [ ] **Step 1: Write deterministic parsing and replacement tests**

```python
def test_same_document_has_stable_normalized_content_and_chunks(tmp_path):
    first = parse_and_chunk(sample_docx(tmp_path), chunk_size=1200, overlap=150)
    second = parse_and_chunk(sample_docx(tmp_path), chunk_size=1200, overlap=150)
    assert first.normalized_content == second.normalized_content
    assert [(c.section_path, c.content_hash) for c in first.chunks] == [
        (c.section_path, c.content_hash) for c in second.chunks
    ]


def test_reupload_does_not_merge_missing_old_section():
    chunks = chunk_knowledge(DocumentPayload(knowledge_type="DOCUMENT", markdown="# Kept\nnew"))
    assert all("Removed section" not in chunk.content for chunk in chunks)
```

- [ ] **Step 2: Run and confirm new chunker is missing**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_chunking.py -q`

Expected: FAIL on missing parse/chunk interfaces.

- [ ] **Step 3: Implement structured and heading-aware normalization**

Parse `.md/.markdown/.docx` with existing safe file limits. Convert each structured payload to stable Markdown sections; preserve SQL fences; split by heading/record boundary, then size with 150-character overlap without splitting a stable JSON path or SQL token where possible. Assign zero-based `chunk_index`, stable `section_path`, token estimate, and SHA-256 content hash.

- [ ] **Step 4: Run chunk tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_chunking.py -q`

Expected: PASS for determinism, all four knowledge types, Unicode text, empty sections, and full-replacement semantics.

- [ ] **Step 5: Commit parsing and chunking**

```powershell
git add backend/apps/knowledge_base/chunking.py backend/apps/knowledge_base/normalizers.py backend/apps/knowledge_base/tasks.py backend/tests/test_knowledge_base_chunking.py
git commit -m "feat: 增加知识标准化与确定性切片"
```

### Task 2: Object Reference Projection and Dynamic Resolution

**Files:**
- Create: `backend/apps/knowledge_base/object_references.py`
- Create: `backend/apps/knowledge_base/object_resolution.py`
- Test: `backend/tests/test_semantic_object_reference.py`
- Test: `backend/tests/test_semantic_object_resolution.py`

**Interfaces:**
- Consumes: payloads, SQL AST, canonical catalog resolver, tracking catalog, and physical schema hash.
- Produces: `project_version_references()`, `project_chunk_references()`, and `resolve_references_for_context()`.

- [ ] **Step 1: Write explicit-vs-AST and platform-resolution tests**

```python
def test_business_sql_extra_reference_blocks_projection():
    payload = business_payload(related_objects=[table_ref("public", "orders")], sql="select * from secret.payments")
    with pytest.raises(ObjectReferenceValidationError) as error:
        project_version_references(payload, projection_context())
    assert error.value.code == "KNOWLEDGE_UNDECLARED_OBJECT_REFERENCE"


def test_platform_reference_resolves_independently_per_datasource(platform_reference):
    a = resolve_references_for_context([platform_reference], tenant_id=2, datasource_id=10, schema_hash="a")
    b = resolve_references_for_context([platform_reference], tenant_id=3, datasource_id=11, schema_hash="b")
    assert a[0].canonical_key != b[0].canonical_key
```

- [ ] **Step 2: Run and confirm projection services are missing**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_semantic_object_reference.py backend/tests/test_semantic_object_resolution.py -q`

Expected: FAIL on missing projector/resolver.

- [ ] **Step 3: Implement immutable references and schema-hash resolutions**

Generate DOCUMENT references from declarations plus SQL blocks, BUSINESS references from related objects plus every SQL AST, EVENT references from table/event/time/parameter sources, and JSON_FIELD references from host field/path/expression. Upsert resolution rows keyed by reference, consumer tenant, datasource, and physical schema hash; store `RESOLVED`, `UNRESOLVED`, `AMBIGUOUS`, or `STALE` and require canonical key only for `RESOLVED`.

- [ ] **Step 4: Run object projection tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_semantic_object_reference.py backend/tests/test_semantic_object_resolution.py backend/tests/test_semantic_object_key.py -q`

Expected: PASS; no unresolved, ambiguous, stale, or cross-context reference is eligible.

- [ ] **Step 5: Commit object projections**

```powershell
git add backend/apps/knowledge_base/object_references.py backend/apps/knowledge_base/object_resolution.py backend/tests/test_semantic_object_reference.py backend/tests/test_semantic_object_resolution.py
git commit -m "feat: 投影并动态解析知识对象引用"
```

### Task 3: Applicability and Crash-Safe Publisher

**Files:**
- Create: `backend/apps/knowledge_base/applicability.py`
- Create: `backend/apps/knowledge_base/publisher.py`
- Modify: `backend/apps/knowledge_base/publish_jobs.py`
- Modify: `backend/apps/knowledge_base/reconciliation.py`
- Modify: `backend/apps/knowledge_base/tasks.py`
- Modify: `backend/common/core/task_registry.py`
- Test: `backend/tests/test_knowledge_base_applicability.py`
- Test: `backend/tests/test_knowledge_base_publish.py`
- Test: `backend/tests/test_knowledge_base_publish_recovery.py`

**Interfaces:**
- Consumes: parsed chunks, object projections, storage readiness, embedding model/signature, confirmed queue, and publish job CAS.
- Produces: `KnowledgeApplicabilityService.evaluate()`, `KnowledgePublisher.publish_version()`, and task `knowledge_base.publish_version`.

- [ ] **Step 1: Write crash, stale-job, and consumer-specific applicability tests**

```python
def test_embedding_failure_keeps_previous_current_version(publisher, existing_current, job):
    publisher.embedding_model.fail_on_batch(2)
    publisher.publish_version(job.id)
    assert reload_knowledge(job.knowledge_base_id).current_version_id == existing_current.id
    assert reload_job(job.id).status == "FAILED"


def test_stale_worker_cannot_finalize_after_revision_change(publisher, stale_job):
    mutate_draft_revision(stale_job.version_id)
    publisher.publish_version(stale_job.id)
    assert reload_knowledge(stale_job.knowledge_base_id).current_version_id != stale_job.version_id
```

- [ ] **Step 2: Run and confirm publication pipeline is absent**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_applicability.py backend/tests/test_knowledge_base_publish.py backend/tests/test_knowledge_base_publish_recovery.py -q`

Expected: FAIL because the publisher and applicability evaluator do not exist.

- [ ] **Step 3: Implement applicability and batch heartbeat checks**

Add the exact callable `KnowledgeApplicabilityService.evaluate(*, session: Session, tenant_id: int, datasource_id: int, version_id: int, physical_schema_hash: str) -> KnowledgeApplicabilityResult`.

Evaluate every reference for the consuming datasource without using the publishing user's authorization. In the publisher, acquire the tenant-scoped short Redis claim lock; CAS `QUEUING/QUEUED` to `RUNNING`; verify version/revision/hash; parse/project/chunk; before and after each embedding batch heartbeat and recheck job status/deadline/version identity; persist derived data idempotently.

- [ ] **Step 4: Implement the short finalization transaction**

Lock the job, version, and knowledge row; require the same `publishing_version_id`, revision, content hash, `RUNNING` job, complete chunks/references, and consistent vector signature/dimension. Mark old current `SUPERSEDED`, new version `PUBLISHED/READY`, switch current, clear draft/publishing pointers, and mark job `SUCCEEDED` in one transaction. On deterministic failure, preserve current, set new version `PUBLISH_FAILED`, clear publishing pointer, retain draft pointer, and save a safe Chinese error.

- [ ] **Step 5: Run publication and recovery tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_applicability.py backend/tests/test_knowledge_base_publish.py backend/tests/test_knowledge_base_publish_recovery.py backend/tests/test_knowledge_base_storage_probe.py -q`

Expected: PASS for duplicate work, API crash, Worker crash, cancellation between batches, response loss, stale revision, and final atomic switch.

- [ ] **Step 6: Commit publishing pipeline**

```powershell
git add backend/apps/knowledge_base/applicability.py backend/apps/knowledge_base/publisher.py backend/apps/knowledge_base/publish_jobs.py backend/apps/knowledge_base/reconciliation.py backend/apps/knowledge_base/tasks.py backend/common/core/task_registry.py backend/tests/test_knowledge_base_applicability.py backend/tests/test_knowledge_base_publish.py backend/tests/test_knowledge_base_publish_recovery.py
git commit -m "feat: 实现可恢复的知识发布流水线"
```

### Task 4: Permission-Filtered Retrieval and Preview API

**Files:**
- Create: `backend/apps/knowledge_base/retrieval.py`
- Modify: `backend/apps/knowledge_base/api/management.py`
- Modify: `backend/common/core/config.py`
- Test: `backend/tests/test_knowledge_base_retrieval.py`

**Interfaces:**
- Consumes: current published chunks, overrides, applicability, object resolutions, `PermissionScopeSnapshot`, and embedding model identity.
- Produces: `KnowledgeCitation`, `KnowledgeRetrievalResult`, `KnowledgeRetrievalService.search()`, and `/knowledge-base/retrieval-preview`.

- [ ] **Step 1: Write tenant, version, permission, and signature filters**

```python
def test_retrieval_excludes_unauthorized_before_loading_content(retrieval_repo, snapshot):
    forbidden = seed_chunk_with_forbidden_reference()
    result = KnowledgeRetrievalService.search(
        session=retrieval_repo.session,
        tenant_id=snapshot.tenant_id,
        datasource_id=snapshot.datasource_id,
        surface="SMART_QA",
        query="revenue",
        permission_snapshot=snapshot,
        top_k=5,
        max_context_chars=12000,
    )
    assert forbidden.id not in {item.chunk_id for item in result.citations}
    assert retrieval_repo.loaded_content_ids == set(result_chunk_ids(result))
```

- [ ] **Step 2: Run and confirm retrieval service is missing**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_retrieval.py -q`

Expected: FAIL on missing service and preview route.

- [ ] **Step 3: Implement database-first filtering and bounded context**

Add the exact callable `KnowledgeRetrievalService.search(*, session: Session, tenant_id: int, datasource_id: int, surface: str, query: str, permission_snapshot: PermissionScopeSnapshot, top_k: int, max_context_chars: int) -> KnowledgeRetrievalResult`.

Filter active/non-archived current versions, platform or current workspace scope, workspace override, valid current-schema applicability, fully resolved references, `NOT EXISTS` any denied/unallowed object, and current embedding signature before cosine ordering. Enforce min score, Top-K, and character budget. Wrap content in `<retrieved-knowledge priority="reference-only">` and return warnings on retrieval degradation rather than pretending there were no candidates.

- [ ] **Step 4: Run retrieval tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_retrieval.py backend/tests/test_knowledge_base_workspace_override.py backend/tests/test_knowledge_base_applicability.py -q`

Expected: PASS for tenant isolation, platform dynamic applicability, current-version-only retrieval, permission exclusion, model mismatch, and bounded output.

- [ ] **Step 5: Commit retrieval service**

```powershell
git add backend/apps/knowledge_base/retrieval.py backend/apps/knowledge_base/api/management.py backend/common/core/config.py backend/tests/test_knowledge_base_retrieval.py
git commit -m "feat: 增加权限前置过滤的知识检索"
```

### Task 5: Retrieval and Semantic Audit Persistence

**Files:**
- Modify: `backend/apps/knowledge_base/retrieval.py`
- Create: `backend/apps/knowledge_base/audit.py`
- Test: `backend/tests/test_knowledge_base_retrieval.py`

**Interfaces:**
- Consumes: retrieval result and later semantic-context snapshots.
- Produces: `record_retrieval_audit()` and `record_semantic_context_audit()`.

- [ ] **Step 1: Write redaction tests**

```python
def test_retrieval_audit_contains_hashes_not_sensitive_text(session, retrieval_call):
    retrieval_call(query="show secret revenue")
    row = latest_retrieval_log(session)
    serialized = json.dumps(row.model_dump(), ensure_ascii=False)
    assert "show secret revenue" not in serialized
    assert row.query_hash
    assert row.hit_snapshot[0]["chunk_id"]
```

- [ ] **Step 2: Run and confirm audits are not written**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_retrieval.py -q`

Expected: FAIL on missing audit row.

- [ ] **Step 3: Persist safe audit summaries**

Store request ID, surface, tenant/user/datasource IDs, query hash, model signature, IDs/version/chunk/score, latency, warnings, and failure type. Provide the semantic audit writer for batches 8-9 with knowledge and Skill ID snapshots plus hashes, never bodies.

- [ ] **Step 4: Run retrieval audit tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_retrieval.py -q`

Expected: PASS with sensitive text absent.

- [ ] **Step 5: Commit safe retrieval audits**

```powershell
git add backend/apps/knowledge_base/retrieval.py backend/apps/knowledge_base/audit.py backend/tests/test_knowledge_base_retrieval.py
git commit -m "feat: 记录脱敏知识检索与语义审计"
```
