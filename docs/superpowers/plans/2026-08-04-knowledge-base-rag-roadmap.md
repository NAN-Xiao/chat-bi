# Knowledge Base and RAG Delivery Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved knowledge-base, RAG, permission, lifecycle, migration, and four-surface integration design in ten independently reviewable batches.

**Architecture:** Keep Data Skills, tracking configuration, and the legacy knowledge-base path as existing authorities while a versioned V2 knowledge service is built beside them. Move to V2 only through a database-authoritative migration phase, and make every runtime consumer use one permission snapshot and one immutable semantic-context snapshot.

**Tech Stack:** FastAPI, SQLModel/SQLAlchemy, PostgreSQL with pgvector, Alembic, Redis task queue, Pydantic v2, sqlglot, Vue 3, TypeScript, Element Plus Secondary, node:test, pytest.

## Global Constraints

- Do not change the existing Data Skills page, three-level scope, or `find_data_skills` selection authority.
- Do not replace the existing tracking/data-dictionary write path; V2 reads it through a read-only adapter.
- Do not add MCP behavior or MCP-specific models, routes, prompts, tests, or UI.
- One datasource is bound to at most one workspace, and one workspace currently has one bound datasource.
- Platform knowledge is resolved against the datasource bound to the workspace that is using it, never the datasource visible to the publishing administrator.
- `knowledge_migration_state.phase` is the highest authority for old/new writes; environment flags cannot lower or bypass it.
- Only batch 10 may perform the shared-environment cutover to `V2_ACTIVE`; batch 6 only builds and rehearses the command in an isolated environment.
- All expected backend business errors include a stable machine code and safe Chinese `message`; the UI never displays HTTP English phrases, exception names, stack traces, or raw third-party errors.
- Redis keys use the helpers in `backend/common/core/redis_client.py` and include tenant, user, and datasource boundaries whenever permissions can affect the result.
- Alembic migrations perform deterministic DDL only; parsing, file reads, Redis operations, embeddings, and historical backfill run outside Alembic.
- Published versions and their source files are immutable; re-upload replaces only the current draft.
- The first release publishes one knowledge item per request; do not add bulk publish, bulk rollback, or bulk state transitions.
- Business terms, definitions, formulas, constraints, and SQL examples are one `BUSINESS` knowledge type, not separate catalogs.
- Runtime permission checks fail closed on missing, stale, ambiguous, or unauthorized object references and never substitute similarly named objects.
- Keep new backend and frontend files split by responsibility; do not consolidate the feature into a large model, route, service, or page file.

---

## Plan Set

| Batch | Plan | Depends on | Exit gate |
| --- | --- | --- | --- |
| 1 | [DDL and invariants](2026-08-04-knowledge-base-rag-batch-01-ddl-invariants.md) | Alembic head 152 | Offline-safe upgrade/downgrade and constraint tests pass |
| 2 | [Legacy barrier and queue](2026-08-04-knowledge-base-rag-batch-02-legacy-barrier-queue.md) | Batch 1 | Phase matrix, atomic enqueue, reconciliation, and storage probe tests pass |
| 3 | [Catalog and permission epoch](2026-08-04-knowledge-base-rag-batch-03-catalog-permission-epoch.md) | Batches 1-2 | Full object keys, all epoch write paths, snapshot consistency, and execution recheck pass |
| 4 | [V2 lifecycle API](2026-08-04-knowledge-base-rag-batch-04-lifecycle-api.md) | Batches 1-3 | Draft, validate, versions, rollback, archive, file download, and publish-job API tests pass |
| 5 | [Publishing and RAG](2026-08-04-knowledge-base-rag-batch-05-publishing-rag.md) | Batches 1-4 | Crash-safe publish, projections, applicability, retrieval, and audit tests pass |
| 6 | [Backfill and cutover tools](2026-08-04-knowledge-base-rag-batch-06-backfill-cutover.md) | Batches 1-5 | Repeatable backfill and isolated cutover rehearsal pass; shared phase remains `LEGACY_OPEN` |
| 7 | [Structured-source fusion](2026-08-04-knowledge-base-rag-batch-07-structured-source-fusion.md) | Batches 1-6 | Tracking plus EVENT/JSON read model is deduplicated and old UI/API regressions pass |
| 8 | [SQL semantic context](2026-08-04-knowledge-base-rag-batch-08-sql-semantic-context.md) | Batches 1-7 | Smart Q&A and dashboard SQL share permissions, Skills, knowledge, and AST enforcement |
| 9 | [Analysis and reports](2026-08-04-knowledge-base-rag-batch-09-analysis-report-context.md) | Batch 8 | Analysis and report surfaces use the same fixed semantic snapshot |
| 10 | [Management UI and rollout](2026-08-04-knowledge-base-rag-batch-10-ui-rollout.md) | Batches 1-9 | UI/build/viewport checks, four-service integration, shared cutover, and runtime gray release pass |

## Requirement Coverage

| Approved requirement | Delivery batch |
| --- | --- |
| Unified knowledge management entry with display, detail, and structured per-item editing | 4 and 10 |
| Markdown/Word upload, authenticated download, immutable history, and full-replacement re-upload | 4, 5, and 10 |
| Combined business terminology and SQL examples | 4 and 10 |
| EVENT parameter mappings and JSON field/path mappings | 4, 5, 7, and 10 |
| Platform-public and workspace knowledge with workspace-specific platform applicability | 3, 5, 7, and 10 |
| Single-item draft, validate, publish, version, rollback, archive, and concurrency behavior | 1, 2, 4, and 5 |
| Preserve existing tracking/data-dictionary logic and keep Skills as an independent management surface | 6, 7, 8, and 10 |
| Preserve platform/workspace/personal Skills and the current selection logic | 6 and 8 |
| Schema, table, field, JSON path, event, event-property, row, and execution permissions | 1, 3, 5, 8, and 9 |
| Smart Q&A and AI dashboard SQL | 8 |
| Comprehensive analysis assistant and dashboard question/report interpretation | 9 |
| Chinese-safe errors and consistent system-management styling | 2, 4, and 10 |
| No knowledge-base MCP behavior | Every batch; local MCP process checks in batch 10 are runbook compliance only |

## Cross-Batch Interface Registry

Implementers must preserve these names and meanings across plans.

```python
class EnqueueOutcome(str, Enum):
    ENQUEUED = "ENQUEUED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EnqueueResult:
    outcome: EnqueueOutcome
    task: dict[str, Any] | None
    error_code: str | None = None


async def enqueue_task_confirmed(
    name: str,
    payload: dict[str, Any] | None = None,
    *,
    created_by: int | None = None,
    tenant_id: int | str | None = None,
    queue_name: str | None = None,
    max_attempts: int | None = None,
    dedupe_key: str | None = None,
) -> EnqueueResult
```

`enqueue_task()` keeps its existing `dict[str, Any]` return contract. Knowledge publishing calls `enqueue_task_confirmed()` directly.

```python
class KnowledgeMigrationPhase(str, Enum):
    LEGACY_OPEN = "LEGACY_OPEN"
    CUTOVER_BARRIER = "CUTOVER_BARRIER"
    V2_ACTIVE = "V2_ACTIVE"


@dataclass(frozen=True)
class DeclaredObjectPath:
    object_type: Literal["SCHEMA", "TABLE", "FIELD", "JSON_PATH", "EVENT", "EVENT_PROPERTY"]
    catalog: str | None = None
    schema: str | None = None
    table: str | None = None
    field: str | None = None
    json_path: str | None = None
    event_name: str | None = None
    event_property_key: str | None = None


@dataclass(frozen=True)
class PermissionScopeSnapshot:
    tenant_id: int
    user_id: int
    datasource_id: int
    permission_version: str
    schema_hash: str
    allowed_object_keys: frozenset[str]
    denied_object_keys: frozenset[str]
    row_constraints_hash: str
```

```python
@dataclass
class KnowledgeRetrievalResult:
    context: str
    citations: list[KnowledgeCitation]
    version_hash: str | None
    warnings: list[str]


@dataclass
class BusinessSemanticContext:
    selected_skills: list[SelectedSkillSnapshot] = field(default_factory=list)
    skill_selection_hash: str | None = None
    tracking_config: str = ""
    tracking_summary: list[str] = field(default_factory=list)
    knowledge_context: str = ""
    knowledge_citations: list[KnowledgeCitation] = field(default_factory=list)
    knowledge_version_hash: str | None = None
    warnings: list[str] = field(default_factory=list)
```

Registered task names are stable protocol values:

```text
knowledge_base.publish_version
knowledge_base.reconcile_publish_jobs
knowledge_base.backfill_v2
data_skill.rebuild_object_projections
knowledge_base.storage_probe
```

## Batch Execution Protocol

- [ ] Before each batch, verify the prior batch's exit gate and record the exact commit SHA in the batch PR description.
- [ ] Run only the batch's focused tests during red/green cycles, then run every regression command listed at the end of that batch.
- [ ] Use one Chinese commit per task unless a task's red/green cycle must remain atomic; do not combine adjacent batches in one commit.
- [ ] Keep `KNOWLEDGE_MANAGEMENT_V2_ENABLED=false` and `KNOWLEDGE_RUNTIME_CONTEXT_ENABLED=false` until the batch plan explicitly changes the rollout state.
- [ ] After batches 1, 3, 5, 8, and 10, run `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_*.py -q` plus the batch-specific permission and surface regressions.
- [ ] Before batch 10 cutover, create a PostgreSQL backup with `tools/postgres-backup-local.ps1`, capture migration phase and backfill counts, and verify all API/Worker builds understand `V2_ACTIVE`.
