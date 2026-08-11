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

## Data Safety

- Run or confirm a PostgreSQL backup before risky schema or data changes with `tools/postgres-backup-local.ps1`.
- Migrations and seed repair must preserve administrator-created records. Do not add destructive cleanup based on a fixed seed list.
- Shared Redis state must use the scoped helpers in `backend/common/core/redis_client.py`; never introduce naked keys such as `dashboard:{id}` or `sql:{hash}`.
- Keep datasource, tenant, user, and permission boundaries in cache and task state whenever those boundaries can affect the result.

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
