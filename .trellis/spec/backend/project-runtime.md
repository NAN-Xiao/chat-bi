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
