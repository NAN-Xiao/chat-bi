# Knowledge Base RAG Batch 02 Legacy Barrier and Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make legacy writes cutover-aware and provide atomic, observable, recoverable Redis enqueue semantics before any V2 publishing path is enabled.

**Architecture:** Centralize database phase locking in a migration-state repository, preserve the legacy API only while `LEGACY_OPEN`, and add a confirmed enqueue API without breaking existing callers. Treat the database publish job as authoritative and Redis as transport; use reconciliation to resolve ambiguous client outcomes and storage-probe readiness.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL row locks, Redis Lua, existing task Worker, pytest, PowerShell.

## Global Constraints

- `enqueue_task()` keeps its existing return contract; add `enqueue_task_confirmed()` for the publication path.
- Confirmed enqueue returns only `ENQUEUED`, `REJECTED`, or `UNKNOWN` and never guesses success after a Redis connection loss.
- Old API and old BackgroundTask/Worker writes take a shared phase lock in every writeback transaction.
- `V2_ACTIVE + flag=false` does not reopen old writes; `LEGACY_OPEN + flag=true` does not open V2 writes.
- New expected errors use Chinese safe messages.
- Use scoped Redis key helpers and the same `local-*` queue for API and Worker.
- Use `KNOWLEDGE_PUBLISH_TIMEOUT_SECONDS=900`, `KNOWLEDGE_PUBLISH_QUEUE_TIMEOUT_SECONDS=60`, and `KNOWLEDGE_PUBLISH_RECONCILE_INTERVAL_SECONDS=60`.

---

### Task 1: Database-Authoritative Phase Repository and Capability Matrix

**Files:**
- Create: `backend/apps/knowledge_base/repository.py`
- Create: `backend/apps/knowledge_base/cutover.py`
- Modify: `backend/common/core/config.py`
- Test: `backend/tests/test_knowledge_base_cutover.py`
- Test: `backend/tests/test_knowledge_base_legacy_api.py`

**Interfaces:**
- Consumes: `KnowledgeMigrationState` and `KnowledgeMigrationPhase` from batch 1.
- Produces: `KnowledgeMigrationStateRepository.lock_for_legacy_write(session)`, `get_capabilities(session)`, and `KnowledgeCapabilities`.

- [ ] **Step 1: Write the phase matrix tests**

```python
@pytest.mark.parametrize(
    ("phase", "flag", "legacy_write", "v2_write", "mode"),
    [
        ("LEGACY_OPEN", False, True, False, "LEGACY"),
        ("LEGACY_OPEN", True, True, False, "UPGRADING"),
        ("CUTOVER_BARRIER", False, False, False, "MAINTENANCE"),
        ("CUTOVER_BARRIER", True, False, False, "MAINTENANCE"),
        ("V2_ACTIVE", False, False, False, "MAINTENANCE"),
        ("V2_ACTIVE", True, False, True, "V2"),
    ],
)
def test_capability_matrix(phase, flag, legacy_write, v2_write, mode, session):
    set_phase(session, phase)
    result = get_capabilities(session, management_enabled=flag, runtime_enabled=False)
    assert (result.legacy_write_enabled, result.v2_write_enabled, result.management_mode) == (
        legacy_write,
        v2_write,
        mode,
    )
```

- [ ] **Step 2: Run and confirm the repository is missing**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_cutover.py backend/tests/test_knowledge_base_legacy_api.py -q`

Expected: FAIL because the capability and locking interfaces do not exist.

- [ ] **Step 3: Implement phase locking and capability calculation**

```python
@dataclass(frozen=True)
class KnowledgeCapabilities:
    phase: KnowledgeMigrationPhase
    management_mode: Literal["LEGACY", "UPGRADING", "V2", "MAINTENANCE"]
    legacy_write_enabled: bool
    v2_write_enabled: bool
    runtime_context_enabled: bool


class KnowledgeMigrationStateRepository:
    @staticmethod
    def lock_for_legacy_write(session: Session) -> KnowledgeMigrationState:
        row = session.exec(
            select(KnowledgeMigrationState).where(KnowledgeMigrationState.id == 1).with_for_update(read=True)
        ).one()
        if row.phase == KnowledgeMigrationPhase.CUTOVER_BARRIER:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_UPGRADE_IN_PROGRESS",
                message="知识库升级中，请稍后重试。",
                status_code=409,
            )
        if row.phase == KnowledgeMigrationPhase.V2_ACTIVE:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_LEGACY_WRITE_DISABLED",
                message="知识库已升级，请刷新页面后重新操作。",
                status_code=410,
            )
        return row
```

Add explicit config defaults `KNOWLEDGE_MANAGEMENT_V2_ENABLED=false` and `KNOWLEDGE_RUNTIME_CONTEXT_ENABLED=false`.

- [ ] **Step 4: Run phase tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_cutover.py backend/tests/test_knowledge_base_legacy_api.py -q`

Expected: PASS for all flag/phase combinations.

- [ ] **Step 5: Commit the phase authority**

```powershell
git add backend/apps/knowledge_base/repository.py backend/apps/knowledge_base/cutover.py backend/common/core/config.py backend/tests/test_knowledge_base_cutover.py backend/tests/test_knowledge_base_legacy_api.py
git commit -m "feat: 建立知识库新旧写入切换屏障"
```

### Task 2: Atomic Confirmed Enqueue and Original-Task Repair

**Files:**
- Create: `backend/common/core/task_queue_enqueue.py`
- Create: `tests/test_task_queue_confirmed_enqueue.py`
- Modify: `backend/common/core/task_queue.py`
- Test: `backend/tests/test_task_queue_worker.py`
- Test: `tests/test_task_queue_reliability.py`

**Interfaces:**
- Consumes: existing task handler registry and scoped Redis helpers.
- Produces: `EnqueueOutcome`, `EnqueueResult`, `enqueue_task_confirmed()`, and `confirm_or_repair_task()`.

- [ ] **Step 1: Write response-loss and partial-write tests**

```python
async def test_confirmed_enqueue_returns_unknown_after_post_commit_disconnect(redis_faults):
    redis_faults.disconnect_after_eval_success()
    result = await enqueue_task_confirmed("test.echo", {"value": 1}, tenant_id=7, dedupe_key="job:1")
    assert result.outcome is EnqueueOutcome.UNKNOWN
    repaired = await confirm_or_repair_task(result.task["id"], tenant_id=7, queue_name="local-test")
    assert repaired.outcome is EnqueueOutcome.ENQUEUED


async def test_atomic_enqueue_never_leaves_task_outside_queue_indexes(redis_faults):
    redis_faults.fail_before_eval()
    result = await enqueue_task_confirmed("test.echo", {}, tenant_id=7)
    assert result.outcome is EnqueueOutcome.REJECTED
    assert await tenant_queue_size(7, "local-test") == 0
```

- [ ] **Step 2: Run queue tests and confirm non-atomic behavior**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_task_queue_worker.py tests/test_task_queue_reliability.py -q`

Expected: FAIL because confirmed enqueue and repair do not exist.

- [ ] **Step 3: Implement one Lua enqueue transaction and compatibility adapter**

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
```

The Lua script must atomically write task, tenant index, dedupe key, global pending queue, and tenant pending index with TTLs. A pre-script quota/dedupe rejection maps to `REJECTED`; script success maps to `ENQUEUED`; connection loss where execution cannot be proven maps to `UNKNOWN`. `confirm_or_repair_task()` checks the exact task ID and repairs missing queue/index membership without creating a replacement ID. Keep `enqueue_task()` as an adapter that returns `result.task` on `ENQUEUED` and raises on other outcomes. Keep the public compatibility surface in `task_queue.py`, but place the new Lua transaction, enqueue result types, and repair transport logic in the focused `task_queue_enqueue.py` module so the existing large queue/Worker module only contains the necessary integration.

- [ ] **Step 4: Run queue reliability tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_task_queue_worker.py tests/test_task_queue_reliability.py -q`

Expected: PASS, including response loss, pre-commit failure, dedupe, retry, and stale-task recovery.

- [ ] **Step 5: Commit queue reliability**

```powershell
git add backend/common/core/task_queue_enqueue.py backend/common/core/task_queue.py backend/tests/test_task_queue_worker.py tests/test_task_queue_reliability.py tests/test_task_queue_confirmed_enqueue.py
git commit -m "feat: 增加任务队列原子入队与三态确认"
```

### Task 3: Apply the Legacy Write Barrier to API and Delayed Writebacks

**Files:**
- Modify: `backend/apps/knowledge_base/api/knowledge_base.py`
- Modify: `backend/apps/knowledge_base/tasks.py`
- Test: `backend/tests/test_knowledge_base_legacy_api.py`

**Interfaces:**
- Consumes: `KnowledgeMigrationStateRepository.lock_for_legacy_write()` and existing legacy processing task.
- Produces: legacy behavior unchanged in `LEGACY_OPEN`; safe Chinese rejection in barrier/V2 phases.

- [ ] **Step 1: Write API and late-Worker barrier tests**

```python
def test_legacy_save_does_not_store_file_or_schedule_after_barrier(client, upload_file, session):
    set_phase(session, "CUTOVER_BARRIER")
    response = client.post("/knowledge-base/save", files={"file": upload_file}, data=legacy_form())
    assert response.status_code == 409
    assert response.json()["code"] == "KNOWLEDGE_UPGRADE_IN_PROGRESS"
    assert response.json()["message"] == "知识库升级中，请稍后重试。"
    assert uploaded_files() == []


def test_legacy_worker_started_before_barrier_cannot_write_back(session):
    payload = create_pending_legacy_record(session)
    set_phase(session, "CUTOVER_BARRIER")
    assert process_knowledge_base_document(payload)["status"] == "REJECTED_BY_PHASE"


def test_legacy_save_is_permanently_gone_after_v2(client, session):
    set_phase(session, "V2_ACTIVE")
    response = client.post("/knowledge-base/save", data=legacy_form())
    assert response.status_code == 410
    assert response.json()["message"] == "知识库已升级，请刷新页面后重新操作。"
```

- [ ] **Step 2: Run tests and observe legacy write-through**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_legacy_api.py -q`

Expected: FAIL because the current route saves the file and the delayed processor writes without phase locking.

- [ ] **Step 3: Lock before file persistence and before every delayed writeback**

Call `lock_for_legacy_write(session)` before `_save_upload()`, before mutating legacy state, and inside each processor transaction that writes `PROCESSING`, `READY`, `FAILED`, content, task ID, or error state. In `LEGACY_OPEN`, retain current queue-to-BackgroundTask fallback; once the phase lock rejects, never enqueue or add a BackgroundTask.

- [ ] **Step 4: Run the legacy regression**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_legacy_api.py -q`

Expected: PASS, and the original `LEGACY_OPEN` upload/process/delete tests remain green.

- [ ] **Step 5: Commit legacy fencing**

```powershell
git add backend/apps/knowledge_base/api/knowledge_base.py backend/apps/knowledge_base/tasks.py backend/tests/test_knowledge_base_legacy_api.py
git commit -m "fix: 阻止切换屏障后的旧知识写回"
```

### Task 4: Publish-Job Reconciliation Skeleton and Storage Probe Generation

**Files:**
- Create: `backend/apps/knowledge_base/publish_jobs.py`
- Create: `backend/apps/knowledge_base/reconciliation.py`
- Create: `backend/apps/knowledge_base/storage_probe.py`
- Modify: `backend/apps/knowledge_base/tasks.py`
- Modify: `backend/common/core/task_registry.py`
- Modify: `backend/common/core/config.py`
- Modify: `tools/worker-local.ps1`
- Modify: `tools/stack-local.ps1`
- Test: `backend/tests/test_knowledge_base_publish_recovery.py`
- Test: `backend/tests/test_knowledge_base_storage_probe.py`

**Interfaces:**
- Consumes: confirmed enqueue, lifecycle tables, shared `UPLOAD_DIR`, and local queue identity.
- Produces: `reconcile_publish_jobs()`, `rotate_storage_probe_generation()`, `record_storage_probe_receipt()`, and `publishing_workers_ready()`.

- [ ] **Step 1: Write reconciliation and multi-API probe tests**

```python
async def test_unknown_enqueue_keeps_job_queuing_and_reconciles_same_task(session):
    job = make_publish_job(session, status="QUEUING", task_id="task-1")
    await reconcile_publish_jobs(session)
    assert reload(job).task_id == "task-1"
    assert reload(job).status in {"QUEUING", "QUEUED", "RUNNING"}


def test_concurrent_api_startup_keeps_one_probe_generation(session_factory):
    generations = run_concurrently(8, lambda: rotate_storage_probe_generation(session_factory, config_hash="same"))
    assert len(set(generations)) == 1
```

- [ ] **Step 2: Run tests and confirm services are missing**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_publish_recovery.py backend/tests/test_knowledge_base_storage_probe.py -q`

Expected: FAIL on missing reconciliation and probe services.

- [ ] **Step 3: Implement database-authoritative reconciliation and probe readiness**

Reconciliation must lock each due job, confirm/repair its exact Redis task ID, advance only forward with CAS, retain `QUEUING` on `UNKNOWN`, and mark a timed-out job failed only after its deadline and a final confirmation attempt. Probe generation rotates only under a singleton row lock when the storage config hash changes or an explicit rotation is requested. Each active publishing Worker reads the probe bytes, verifies SHA-256, and upserts a generation-scoped heartbeat; document publication readiness requires fresh receipts from every active consumer.

- [ ] **Step 4: Register tasks and pass one local queue to Worker**

Register `knowledge_base.reconcile_publish_jobs` and `knowledge_base.storage_probe`. Ensure `tools/stack-local.ps1` passes its generated `local-*` queue unchanged to `tools/worker-local.ps1`; do not introduce a production `default` fallback.

- [ ] **Step 5: Run focused and orchestration regressions**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_publish_recovery.py backend/tests/test_knowledge_base_storage_probe.py tests/test_stack_local_script.py -q`

Expected: PASS for response loss, Worker race, timeout, concurrent API startup, stale generation, and local queue identity.

- [ ] **Step 6: Commit recovery foundation**

```powershell
git add backend/apps/knowledge_base/publish_jobs.py backend/apps/knowledge_base/reconciliation.py backend/apps/knowledge_base/storage_probe.py backend/apps/knowledge_base/tasks.py backend/common/core/task_registry.py backend/common/core/config.py tools/worker-local.ps1 tools/stack-local.ps1 backend/tests/test_knowledge_base_publish_recovery.py backend/tests/test_knowledge_base_storage_probe.py tests/test_stack_local_script.py
git commit -m "feat: 增加知识发布对账与共享存储探针"
```
