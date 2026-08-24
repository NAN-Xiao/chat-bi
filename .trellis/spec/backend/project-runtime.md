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

## Scenario: Shared Local File Artifacts Across Linked Worktrees

### 1. Scope / Trigger

- Trigger: starting API, MCP, Worker, or the standalone local development script from a Git linked worktree while the processes share the core application database.
- Database file references are meaningful only when every process that can upload, publish, or download the referenced artifact uses the same physical file root.

### 2. Signatures

- Resolver: `Resolve-SharedRuntimeRoot -WorkspaceRoot <path>` in `tools/local-runtime-paths.ps1`.
- Shared environment keys: `UPLOAD_DIR`, `EXCEL_PATH`, and `MCP_IMAGE_PATH`.
- Worktree-private environment keys and state: `BASE_DIR`, `LOCAL_MODEL_PATH`, logs, PID files, and queue metadata.

### 3. Contracts

- Resolve the primary checkout from `git rev-parse --path-format=absolute --git-common-dir`; use the primary checkout's `.codex-runtime` for file artifacts.
- API, MCP, Worker, and `tools/dev-local.ps1` must use the same resolver and directory mapping.
- Keep process ownership and transient runtime state under the current worktree's `.codex-runtime` so one development stack cannot stop or overwrite another.
- If Git common-dir resolution fails or does not identify a normal `.git` directory, use only the current workspace's `.codex-runtime`; do not search arbitrary worktrees or legacy storage roots.
- Never reconstruct a missing uploaded source from normalized database content. The original file must be uploaded again.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| API and Worker run from the same linked worktree | Both receive identical shared file artifact roots |
| A different linked worktree reads the shared database reference | It resolves the same primary-checkout file root |
| Git common-dir lookup fails | Use the current workspace runtime root explicitly |
| Database reference exists but physical source file is missing | Return the existing explicit source-file-not-found error |
| Two local stacks run simultaneously | Their logs, PIDs, and queue metadata remain isolated |

### 5. Good/Base/Bad Cases

- Good: a source uploaded by one linked worktree can be published by its Worker and downloaded by another API process because all three use the primary checkout artifact root.
- Base: a normal non-worktree checkout resolves its own `.codex-runtime` as both the primary and shared artifact root.
- Bad: each worktree stores `UPLOAD_DIR` under itself while sharing database rows, or the downloader silently generates a replacement file from normalized content.

### 6. Tests Required

- Execute the resolver inside a real linked worktree and assert it equals `<git-common-dir-parent>/.codex-runtime`.
- Contract-test all local startup entry points for shared `UPLOAD_DIR`, `EXCEL_PATH`, and `MCP_IMAGE_PATH` mappings.
- Assert `BASE_DIR`, `LOCAL_MODEL_PATH`, logs, PIDs, and queue metadata do not use the shared artifact root.
- Exercise a real browser download whose file exists only in the primary checkout and confirm the API returns HTTP 200.

### 7. Wrong vs Correct

#### Wrong

```powershell
$env:UPLOAD_DIR = "$workspaceRootUnix/.codex-runtime/file"
$env:BASE_DIR = "$workspaceRootUnix/.codex-runtime/shuzhi"
```

#### Correct

```powershell
$sharedRuntimeRoot = Resolve-SharedRuntimeRoot -WorkspaceRoot $workspaceRoot
$env:UPLOAD_DIR = "$($sharedRuntimeRoot.Replace('\', '/'))/file"
$env:BASE_DIR = "$workspaceRootUnix/.codex-runtime/shuzhi"
```

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

## Scenario: Knowledge Version Retention

### 1. Scope / Trigger

- Trigger: creating a knowledge-base draft, creating a rollback draft, or changing version-history retention.
- Each knowledge base physically retains at most 10 versions; this is a storage contract, not a frontend display limit.

### 2. Signatures

- Repository: `KnowledgeVersionRepository.prune_versions(tenant_id, knowledge_base_id, retain=10) -> tuple[str, ...]`.
- Protected pointers: `current_version_id`, `draft_version_id`, and `publishing_version_id`.
- Active publish-job statuses: `QUEUING`, `QUEUED`, and `RUNNING`.

### 3. Contracts

- Compute retention under the knowledge-base row lock and scope every query/delete by both tenant and knowledge-base ID.
- Keep protected pointer/job versions first, then fill the retained set by descending `version_number` until it contains 10 versions.
- Delete publish jobs for discarded versions before deleting the versions because `knowledge_publish_job.version_id` uses `ON DELETE RESTRICT`.
- Version-owned chunks, applicability records, and reference projections use `ON DELETE CASCADE`; do not duplicate manual deletion for those tables.
- Commit database deletion before passing discarded `file_id` values to `cleanup_unreferenced_source_files`.
- Keep version numbers monotonic; never renumber retained versions or reuse deleted version numbers.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Version count is 10 or fewer | Do not query jobs or delete records/files |
| Creating version 11 | Retain 10 protected/newest versions and delete the remainder |
| Discarded version has completed/failed jobs | Delete those jobs before the version |
| A candidate file is still referenced | Keep the physical file |
| Physical file cleanup fails after commit | Log the failed IDs; keep the committed version result successful |
| A pointer or active job references an older version | Protect it instead of deleting live state |

### 5. Good/Base/Bad Cases

- Good: the API creates a new draft, prunes in the same database transaction, commits, then reclaims only globally unreferenced source files.
- Base: a knowledge base with exactly 10 versions creates no cleanup side effects until another version is created.
- Bad: return only 10 rows in the API or slice the frontend array while old versions and vectors continue accumulating.

### 6. Tests Required

- Repository unit test: assert protected selection, tenant/knowledge scoping, job-before-version deletion, and returned file candidates.
- PostgreSQL transaction test: assert 11 versions become 10, the `RESTRICT` job is removed, and `CASCADE` removes chunks; roll the fixture transaction back.
- API test: assert normal draft creation and rollback creation both use the shared retention/commit path.
- File test: assert shared files remain and cleanup failure cannot turn an already committed creation into an API failure.

### 7. Wrong vs Correct

#### Wrong

```python
versions = versions[:10]
```

#### Correct

```python
source_file_ids = repository.prune_versions(
    tenant_id=tenant_id,
    knowledge_base_id=knowledge_base_id,
)
session.commit()
cleanup_unreferenced_source_files(session, source_file_ids)
```

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

## Scenario: Reproducible SSR Docker Dependency Build

### 1. Scope / Trigger

- Trigger: changing `g2-ssr` dependencies, the SSR Docker build stage, the Node base image, or the Jenkins Docker image build stage.
- The SSR dependency layer must remain reproducible and must not wait indefinitely on third-party native binary hosts.

### 2. Signatures

- Dependency manifest: `g2-ssr/package.json`.
- Required lockfile: `g2-ssr/package-lock.json` with lockfile version 3.
- Docker install command: `npm_config_build_from_source=true npm ci` with a BuildKit cache mounted at `/root/.npm`.
- Jenkins stage: `stage('构建 Docker 镜像')` with `timeout(time: 20, unit: 'MINUTES')`.

### 3. Contracts

- Every committed SSR dependency change updates `package.json` and `package-lock.json` together.
- Docker builds use `npm ci`; do not use `npm install` for the SSR image layer.
- Native SSR packages compile from source using the development libraries installed in the `ssr-builder` stage. The normal build path must not depend on GitHub Release prebuilt archives.
- The npm cache is a BuildKit cache only. It is not copied into the runtime image and is not a substitute for the lockfile.
- The Jenkins timeout is a failure boundary, not a fallback. A timeout must fail the build explicitly.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| `package.json` and lockfile agree | `npm ci --ignore-scripts` succeeds |
| Lockfile is missing or stale | Build or contract test fails; do not regenerate silently in Docker |
| Canvas source compilation fails | Docker build fails with the compiler error |
| npm registry or BuildKit stops making progress | Jenkins terminates the image-build stage within 20 minutes |
| GitHub Release binary host is unavailable | SSR dependency installation remains on the source-build path |

### 5. Good/Base/Bad Cases

- Good: a cold build resolves the locked registry packages from the npm cache where available, compiles canvas locally, and completes without a GitHub Release download.
- Base: unchanged dependency inputs reuse the Docker layer cache and skip installation entirely.
- Bad: `RUN npm install` resolves a new graph and `node-pre-gyp` keeps an established GitHub connection open indefinitely.

### 6. Tests Required

- Assert the SSR Docker section copies `package-lock.json`, mounts `/root/.npm`, sets `npm_config_build_from_source=true`, and runs `npm ci`.
- Assert the lockfile includes both the direct SSR package graph and the transitive `canvas` package.
- Assert the Jenkins Docker image stage contains the 20-minute timeout.
- Run `npm ci --ignore-scripts` with npm 10 to prove manifest and lockfile consistency.
- When Docker is available, build the `ssr-builder` target to prove the Linux native toolchain remains complete.

### 7. Wrong vs Correct

#### Wrong

```dockerfile
COPY g2-ssr/package.json /app/
RUN npm install
```

#### Correct

```dockerfile
COPY g2-ssr/package.json g2-ssr/package-lock.json /app/
RUN --mount=type=cache,target=/root/.npm \
    npm_config_build_from_source=true \
    npm ci --prefer-offline --no-audit --no-fund
```

## Scenario: V2 Knowledge Management Contract And Release Alignment

### 1. Scope / Trigger

- Trigger: a frontend release adds or changes a knowledge-management route, response field, or deployment capability contract.
- The frontend and backend deployed for one environment must come from the same target release line. A successful build of another branch does not validate the requested release.

### 2. Signatures

- Knowledge management capability probe: `GET /api/v1/knowledge-base/capabilities`.
- Knowledge management list: `GET /api/v1/knowledge-base/list`.
- The final application router in `backend/apps/api.py`, not only a feature-local router, must register both methods and paths.
- V2 publication task: `knowledge_base.publish_version`.

### 3. Contracts

- The capability response contains `phase`, `management_mode`, `legacy_write_enabled`, `v2_write_enabled`, and `runtime_context_enabled`.
- `management_mode` is one of `LEGACY`, `UPGRADING`, `V2`, or `MAINTENANCE`.
- Capabilities remain deployment and maintenance safety signals. They may block V2 writes, but they must never dispatch a legacy list, delete, upload, or processing path.
- List, detail, create, archive/delete, restore, and permanent-delete behavior is V2-only. `POST /knowledge-base/save` and task `knowledge_base.process_document` must not be registered.
- `knowledge_base` is the identity and version-pointer table. It must not contain or serialize the legacy `status`, `task_id`, or `error_message` columns; version and publish-job tables remain authoritative for validation, indexing, publication, task, and error state.
- The frontend always renders the V2 management surface. Capability failures must not synthesize or restore a legacy page.
- Before deployment, verify that the CI branch parameter and checkout `BranchSpec` select the same target release as the frontend and backend artifacts.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| V2 write is enabled | Execute the V2 lifecycle operation |
| V2 write is disabled or cutover barrier is active | Return the explicit maintenance/upgrade error; do not dispatch legacy code |
| Database is not yet `V2_ACTIVE` | Keep operational capability reporting, but do not expose legacy application writes |
| List returns `200` with `[]` | Show the real empty state |
| List returns an HTTP or transport error | Show list error with retry; do not show the empty state |
| Old client calls `POST /knowledge-base/save` | Return route-not-found behavior; no compatibility fallback |
| CI checkout branch differs from the requested release | Stop release verification and correct the pipeline selection before deployment |

### 5. Good/Base/Bad Cases

- Good: release 2.0 frontend and backend are built from the release 2.0 branch, both routes return the expected contracts, and the V2 page loads.
- Base: deployment is in a maintenance phase; reads remain on the V2 model and writes return an explicit blocked response.
- Bad: a non-V2 phase causes list/delete to call a legacy implementation, or the frontend restores the old card page and displays identity-table processing status.

### 6. Tests Required

- Backend route regression: inspect the final `apps.api.api_router`, assert V2 routes are registered, and assert `/knowledge-base/save` is absent.
- Task registry regression: assert `knowledge_base.process_document` is absent and `knowledge_base.publish_version` remains registered.
- Schema/serialization regression: assert the identity model and API item omit `status`, `task_id`, and `error_message`; test the upgrade/downgrade migration structure.
- Frontend regression: assert the entry contains only `KnowledgeBaseV2Panel`, the list has no processing-status column, and publish-job task/error fields remain typed.
- Frontend list regression: assert an empty success and a failed request render different states and that the failed request exposes retry.
- Deployment verification: record the requested branch, CI checkout branch/commit, running image identifier, and direct capability endpoint result.

### 7. Wrong vs Correct

#### Wrong

```python
if capabilities.phase != KnowledgeMigrationPhase.V2_ACTIVE:
    return await save_legacy_knowledge_base(...)
```

#### Correct

```python
blocked = v2_write_error(capabilities)
if blocked is not None:
    return serialize_error(blocked)
return run_v2_lifecycle_operation(...)
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

## Scenario: Workspace Event Dictionary Is Not AI Context

### 1. Scope / Trigger

- Trigger: building SQL or answer context for Smart Q&A, normal chat, the analysis assistant, dashboard SQL generation, or another consumer of the shared business SQL context.
- Workspace event dictionary records remain management metadata. They are not an AI semantic source and must not be projected into prompts or request-level schema text.

### 2. Signatures

- AI-safe configuration: `project_tracking_config_for_ai_context(config) -> TenantTrackingConfigDTO`.
- Prompt projection: `build_tracking_prompt_context(config, validation_warnings=None, *, datasource_type=None, question=None, data_skill_text=None) -> tuple[str, list[str]]`.
- Schema projection: `get_ai_table_schema(session, current_user, ds, question, embedding=True, table_list=None, data_skill_text=None, tenant_id=None) -> tuple[str, list]`.
- Smart Q&A post-check: `_event_availability_for_sql(service, sql) -> list[_EventAvailability]`.

### 3. Contracts

- `<Workspace-Tracking-Rules>` may contain non-event workspace table and field descriptions, generic field-role mappings, SQL constraints, and workspace notes.
- It must not serialize event names, event-name mappings, event groups, event-specific defaults, or event properties from `TenantTrackingConfigDTO`.
- Workspace `m-schema` must not append `Request event attribute schema`, `# Event:`, `Required predicate`, or JSON expressions derived from the event dictionary.
- When `<Configured-Event-Names>` is absent, event-availability post-checks must remain inactive. They must not compensate by scanning physical event tables or inferring event names from similar fields.
- Event storage, management APIs, catalog APIs, permissions, and Excel import/export remain unchanged. Event text explicitly supplied by the user, Data Skills, knowledge, or ordinary table/field metadata follows the rules of that independent source.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Workspace dictionary contains `ShopBuyItem` and `ShopBuyComplete` | Neither event name appears in tracking Prompt or dictionary-derived `m-schema` |
| The same workspace also contains non-event table/field metadata and SQL rules | Preserve those entries in shared AI context |
| Generated SQL contains an event predicate but the configured-event marker is absent | Skip event-availability probing and rewriting |
| A Data Skill or user question explicitly names an event | Preserve that independent context; do not scrub the text globally |
| An administrator edits, imports, exports, or browses events | Keep the existing management behavior and permissions |

### 5. Good/Base/Bad Cases

- Good: all shared AI entry points receive the same event-free workspace context while administrators can still maintain and export the event catalog.
- Base: a workspace with only table/field descriptions continues to produce the same useful schema and tracking rules.
- Bad: removing event sections from one assistant only, projecting matching event properties into `m-schema`, or querying physical event values after the marker disappears.

### 6. Tests Required

- Prompt regression: assert configured event names, mappings, groups, defaults, and properties are absent while non-event metadata remains.
- Schema regression: assert event projection is not invoked and no event predicate or request-event section is appended.
- Shared-entry regression: cover each shared business SQL context consumer or prove they all call the same sanitized builders.
- Smart Q&A regression: assert removal of the marker cannot trigger a physical event-table query.
- Management regression: keep event catalog, configuration persistence, and Excel import/export tests passing.

### 7. Wrong vs Correct

#### Wrong

```python
if requested_event:
    schema += project_event_schema_fields(tracking_config, physical_schema, question)
```

#### Correct

```python
tracking_context, summary = build_tracking_prompt_context(tracking_config)
# Event catalog data stays in management APIs and is not projected into AI context.
```
