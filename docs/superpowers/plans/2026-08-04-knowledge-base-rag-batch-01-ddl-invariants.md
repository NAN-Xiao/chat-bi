# Knowledge Base RAG Batch 01 DDL and Invariants Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic PostgreSQL schema for versioned knowledge, retrieval projections, publication jobs, migration state, storage probes, canonical catalog keys, and permission epochs.

**Architecture:** Use three linear Alembic revisions after revision 152, split into lifecycle, retrieval/projection, and permission/catalog responsibilities. Encode ownership, active-draft uniqueness, pointer ownership, and final pointer-state checks in PostgreSQL so API or Worker races cannot create invalid state.

**Tech Stack:** Alembic, PostgreSQL, SQLAlchemy, SQLModel, pgvector, pytest.

## Global Constraints

- The current Alembic head is `152platformsqlaliasquote`; revisions 153, 154, and 155 must form one linear chain.
- Migration code must not read source files, contact Redis, call embedding models, create upload directories, or inspect application runtime state.
- Do not guess an embedding dimension or create HNSW/IVFFlat indexes in this batch.
- Deterministic backfill may copy existing scalar columns and assign singleton defaults; content parsing and chunk generation are excluded.
- Keep both V2 feature flags disabled after this batch.
- PostgreSQL constraints are authoritative; ORM checks only improve error messages.

---

### Task 1: Lifecycle Schema and Deferred Pointer Constraints

**Files:**
- Create: `backend/alembic/versions/153_knowledge_base_version_lifecycle.py`
- Create: `backend/apps/knowledge_base/lifecycle_models.py`
- Modify: `backend/apps/knowledge_base/models.py`
- Test: `backend/tests/test_knowledge_base_models.py`
- Test: `backend/tests/test_knowledge_base_version_lifecycle.py`

**Interfaces:**
- Consumes: existing `knowledge_base` table and Alembic revision `152platformsqlaliasquote`.
- Produces: `KnowledgeBaseVersion`, `KnowledgePublishJob`, `KnowledgeMigrationState`, `KnowledgeStorageProbe`, `KnowledgeStorageProbeReceipt`, `KnowledgeMigrationPhase`, `KnowledgeVersionStatus`, and `KnowledgeIndexStatus`.

- [ ] **Step 1: Write failing migration metadata tests**

```python
def test_lifecycle_revision_is_linear_and_offline_safe():
    module = importlib.import_module("alembic.versions.153_knowledge_base_version_lifecycle")
    assert module.down_revision == "152platformsqlaliasquote"
    source = inspect.getsource(module)
    for forbidden in ("EmbeddingModelCache", "get_redis_client", "AppFileUtils", "open("):
        assert forbidden not in source


def test_lifecycle_models_have_composite_pointer_contracts():
    assert KnowledgeBaseVersion.__tablename__ == "knowledge_base_version"
    assert KnowledgePublishJob.__tablename__ == "knowledge_publish_job"
    assert KnowledgeMigrationState.__tablename__ == "knowledge_migration_state"
```

- [ ] **Step 2: Run the tests and confirm the missing module failure**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_models.py backend/tests/test_knowledge_base_version_lifecycle.py -q`

Expected: collection fails because `153_knowledge_base_version_lifecycle` and lifecycle model classes do not exist.

- [ ] **Step 3: Add lifecycle DDL and focused SQLModel mappings**

Implement revision constants and lifecycle enums exactly as follows, then create the columns, indexes, foreign keys, singleton rows, partial unique index, and deferred constraint trigger described in the lifecycle design:

```python
revision = "153knowledgeversion"
down_revision = "152platformsqlaliasquote"


class KnowledgeVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    PUBLISH_FAILED = "PUBLISH_FAILED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class KnowledgeMigrationPhase(str, Enum):
    LEGACY_OPEN = "LEGACY_OPEN"
    CUTOVER_BARRIER = "CUTOVER_BARRIER"
    V2_ACTIVE = "V2_ACTIVE"
```

The migration must create `(knowledge_base_id, tenant_id, id)` uniqueness on versions; composite deferrable foreign keys from all three knowledge pointers; one active draft via a partial unique index over draft-like states; one active publish job per knowledge item; and a `DEFERRABLE INITIALLY DEFERRED` constraint trigger that enforces final pointer states at commit.

- [ ] **Step 4: Run lifecycle tests against PostgreSQL**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_models.py backend/tests/test_knowledge_base_version_lifecycle.py -q`

Expected: PASS, including a transaction that fails at commit when `current_version_id` targets `DRAFT`, and succeeds when pointers and final statuses are updated in one transaction.

- [ ] **Step 5: Commit lifecycle DDL**

```powershell
git add backend/alembic/versions/153_knowledge_base_version_lifecycle.py backend/apps/knowledge_base/models.py backend/apps/knowledge_base/lifecycle_models.py backend/tests/test_knowledge_base_models.py backend/tests/test_knowledge_base_version_lifecycle.py
git commit -m "feat: 建立知识库版本生命周期数据库约束"
```

### Task 2: Retrieval, Applicability, Audit, and Object Projection Schema

**Files:**
- Create: `backend/alembic/versions/154_knowledge_base_retrieval_projection.py`
- Create: `backend/apps/knowledge_base/retrieval_models.py`
- Create: `backend/apps/knowledge_base/audit_models.py`
- Test: `backend/tests/test_semantic_object_reference.py`
- Test: `backend/tests/test_knowledge_base_models.py`

**Interfaces:**
- Consumes: revision `153knowledgeversion` and composite version ownership key.
- Produces: chunk, workspace override, applicability, source reference, retrieval log, semantic context audit, object reference/resolution, and Skill projection tables.

- [ ] **Step 1: Write failing ownership and uniqueness tests**

```python
def test_chunk_cannot_cross_tenant_or_knowledge(postgres_session):
    chunk = KnowledgeBaseChunk(
        knowledge_base_id=other_knowledge.id,
        version_id=published_version.id,
        tenant_id=published_version.tenant_id,
        visibility_scope="ADMIN_PUBLIC",
        chunk_index=0,
        content="x",
        content_hash="0" * 64,
    )
    postgres_session.add(chunk)
    with pytest.raises(IntegrityError):
        postgres_session.commit()


def test_resolution_requires_canonical_key_only_when_resolved(postgres_session):
    row = SemanticObjectResolution(status="RESOLVED", canonical_key=None, **resolution_scope)
    postgres_session.add(row)
    with pytest.raises(IntegrityError):
        postgres_session.commit()
```

- [ ] **Step 2: Run the tests and confirm missing tables/classes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_semantic_object_reference.py backend/tests/test_knowledge_base_models.py -q`

Expected: FAIL because the retrieval and projection models are absent.

- [ ] **Step 3: Implement revision 154 and model mappings**

```python
revision = "154knowledgeretrieval"
down_revision = "153knowledgeversion"
```

Create `knowledge_base_chunk` with pgvector `embedding` without a fixed ANN index, `knowledge_base_workspace_override`, `knowledge_base_applicability`, `knowledge_base_source_reference`, `knowledge_retrieval_log`, `semantic_context_audit`, `semantic_object_reference`, `semantic_object_resolution`, and `data_skill_object_projection`. Apply every unique/check/composite foreign key from the development and permission designs, including owner-column exclusivity and `(version_id, chunk_index)` uniqueness.

- [ ] **Step 4: Run projection schema tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_semantic_object_reference.py backend/tests/test_knowledge_base_models.py -q`

Expected: PASS with cross-owner, cross-tenant, and invalid resolution-state rows rejected by PostgreSQL.

- [ ] **Step 5: Commit projection DDL**

```powershell
git add backend/alembic/versions/154_knowledge_base_retrieval_projection.py backend/apps/knowledge_base/retrieval_models.py backend/apps/knowledge_base/audit_models.py backend/tests/test_semantic_object_reference.py backend/tests/test_knowledge_base_models.py
git commit -m "feat: 建立知识检索与对象投影表结构"
```

### Task 3: Canonical Catalog Columns and Semantic Scope Epoch

**Files:**
- Create: `backend/alembic/versions/155_semantic_permission_epoch.py`
- Modify: `backend/apps/datasource/models/datasource.py`
- Test: `backend/tests/test_semantic_object_key.py`
- Test: `backend/tests/test_permission_scope_service.py`

**Interfaces:**
- Consumes: revision `154knowledgeretrieval`, `core_table`, and `core_field`.
- Produces: normalized catalog/schema/table/field columns, deterministic catalog completeness state, `semantic_scope_epoch`, and `physical_schema_hash` storage.

- [ ] **Step 1: Write failing catalog migration tests**

```python
def test_catalog_keys_are_non_null_and_unique(postgres_inspector):
    columns = column_map(postgres_inspector, "core_table")
    assert columns["catalog_key"]["nullable"] is False
    assert columns["schema_key"]["nullable"] is False
    assert columns["table_key"]["nullable"] is False
    assert has_unique(postgres_inspector, "core_table", ("ds_id", "catalog_key", "schema_key", "table_key"))


def test_semantic_epoch_has_full_scope_key(postgres_inspector):
    assert has_unique_expression_index(
        postgres_inspector,
        "semantic_scope_epoch",
        "scope_type, tenant_id, COALESCE(datasource_id, 0), COALESCE(subject_id, 0)",
    )


def test_semantic_epoch_null_scopes_do_not_duplicate(postgres_session):
    postgres_session.add(SemanticScopeEpoch(scope_type="SCHEMA", tenant_id=2, datasource_id=None, subject_id=None))
    postgres_session.commit()
    postgres_session.add(SemanticScopeEpoch(scope_type="SCHEMA", tenant_id=2, datasource_id=None, subject_id=None))
    with pytest.raises(IntegrityError):
        postgres_session.commit()
```

- [ ] **Step 2: Run the tests and confirm new columns are absent**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_semantic_object_key.py backend/tests/test_permission_scope_service.py -q`

Expected: FAIL because catalog keys and `semantic_scope_epoch` are absent.

- [ ] **Step 3: Implement deterministic revision 155**

```python
revision = "155semanticpermepoch"
down_revision = "154knowledgeretrieval"
```

Add raw `catalog_name/schema_name`, normalized non-null `catalog_key/schema_key/table_key/field_key`, catalog completeness and schema hash fields. Backfill only values deterministically available from existing rows and datasource configuration; mark ambiguous multi-schema rows incomplete rather than selecting a schema. Replace naked-table uniqueness with full table identity and create `semantic_scope_epoch` with scope values `PERMISSION`, `SYSTEM_ROLE`, `MEMBERSHIP`, `DATASOURCE_ACCESS`, `DATASOURCE_ROLE`, `TRACKING`, `DATASOURCE_BINDING`, and `SCHEMA`. Create named unique expression index `uq_semantic_scope_epoch_scope` over `scope_type, tenant_id, COALESCE(datasource_id, 0), COALESCE(subject_id, 0)` so nullable datasource/subject scopes still have one upsert target on supported repository PostgreSQL versions.

- [ ] **Step 4: Run catalog and epoch tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_semantic_object_key.py backend/tests/test_permission_scope_service.py -q`

Expected: PASS; ambiguous records remain explicitly incomplete, and duplicate full keys fail.

- [ ] **Step 5: Commit catalog DDL**

```powershell
git add backend/alembic/versions/155_semantic_permission_epoch.py backend/apps/datasource/models/datasource.py backend/tests/test_semantic_object_key.py backend/tests/test_permission_scope_service.py
git commit -m "feat: 增加完整物理对象键与权限版本表"
```

### Task 4: Verify Full Upgrade, Downgrade, and Offline Safety

**Files:**
- Modify: `backend/tests/test_knowledge_base_models.py`
- Create: `backend/tests/test_knowledge_base_migration.py`

**Interfaces:**
- Consumes: revisions 153-155.
- Produces: a repeatable migration gate used by every later batch.

- [ ] **Step 1: Add the full-chain migration test**

```python
def test_knowledge_schema_upgrade_downgrade_upgrade(alembic_runner):
    alembic_runner.upgrade("152platformsqlaliasquote")
    alembic_runner.upgrade("155semanticpermepoch")
    assert alembic_runner.current() == "155semanticpermepoch"
    alembic_runner.downgrade("152platformsqlaliasquote")
    alembic_runner.upgrade("155semanticpermepoch")
    assert alembic_runner.current() == "155semanticpermepoch"
```

- [ ] **Step 2: Run the migration gate**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_migration.py backend/tests/test_knowledge_base_models.py -q`

Expected: PASS with network, Redis, and upload directory fixtures disabled.

- [ ] **Step 3: Run diff and Alembic checks**

Run: `git diff --check`

Expected: no output and exit code 0.

Run: `Set-Location backend; .\.venv\Scripts\python.exe -m alembic heads`

Expected: exactly `155semanticpermepoch (head)`.

- [ ] **Step 4: Commit the migration gate**

```powershell
git add backend/tests/test_knowledge_base_migration.py backend/tests/test_knowledge_base_models.py
git commit -m "test: 覆盖知识库迁移完整升级与回退"
```
