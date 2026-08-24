# Quality Check

## Root Cause And Fix

- The workspace event dictionary reached AI through two shared paths: event sections in `<Workspace-Tracking-Rules>` and request-level event attribute projection in `m-schema`.
- Removing those renderers alone was insufficient because invalid event defaults could still leak through schema-validation warnings.
- `project_tracking_config_for_ai_context()` now strips event defaults, mappings, and groups before Prompt or schema validation, while preserving non-event workspace metadata.
- Smart Q&A skips event availability probing when `<Configured-Event-Names>` is absent and does not replace the removed channel with physical-table discovery.

## Verification

- Core regression: `123 passed` across tracking Prompt, event schema projection, tenant schema context, Smart Q&A, and tracking Excel tests.
- Related cross-entry regression: `313 passed`.
- Full backend regression: `1709 passed, 8 skipped, 15 failed`; all 15 failures are existing unrelated test-environment baselines involving fake sessions without `exec()` or SQLite missing `sys_tenant.roi_project_id`.
- Focused Ruff for task-owned code/tests: passed.
- Ruff `F` checks for all changed Python files: passed. Full changed-file Ruff reports 33 existing violations in older large modules/tests.
- Python compilation: passed.
- `git diff --check`: passed.
- Mypy could not start because the shared virtual environment is missing `0aca9ce3d91742c5b361__mypyc`; no type-check result is claimed.

## Runtime

- Read-only status found API `8000`, MCP `8001`, and frontend `5173` already owned by other running worktrees; the frontend process explicitly points to `remove-legacy-knowledge-status`.
- This linked worktree does not contain `backend/.venv`, so its standard Worker status/start command cannot resolve the interpreter.
- No existing process was stopped or replaced. Runtime stack verification remains unclaimed; the behavior is covered by shared-context and no-physical-probe regressions.

## Review Result

- All PRD acceptance criteria are covered by the implementation and regression tests.
- No unresolved task-related correctness finding remains.
