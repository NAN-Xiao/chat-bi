# Knowledge Base RAG Batch 04 Lifecycle API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement typed payloads, optimistic-lock drafts, validation, versions, rollback, archive, source-file download, platform overrides, and database-backed publish-job creation behind the disabled V2 management capability.

**Architecture:** Keep route modules thin and place state transitions in a lifecycle service backed by a row-locking version repository. Validate immutable payload snapshots and use `draft_version_id + revision + content_hash` as the concurrency and publication identity.

**Tech Stack:** FastAPI, Pydantic v2, SQLModel/SQLAlchemy, sqlglot, PostgreSQL, pytest.

## Global Constraints

- `KNOWLEDGE_MANAGEMENT_V2_ENABLED` remains `false` in default configuration.
- `/knowledge-base/capabilities` is registered before `/{id}`.
- The server derives tenant and scope from `CurrentUser`; requests cannot select an arbitrary tenant.
- One knowledge item has at most one active draft and one active publish job.
- A draft save never changes `current_version_id`.
- Re-upload completely replaces the draft document and uses a request-private temporary file until the conditional update succeeds.
- Existing published and historical source files remain immutable and are downloaded only through an authenticated API.
- Every expected error returns `code`, Chinese `message`, `field_path`, `error_type`, and `suggestion` without leaking physical paths or foreign object names.

---

### Task 1: Typed Payload Union and Deterministic Validators

**Files:**
- Create: `backend/apps/knowledge_base/schemas.py`
- Create: `backend/apps/knowledge_base/errors.py`
- Create: `backend/apps/knowledge_base/validators.py`
- Create: `backend/apps/knowledge_base/normalizers.py`
- Test: `backend/tests/test_knowledge_base_payload_validation.py`

**Interfaces:**
- Consumes: `DeclaredObjectPath`, datasource dialect metadata, sqlglot, and four knowledge types.
- Produces: `KnowledgePayload`, `KnowledgeBusinessError`, `ValidationReport`, `validate_payload()`, `normalize_payload()`, and `content_hash_for_payload()`.

- [ ] **Step 1: Write failing discriminated-union and business-rule tests**

```python
def test_business_payload_allows_question_and_sql_without_term():
    payload = KnowledgePayloadAdapter.validate_python({
        "knowledge_type": "BUSINESS",
        "term": None,
        "definition": "",
        "examples": [{"name": "收入", "question": "收入是多少", "sql": "select sum(amount) from orders"}],
    })
    assert payload.examples[0].question == "收入是多少"


def test_datasource_neutral_document_rejects_sql():
    report = validate_payload(DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="```sql\nselect * from orders\n```",
        datasource_neutral=True,
    ), context=validation_context())
    assert report.errors[0].code == "KNOWLEDGE_DOCUMENT_NOT_NEUTRAL"
```

- [ ] **Step 2: Run tests and confirm schema module is missing**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_payload_validation.py -q`

Expected: collection fails on missing payload and validator types.

- [ ] **Step 3: Implement the exact four payloads and validation report**

```python
KnowledgePayload = Annotated[
    DocumentPayload | BusinessKnowledgePayload | EventKnowledgePayload | JsonFieldKnowledgePayload,
    Field(discriminator="knowledge_type"),
]


class ValidationIssue(BaseModel):
    code: str
    message: str
    field_path: str | None = None
    error_type: Literal["ERROR", "WARNING"]
    suggestion: str = ""


class ValidationReport(BaseModel):
    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
```

Implement every payload field and rule from sections 6.1-6.4 of the development design. Parse every SQL example as one read-only statement; compare explicit related objects with AST references; validate EVENT uniqueness in the workspace tracking specification; validate JSON host field, static path, target type, and expression dialect. Hash stable JSON plus normalized document text using SHA-256.

- [ ] **Step 4: Run payload tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_payload_validation.py backend/tests/test_data_skill_sql_validation.py -q`

Expected: PASS for all four payloads, SQL read-only enforcement, neutral-document rules, and deterministic hashes.

- [ ] **Step 5: Commit payload validation**

```powershell
git add backend/apps/knowledge_base/schemas.py backend/apps/knowledge_base/errors.py backend/apps/knowledge_base/validators.py backend/apps/knowledge_base/normalizers.py backend/tests/test_knowledge_base_payload_validation.py
git commit -m "feat: 定义四类知识载荷与校验规则"
```

### Task 2: Draft Repository and Optimistic Lifecycle Service

**Files:**
- Create: `backend/apps/knowledge_base/version_repository.py`
- Create: `backend/apps/knowledge_base/lifecycle_service.py`
- Create: `backend/apps/knowledge_base/permissions.py`
- Test: `backend/tests/test_knowledge_base_version_lifecycle.py`
- Test: `backend/tests/test_knowledge_base_state_machine.py`
- Test: `backend/tests/test_knowledge_base_permissions.py`

**Interfaces:**
- Consumes: lifecycle models, payload validators, current user/tenant roles, and deferred database constraints.
- Produces: `KnowledgeVersionRepository`, `KnowledgeLifecycleService.create_draft()`, `save_draft()`, `validate_draft()`, `rollback_to_new_draft()`, `archive_or_delete()`, and `set_workspace_enabled()`.

- [ ] **Step 1: Write concurrent create/save and publishing-state tests**

```python
def test_two_concurrent_saves_only_one_revision_wins(service_factory, draft):
    left = service_factory().save_draft(draft.id, draft.version_id, draft.revision, payload_a())
    with pytest.raises(KnowledgeBusinessError) as error:
        service_factory().save_draft(draft.id, draft.version_id, draft.revision, payload_b())
    assert error.value.code == "KNOWLEDGE_DRAFT_CONFLICT"
    assert error.value.message == "该知识已被其他用户更新，请刷新后重新编辑。"
    assert reload_version(draft.version_id).payload == left.payload


@pytest.mark.parametrize("operation", ["save", "validate", "delete", "archive", "rollback"])
def test_every_mutation_is_blocked_while_publishing(operation, publishing_item, lifecycle_service):
    with pytest.raises(KnowledgeBusinessError) as error:
        invoke(lifecycle_service, operation, publishing_item)
    assert error.value.code == "KNOWLEDGE_PUBLISHING"
```

- [ ] **Step 2: Run tests and confirm lifecycle interfaces are missing**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_version_lifecycle.py backend/tests/test_knowledge_base_state_machine.py backend/tests/test_knowledge_base_permissions.py -q`

Expected: FAIL before lifecycle service implementation.

- [ ] **Step 3: Implement row-lock allocation and conditional revision updates**

```python
def save_draft(
    self,
    *,
    knowledge_base_id: int,
    draft_version_id: int,
    revision: int,
    payload: KnowledgePayload,
    source_file: StagedSourceFile | None,
) -> KnowledgeBaseVersion:
    updated = self.versions.update_draft_if_revision_matches(
        knowledge_base_id=knowledge_base_id,
        version_id=draft_version_id,
        expected_revision=revision,
        payload=payload,
        content_hash=content_hash_for_payload(payload),
        source_file=source_file,
    )
    if updated is None:
        raise KnowledgeBusinessError(
            code="KNOWLEDGE_DRAFT_CONFLICT",
            message="该知识已被其他用户更新，请刷新后重新编辑。",
            status_code=409,
        )
    return updated
```

Allocate `max(version_number)+1` only while holding the knowledge row lock. Rollback always copies a historical payload/file reference into a new draft and rejects when any active draft exists. Archive published items; physically delete only never-published items. Platform override writes are tenant-scoped and do not modify platform rows.

- [ ] **Step 4: Run lifecycle and permission tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_version_lifecycle.py backend/tests/test_knowledge_base_state_machine.py backend/tests/test_knowledge_base_permissions.py backend/tests/test_knowledge_base_workspace_override.py -q`

Expected: PASS for concurrent version allocation, save conflicts, publish-state blocks, rollback refusal, scope roles, and overrides.

- [ ] **Step 5: Commit lifecycle services**

```powershell
git add backend/apps/knowledge_base/version_repository.py backend/apps/knowledge_base/lifecycle_service.py backend/apps/knowledge_base/permissions.py backend/tests/test_knowledge_base_version_lifecycle.py backend/tests/test_knowledge_base_state_machine.py backend/tests/test_knowledge_base_permissions.py backend/tests/test_knowledge_base_workspace_override.py
git commit -m "feat: 实现知识草稿与版本生命周期"
```

### Task 3: Resource Routes, Capabilities, and Chinese Error Contract

**Files:**
- Create: `backend/apps/knowledge_base/api/management.py`
- Create: `backend/apps/knowledge_base/api/versions.py`
- Create: `backend/apps/knowledge_base/api/publish.py`
- Modify: `backend/apps/knowledge_base/api/knowledge_base.py`
- Modify: `backend/apps/api.py`
- Test: `backend/tests/test_knowledge_base_legacy_api.py`
- Test: `backend/tests/test_knowledge_base_state_machine.py`

**Interfaces:**
- Consumes: capability matrix, lifecycle service, permission service, and error schema.
- Produces: every management API listed in development design section 15.

- [ ] **Step 1: Write route-order, mode, and error serialization tests**

```python
def test_capabilities_route_is_not_captured_as_id(client):
    response = client.get("/knowledge-base/capabilities")
    assert response.status_code == 200
    assert response.json()["management_mode"] in {"LEGACY", "UPGRADING", "V2", "MAINTENANCE"}


def test_conflict_response_has_safe_chinese_contract(client, stale_draft_request):
    response = client.put(stale_draft_request.path, json=stale_draft_request.body)
    assert response.status_code == 409
    assert response.json() == {
        "code": "KNOWLEDGE_DRAFT_CONFLICT",
        "message": "该知识已被其他用户更新，请刷新后重新编辑。",
        "field_path": None,
        "error_type": "CONFLICT",
        "suggestion": "刷新后比较最新版本，再重新保存。",
    }
```

- [ ] **Step 2: Run route tests and confirm V2 routes are absent**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_legacy_api.py backend/tests/test_knowledge_base_state_machine.py -q`

Expected: FAIL for missing capabilities and V2 resources.

- [ ] **Step 3: Move shared paths to a phase-aware dispatcher**

Keep legacy `/save` in `api/knowledge_base.py`. Convert the current legacy list and delete handlers into undecorated `list_legacy_knowledge_base()` and `delete_legacy_knowledge_base()` service functions. Let `management.py` own the single registered `GET /list` and `DELETE /{id}` routes: dispatch to the legacy functions in `LEGACY/UPGRADING`, keep reads available in maintenance, and use V2 list/delete semantics in `V2`. This avoids duplicate FastAPI path registration while preserving the old response behavior before cutover.

- [ ] **Step 4: Add focused routers and exception handling**

Register static routes before `/{id}` and enforce `KnowledgeCapabilities.v2_write_enabled` on all V2 writes. Implement list/detail/draft/validate/versions/version detail/rollback/workspace-enabled/delete in the management and version routers. Convert expected exceptions to the exact safe response schema; unknown errors return “操作失败，请稍后重试。” plus request ID while technical detail stays in server logs.

- [ ] **Step 5: Run management API tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_legacy_api.py backend/tests/test_knowledge_base_state_machine.py backend/tests/test_knowledge_base_permissions.py -q`

Expected: PASS; with the default flag false, V2 writes return maintenance/upgrade mode and legacy writes still follow the database phase.

- [ ] **Step 6: Commit resource APIs**

```powershell
git add backend/apps/knowledge_base/api/management.py backend/apps/knowledge_base/api/versions.py backend/apps/knowledge_base/api/publish.py backend/apps/knowledge_base/api/knowledge_base.py backend/apps/api.py backend/tests/test_knowledge_base_legacy_api.py backend/tests/test_knowledge_base_state_machine.py
git commit -m "feat: 增加知识库 V2 资源化管理接口"
```

### Task 4: Immutable Source Files and Database Publish-Job Preparation

**Files:**
- Modify: `backend/apps/knowledge_base/lifecycle_service.py`
- Modify: `backend/apps/knowledge_base/api/versions.py`
- Modify: `backend/apps/knowledge_base/api/publish.py`
- Modify: `backend/apps/knowledge_base/publish_jobs.py`
- Test: `backend/tests/test_knowledge_base_publish.py`
- Test: `backend/tests/test_knowledge_base_version_lifecycle.py`

**Interfaces:**
- Consumes: `AppFileUtils`, storage readiness, confirmed enqueue, and `knowledge_publish_job`.
- Produces: authenticated source-file response and `prepare_publish_job()` with idempotent job identity.

- [ ] **Step 1: Write file replacement/download and duplicate-publish tests**

```python
def test_conflicting_upload_cleans_only_request_temp_file(client, existing_draft_file):
    response = upload_with_stale_revision(client)
    assert response.status_code == 409
    assert file_exists(existing_draft_file)
    assert request_temp_files() == []


def test_duplicate_publish_returns_same_database_job(service, ready_draft):
    first = service.prepare_publish_job(ready_draft.id, ready_draft.revision, ready_draft.content_hash)
    second = service.prepare_publish_job(ready_draft.id, ready_draft.revision, ready_draft.content_hash)
    assert second.id == first.id
```

- [ ] **Step 2: Run tests and observe mutable/absent behavior**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_publish.py backend/tests/test_knowledge_base_version_lifecycle.py -q`

Expected: FAIL because source files are not version-addressed and V2 job preparation is absent.

- [ ] **Step 3: Implement immutable file binding and publish preparation**

Move a request-private staged upload into its immutable version file only after the revision CAS succeeds; on conflict remove only the staged file. Download looks up `knowledge_base_id + version_id`, checks view/edit permission, uses a safe `Content-Disposition` filename, and never returns `file_id` or storage path. `prepare_publish_job()` locks the knowledge row, verifies current draft/status/revision/hash, returns an existing nonterminal matching job, or creates `QUEUING`, sets `PUBLISHING` and `publishing_version_id`, and commits before confirmed enqueue.

- [ ] **Step 4: Run publication preparation tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_publish.py backend/tests/test_knowledge_base_version_lifecycle.py -q`

Expected: PASS; no publication Worker is enabled yet, so tests stop at durable job creation/queue outcome.

- [ ] **Step 5: Commit source-file and job preparation**

```powershell
git add backend/apps/knowledge_base/lifecycle_service.py backend/apps/knowledge_base/api/versions.py backend/apps/knowledge_base/api/publish.py backend/apps/knowledge_base/publish_jobs.py backend/tests/test_knowledge_base_publish.py backend/tests/test_knowledge_base_version_lifecycle.py
git commit -m "feat: 固化知识源文件与发布作业认领"
```
