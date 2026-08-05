# Knowledge Base RAG Batch 06 Backfill and Cutover Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repeatable legacy-document backfill, incremental catch-up, Data Skill object-projection rebuild, dual-read verification, and an isolated-environment cutover rehearsal command.

**Architecture:** Scan authorities by primary-key cursor, identify source revisions with stable fingerprints, and create immutable V2 versions idempotently. The cutover command takes an exclusive migration-state lock, verifies compatible builds and drained legacy writes, performs a final catch-up and dual-read gate, then changes phase atomically; shared environments must not run that transition in this batch.

**Tech Stack:** SQLAlchemy, PostgreSQL locks, registered Redis tasks, existing Worker, argparse, pytest.

## Global Constraints

- Shared/local development database phase remains `LEGACY_OPEN` after this batch.
- Cutover tests use an isolated test database and fake Worker/API heartbeat inventory.
- Backfill never modifies or deletes legacy `knowledge_base.content/file_id/status`.
- Stable migration identity is `legacy_id + source_fingerprint`, where fingerprint includes normalized content hash, `update_time`, and `file_id`.
- Skill projection rebuild does not modify Skill text, scope, enable state, owner, selection rules, or embedding.
- A failed or interrupted scan resumes from database cursor/counters and is safe to run repeatedly.

---

### Task 1: Idempotent Legacy Knowledge Backfill

**Files:**
- Create: `backend/apps/knowledge_base/backfill.py`
- Modify: `backend/apps/knowledge_base/tasks.py`
- Modify: `backend/common/core/task_registry.py`
- Test: `backend/tests/test_knowledge_base_backfill.py`

**Interfaces:**
- Consumes: legacy knowledge rows, migration state cursor, lifecycle repository, and publication/index task.
- Produces: `legacy_source_fingerprint()`, `backfill_v2_page()`, `run_backfill_v2()`, and task `knowledge_base.backfill_v2`.

- [ ] **Step 1: Write rerun, source-change, and status mapping tests**

```python
def test_backfill_rerun_does_not_duplicate_version(session, ready_legacy_row):
    first = run_backfill_v2(session, page_size=20)
    second = run_backfill_v2(session, page_size=20, restart_scan=True)
    assert version_count_for_legacy(ready_legacy_row.id) == 1
    assert first.created == 1
    assert second.skipped == 1


def test_changed_legacy_source_creates_new_migration_version_without_mutating_old(session, ready_legacy_row):
    run_backfill_v2(session)
    old_version = current_migrated_version(ready_legacy_row.id)
    update_legacy_content(ready_legacy_row.id, "new")
    run_backfill_v2(session, restart_scan=True)
    assert current_migrated_version(ready_legacy_row.id).id != old_version.id
    assert reload_version(old_version.id).payload == old_version.payload
```

- [ ] **Step 2: Run and confirm backfill is absent**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_backfill.py -q`

Expected: FAIL on missing backfill services.

- [ ] **Step 3: Implement cursor scan and stable fingerprint mapping**

Map legacy `READY` plus non-empty content to `PUBLISHED` with `index_status=PENDING`; map `PENDING/PROCESSING/FAILED` to an editable draft with safe error summary. Before final mapping/index switch, recompute source fingerprint under the legacy shared phase lock; if changed, discard the stale result and enqueue the ID for the next incremental page. Persist cursor and counters after each page.

- [ ] **Step 4: Run backfill tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_backfill.py backend/tests/test_knowledge_base_legacy_api.py -q`

Expected: PASS for restart, duplicate task, content change, file change, legacy status mapping, and no legacy mutation.

- [ ] **Step 5: Commit legacy backfill**

```powershell
git add backend/apps/knowledge_base/backfill.py backend/apps/knowledge_base/tasks.py backend/common/core/task_registry.py backend/tests/test_knowledge_base_backfill.py
git commit -m "feat: 增加可续跑的旧知识幂等回填"
```

### Task 2: Data Skill Object Projection Rebuild

**Files:**
- Create: `backend/apps/chat/curd/skill_object_references.py`
- Create: `backend/apps/chat/task/data_skill_object_projection.py`
- Modify: `backend/apps/chat/curd/custom_prompt_manage.py`
- Modify: `backend/common/core/task_registry.py`
- Test: `backend/tests/test_data_skill_object_projection.py`

**Interfaces:**
- Consumes: current `custom_prompt.type=DATA_SKILL`, Skill SQL/rules, canonical object projector, and task registry.
- Produces: `skill_projection_source_hash()`, `rebuild_skill_object_projection()`, and task `data_skill.rebuild_object_projections`.

- [ ] **Step 1: Write zero-reference, stale-hash, update, and delete tests**

```python
def test_ready_zero_reference_projection_is_distinct_from_missing(session, neutral_skill):
    rebuild_skill_object_projection(session, neutral_skill.id)
    state = projection_state(neutral_skill.id)
    assert (state.status, state.reference_count) == ("READY", 0)


def test_skill_update_marks_old_projection_stale_without_changing_selection_fields(session, skill):
    before = selection_snapshot(skill)
    update_skill_prompt(session, skill.id, "select * from public.orders")
    assert projection_state(skill.id).status == "PENDING"
    assert selection_snapshot(reload_skill(skill.id)) == before
```

- [ ] **Step 2: Run and confirm projection state is absent**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_data_skill_object_projection.py -q`

Expected: FAIL because Skill object projections are not built.

- [ ] **Step 3: Implement source-hash projection and write-path invalidation**

Hash only fields that can alter object dependencies, including SQL/rules/required tables and datasource scope. Project SQL AST and structured rules; set `READY` with exact reference count, or `FAILED` with safe error code. On Skill create/update commit, upsert `PENDING` and enqueue rebuild; on delete, delete projection state and derived references. Cursor-backfill all platform/workspace/personal Skills without changing current `find_data_skills` behavior.

- [ ] **Step 4: Run Skill projection and existing Skill regressions**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_data_skill_object_projection.py backend/tests/test_custom_prompt_datasource_scope.py backend/tests/test_data_skill_conflict_regressions.py -q`

Expected: PASS; original scope, owner, override, foundation, and selection data are unchanged.

- [ ] **Step 5: Commit Skill projection rebuild**

```powershell
git add backend/apps/chat/curd/skill_object_references.py backend/apps/chat/task/data_skill_object_projection.py backend/apps/chat/curd/custom_prompt_manage.py backend/common/core/task_registry.py backend/tests/test_data_skill_object_projection.py
git commit -m "feat: 补建 Data Skill 对象安全投影"
```

### Task 3: Incremental Catch-Up and Dual-Read Verification

**Files:**
- Modify: `backend/apps/knowledge_base/backfill.py`
- Create: `backend/apps/knowledge_base/source_references.py`
- Test: `backend/tests/test_knowledge_base_backfill.py`
- Test: `backend/tests/test_knowledge_base_source_references.py`

**Interfaces:**
- Consumes: source fingerprints, V2 version/index state, and legacy rows.
- Produces: `catch_up_changed_sources()` and `verify_legacy_v2_parity()`.

- [ ] **Step 1: Write concurrent legacy-write and parity tests**

```python
def test_catch_up_observes_write_committed_before_barrier(session, concurrent_legacy_writer):
    concurrent_legacy_writer.commit_new_content()
    report = catch_up_changed_sources(session)
    assert report.remaining == 0
    assert migrated_content_hash(concurrent_legacy_writer.id) == concurrent_legacy_writer.content_hash


def test_parity_rejects_pending_index(session, migrated_version):
    migrated_version.index_status = "PENDING"
    session.commit()
    assert verify_legacy_v2_parity(session).ready_for_cutover is False
```

- [ ] **Step 2: Run and confirm incremental/parity interfaces are absent**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_backfill.py backend/tests/test_knowledge_base_source_references.py -q`

Expected: FAIL on missing catch-up and parity report.

- [ ] **Step 3: Implement fingerprint catch-up and indexed dual-read comparison**

Compare all changed sources since the stored catch-up watermark plus a bounded overlap window, then verify counts, stable keys, source fingerprints, payload hashes, current version states, index readiness, chunk counts, and reference status. Store only mismatch IDs and hashes. Do not compare or log whole document bodies.

- [ ] **Step 4: Run catch-up tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_backfill.py backend/tests/test_knowledge_base_source_references.py -q`

Expected: PASS for concurrent writes, overlap re-scan, pending indexes, and mismatch redaction.

- [ ] **Step 5: Commit catch-up verification**

```powershell
git add backend/apps/knowledge_base/backfill.py backend/apps/knowledge_base/source_references.py backend/tests/test_knowledge_base_backfill.py backend/tests/test_knowledge_base_source_references.py
git commit -m "feat: 增加旧知识增量追平与双读校验"
```

### Task 4: Isolated Cutover Command and Recovery Rehearsal

**Files:**
- Modify: `backend/apps/knowledge_base/cutover.py`
- Create: `backend/scripts/knowledge_base_migrate.py`
- Test: `backend/tests/test_knowledge_base_cutover.py`

**Interfaces:**
- Consumes: build/Worker heartbeat inventory, exclusive migration-state lock, catch-up, parity, and index readiness.
- Produces: CLI actions `status`, `backfill`, `verify`, `enter-barrier`, `activate-v2`, and `return-legacy`.

- [ ] **Step 1: Write incompatible-build, late-writer, failed-final-scan, and successful-rehearsal tests**

```python
def test_cutover_refuses_incompatible_worker(cutover, old_worker_heartbeat):
    report = cutover.enter_barrier()
    assert report.changed is False
    assert report.code == "KNOWLEDGE_INCOMPATIBLE_WORKER"


def test_isolated_cutover_reaches_v2_only_after_final_parity(cutover):
    assert cutover.enter_barrier().phase == "CUTOVER_BARRIER"
    assert cutover.activate_v2().phase == "V2_ACTIVE"
    assert cutover.current_phase() == "V2_ACTIVE"
```

- [ ] **Step 2: Run and confirm cutover gates are absent**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_cutover.py -q`

Expected: FAIL on missing CLI/service gates.

- [ ] **Step 3: Implement explicit actions with phase compare-and-set**

`enter-barrier` takes the singleton row exclusively, waits for shared legacy writers, verifies every live API/Worker build supports the phase protocol, changes to `CUTOVER_BARRIER`, and commits. `activate-v2` runs final catch-up/parity/index checks under the barrier and CASes to `V2_ACTIVE`. `return-legacy` is accepted only from `CUTOVER_BARRIER`, never from `V2_ACTIVE`. Every command prints phase, revision, counts, mismatch IDs, and safe Chinese failure reason.

- [ ] **Step 4: Rehearse only on an isolated test database**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_cutover.py backend/tests/test_knowledge_base_backfill.py -q`

Expected: PASS for old build, active shared writer, delayed Worker, failed final scan, return to legacy from barrier, and successful V2 transition.

- [ ] **Step 5: Verify the shared database was not changed**

Run: `backend\.venv\Scripts\python.exe backend/scripts/knowledge_base_migrate.py status`

Expected: output includes `phase=LEGACY_OPEN`; do not run `enter-barrier` or `activate-v2` against the shared database in this batch.

- [ ] **Step 6: Commit cutover tooling**

```powershell
git add backend/apps/knowledge_base/cutover.py backend/scripts/knowledge_base_migrate.py backend/tests/test_knowledge_base_cutover.py
git commit -m "feat: 增加知识库切换校验与隔离演练工具"
```
