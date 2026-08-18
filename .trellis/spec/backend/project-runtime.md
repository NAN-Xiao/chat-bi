# Backend Project Runtime And Quality Gates

## Project Shape

- Backend source is under `backend/` and is a Python 3.11 FastAPI application.
- Dependency and tool configuration lives in `backend/pyproject.toml`; the repository keeps a `backend/uv.lock` lockfile.
- The local stack has four processes: API on `0.0.0.0:8000`, MCP on `0.0.0.0:8001`, one Redis-backed task Worker using the API's isolated local queue, and the frontend on `0.0.0.0:5173`.

## Required Checks

Run backend tests from the repository root with the backend virtual environment:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests
```

For Python quality checks, use the tools configured in `backend/pyproject.toml`:

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m mypy backend
```

Do not claim runtime verification from tests alone. For backend behavior, restart or verify the actual process and call the exact endpoint directly. The unauthenticated login-method endpoint is a useful health check:

```text
GET http://127.0.0.1:8000/api/v1/system/getLoginMethod
```

An HTTP 401 can still prove that the API process is listening; unexpected connection failures do not.

## Local Runtime Rules

- Use `tools/stack-local.ps1` for the default local orchestration so API and Worker share the same isolated `local-*` Redis queue.
- The complete local status check must cover API `8000`, MCP `8001`, Worker, and frontend `5173`. Check frontend listening state independently with `Get-NetTCPConnection -LocalPort 5173 -State Listen`.
- Use the repository-root `.env` core database and Redis settings documented in `AGENTS.md`. Do not fall back to the retired local system database.
- Verify `LLM_REQUEST_TIMEOUT=120`, `LLM_TASK_MAX_WAIT_SECONDS=900`, and `LLM_MAX_RETRIES=1` after startup or restart.
- Keep `MCP_ENABLED=false` for ordinary local backend and MCP startup unless MCP access controls are the subject of the test.

## Scenario: Knowledge Management And Runtime Defaults

### 1. Scope / Trigger

- Trigger: starting an API, MCP, or Worker that evaluates knowledge-base management or builds AI context.
- Knowledge management is available by default after the database reaches `V2_ACTIVE`; runtime context and retrieval are also enabled by default but remain independently controllable.

### 2. Signatures

- Environment: `KNOWLEDGE_MANAGEMENT_V2_ENABLED=true|false`, `KNOWLEDGE_RUNTIME_CONTEXT_ENABLED=true|false`, and `KNOWLEDGE_RETRIEVAL_ENABLED=true|false`.
- Local rollback switches: `-DisableKnowledgeManagementV2`, `-DisableKnowledgeRuntimeContext`, and `-DisableKnowledgeRetrieval` on `tools/stack-local.ps1`, `tools/backend-local.ps1`, and `tools/worker-local.ps1`.
- Compatibility switches: the corresponding `-EnableKnowledge...` switches remain accepted, but are not required for the default path.

### 3. Contracts

- All three knowledge flags default to `True` when their environment keys are absent.
- An explicit environment value of `false` overrides the corresponding Python default without changing the other flags.
- Local scripts set all three API, MCP, and Worker flags to `true` unless the corresponding `-DisableKnowledge...` switch is passed.
- The database phase remains authoritative: `CUTOVER_BARRIER` is maintenance regardless of flags, while `V2_ACTIVE + management=true` returns management mode `V2`.

### 4. Validation & Error Matrix

| Input | Required behavior |
| --- | --- |
| No management option or environment override | Management V2 enabled |
| `-EnableKnowledgeManagementV2` | Management V2 enabled |
| `-DisableKnowledgeManagementV2` | API and Worker management V2 disabled |
| Enable and disable switches together | Stop with an explicit conflict error |
| Direct process with `KNOWLEDGE_MANAGEMENT_V2_ENABLED=false` | Management V2 disabled |
| Runtime/retrieval switches omitted | Runtime context and retrieval enabled |
| `-DisableKnowledgeRuntimeContext` | Runtime structured context disabled; retrieval remains enabled |
| `-DisableKnowledgeRetrieval` | Vector retrieval disabled; runtime structured context remains enabled |
| Matching enable and disable switches together | Stop with an explicit conflict error |
| Direct process with either runtime flag set to `false` | Only that runtime capability is disabled |

### 5. Good/Base/Bad Cases

- Good: the default stack starts API, MCP, and Worker with management, structured runtime context, and vector retrieval enabled.
- Base: an operator disables one runtime capability during rollback; API, MCP, and Worker receive the same explicit `false` without changing the other capability.
- Bad: API and Worker receive different runtime flags, or a local script silently writes `false` merely because a compatibility enable switch was omitted.

### 6. Tests Required

- Settings test: assert all missing environment keys resolve to `True` and an explicit `false` affects only its matching flag.
- Script contract test: assert backend and Worker environment functions default all three flags to `true` and each disable switch produces `false`.
- Stack propagation test: assert all enable and disable switches are forwarded to both API/MCP and Worker scripts.
- Conflict test: assert every local script rejects simultaneous matching enable and disable switches.
- Capability test: assert `V2_ACTIVE` resolves to `V2` by default and to maintenance when explicitly disabled.

### 7. Wrong vs Correct

#### Wrong

```powershell
$env:KNOWLEDGE_MANAGEMENT_V2_ENABLED = if ($EnableKnowledgeManagementV2) { "true" } else { "false" }
```

#### Correct

```powershell
$env:KNOWLEDGE_MANAGEMENT_V2_ENABLED = if ($DisableKnowledgeManagementV2) { "false" } else { "true" }
$env:KNOWLEDGE_RUNTIME_CONTEXT_ENABLED = if ($DisableKnowledgeRuntimeContext) { "false" } else { "true" }
$env:KNOWLEDGE_RETRIEVAL_ENABLED = if ($DisableKnowledgeRetrieval) { "false" } else { "true" }
```

## Data Safety

- Run or confirm a PostgreSQL backup before risky schema or data changes with `tools/postgres-backup-local.ps1`.
- Migrations and seed repair must preserve administrator-created records. Do not add destructive cleanup based on a fixed seed list.
- Shared Redis state must use the scoped helpers in `backend/common/core/redis_client.py`; never introduce naked keys such as `dashboard:{id}` or `sql:{hash}`.
- Keep datasource, tenant, user, and permission boundaries in cache and task state whenever those boundaries can affect the result.

## Scenario: OpenAI-Compatible Embedding Batch Limit

### 1. Scope / Trigger

- Applies whenever API or Worker code sends one or more texts to an
  OpenAI-compatible embedding endpoint, including knowledge publication,
  semantic retrieval, Data Skill embedding, and datasource/table embedding.

### 2. Signatures

- Application setting: `Settings.EMBEDDING_BATCH_SIZE: int`.
- Runtime environment: `EMBEDDING_BATCH_SIZE=<positive integer>`.
- Release input: `SHUZHI_EMBEDDING_BATCH_SIZE=<positive integer>`.
- Client entry point: `OpenAICompatibleEmbeddings.embed_documents(texts)`.

### 3. Contracts

- The conservative application and installer default is `10`; deployments may
  explicitly choose another positive value supported by their provider.
- Release configuration maps `SHUZHI_EMBEDDING_BATCH_SIZE` to
  `EMBEDDING_BATCH_SIZE`. API and Worker processes in one deployment must receive
  the same explicit value.
- Inputs larger than the configured value are split into ordered batches. The
  combined result preserves both input order and output cardinality.
- The contract is provider-capability driven, not model-name driven. Do not add
  special branches for `text-embedding-v4` or any business knowledge type.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Runtime value omitted in direct development startup | Use application default `10` |
| Release input omitted | Stop environment generation with an explicit missing-variable error |
| Input contains 23 texts and batch size is 10 | Send batches `10`, `10`, and `3` |
| Provider rejects a configured batch | Propagate the upstream request error; do not silently retry smaller batches |
| Provider returns a different vector count | Raise an explicit cardinality mismatch error |
| Input is empty | Return an empty vector list without an HTTP request |

### 5. Good/Base/Bad Cases

- Good: API and Workers all run with `EMBEDDING_BATCH_SIZE=10`, and a 23-text
  request returns 23 ordered vectors after three provider requests.
- Base: a deployment explicitly configures a provider-supported value other than
  10; every embedding path respects that value.
- Bad: the API uses one value while Workers use another, a publisher falls back
  to a literal `32`, or code catches HTTP 400 and silently retries smaller batches.

### 6. Tests Required

- Assert the settings default is 10 and an explicit positive environment value
  is preserved.
- Assert 23 inputs at batch size 10 produce request sizes `10, 10, 3` and ordered
  output with the same cardinality.
- Assert publisher paths without a model-local config use the shared setting.
- Assert `installer/install.conf`, the installer template, and `Jenkinsfile`
  propagate the release input into the runtime environment.

### 7. Wrong vs Correct

#### Wrong

```python
batch_size = getattr(model.config, "batch_size", 32)
```

#### Correct

```python
batch_size = getattr(model.config, "batch_size", settings.EMBEDDING_BATCH_SIZE)
```

## API Verification

- Call the exact backend endpoint directly before testing a frontend workflow that depends on it.
- Test authenticated routes with a real local auth flow or an explicitly prepared test token; do not treat an unauthenticated error as proof that the route's business behavior works.
- Preserve audit/history records and response error shapes when changing lifecycle, permission, migration, or task behavior.

## Scenario: Frontend And Backend Release Alignment

### 1. Scope / Trigger

- Trigger: a frontend release adds or changes an API capability probe, route, response field, or mode-selection contract.
- The frontend and backend deployed for one environment must come from the same target release line. A successful build of another branch does not validate the requested release.

### 2. Signatures

- Knowledge management capability probe: `GET /api/v1/knowledge-base/capabilities`.
- Knowledge management list: `GET /api/v1/knowledge-base/list`.
- The final application router in `backend/apps/api.py`, not only a feature-local router, must register both methods and paths.

### 3. Contracts

- The capability response contains `phase`, `management_mode`, `legacy_write_enabled`, `v2_write_enabled`, and `runtime_context_enabled`.
- `management_mode` is one of `LEGACY`, `UPGRADING`, `V2`, or `MAINTENANCE`.
- The frontend may render the legacy management surface only when the capability response explicitly contains `management_mode: "LEGACY"`.
- HTTP errors, malformed responses, and transport failures are capability-unavailable states. They must remain visible errors and must not be converted to `LEGACY` or an empty list.
- Before deployment, verify that the CI branch parameter and checkout `BranchSpec` select the same target release as the frontend and backend artifacts.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Capability returns `200` with a valid mode | Render the matching management state |
| Capability returns `404`, `405`, `5xx`, or a transport error | Show capability unavailable with retry; do not load legacy cards |
| Capability payload has a missing or unknown mode | Treat it as capability unavailable |
| List returns `200` with `[]` | Show the real empty state |
| List returns an HTTP or transport error | Show list error with retry; do not show the empty state |
| CI checkout branch differs from the requested release | Stop release verification and correct the pipeline selection before deployment |

### 5. Good/Base/Bad Cases

- Good: release 2.0 frontend and backend are built from the release 2.0 branch, both routes return the expected contracts, and the V2 page loads.
- Base: the backend explicitly returns `LEGACY`; the frontend renders the legacy management page without synthesizing that mode locally.
- Bad: a release 2.0 frontend is deployed with a release 1.0 backend, receives `405` from the capability probe, and silently displays the legacy empty state.

### 6. Tests Required

- Backend route regression: inspect the final `apps.api.api_router` and assert `GET` is registered for both `/knowledge-base/capabilities` and `/knowledge-base/list`.
- Frontend mode regression: assert valid modes map exactly, while null, unknown, and failed capability loads resolve to the explicit unavailable state.
- Frontend list regression: assert an empty success and a failed request render different states and that the failed request exposes retry.
- Deployment verification: record the requested branch, CI checkout branch/commit, running image identifier, and direct capability endpoint result.

### 7. Wrong vs Correct

#### Wrong

```ts
try {
  return await loadCapabilities()
} catch {
  return { management_mode: 'LEGACY' }
}
```

#### Correct

```ts
try {
  return resolveKnowledgePageMode(await loadCapabilities())
} catch {
  return 'CAPABILITIES_UNAVAILABLE'
}
```

## Scenario: Knowledge Base Permanent Deletion And Source Cleanup

### 1. Scope / Trigger

- Trigger: permanently removing archived V2 knowledge bases, deleting never-published knowledge bases, or replacing a draft source file.
- Archiving remains reversible and retains versions; permanent deletion is the explicit irreversible storage-reclamation boundary.

### 2. Signatures

- Archive or delete never-published knowledge: `DELETE /api/v1/knowledge-base/{id}`.
- Permanently delete archived knowledge: `DELETE /api/v1/knowledge-base/{id}/permanent`.
- Removal response: `{ id, archived, deleted, file_cleanup: { deleted, missing, referenced, failed } }`.
- Source cleanup helper: `cleanup_unreferenced_source_files(session, file_ids)`.

### 3. Contracts

- Permanent deletion requires the existing `require_manage` permission and `knowledge_base.archived = true`.
- Clear `draft_version_id`, `current_version_id`, and `publishing_version_id` before deleting versions.
- Delete `knowledge_publish_job` rows before version rows because the publish-job foreign key uses `RESTRICT`.
- Existing cascades own chunks, applicability rows, source references, semantic object references/resolutions, and workspace overrides.
- Collect source `file_id` values before database deletion, commit the database transaction, then delete only files with no remaining reference in either `knowledge_base` or `knowledge_base_version`.
- Missing files count as cleaned. Reference-query or file-system failures retain the file, log the failure, and increment `file_cleanup.failed` without pretending that the committed database deletion rolled back.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Permanent delete targets current knowledge | `409 KNOWLEDGE_PERMANENT_DELETE_REQUIRES_ARCHIVE` |
| Caller lacks management permission | Existing `KNOWLEDGE_FORBIDDEN` / tenant-safe not-found behavior |
| Knowledge is publishing or validating during archive | Existing lifecycle conflict; do not delete |
| Candidate file is still referenced | Retain it and increment `referenced` |
| Candidate file is already absent | Increment `missing`; do not fail the removal |
| Reference query or unlink fails after commit | Retain the file, log the error, increment `failed` |

### 5. Good/Base/Bad Cases

- Good: an administrator archives a published knowledge base, confirms permanent deletion, dependent rows cascade away, and only unreferenced source files are removed.
- Base: two versions share one source file; replacing or deleting one version retains the file until the final database reference disappears.
- Bad: a route deletes the physical file before commit, bulk-deletes versions before publish jobs, or permanently deletes a current knowledge base without an archived-state check.

### 6. Tests Required

- State-machine test: current knowledge is rejected and archived knowledge returns candidate source file IDs.
- Repository test: publish-job deletion precedes version deletion and record version pointers are cleared.
- Cleanup test: unreferenced, referenced, missing, query-failure, and unlink-failure outcomes remain distinct.
- Upload regression: successful replacement checks the prior `file_id`; parse or revision conflicts clean only the request staging file.
- API/UI tests: response fields remain aligned, only manageable archived rows expose permanent deletion, and confirmation requires the exact knowledge-base name.

### 7. Wrong vs Correct

#### Wrong

```python
AppFileUtils.delete_file(version.file_id)
session.delete(version)
session.commit()
```

#### Correct

```python
candidate_ids = repository.delete_all(record=record)
session.commit()
cleanup = cleanup_unreferenced_source_files(session, candidate_ids)
```
