# Implementation Plan

1. Load `trellis-before-dev` and the backend specs before editing runtime code.
2. Change shared tracking Prompt assembly so event dictionary sections and event-specific summaries are omitted while non-event workspace metadata remains.
3. Remove request event attribute projection from workspace `m-schema` assembly and clean up imports/dead runtime wiring without touching management APIs.
4. Ensure Smart Q&A post-processing does not compensate for the removed channel by querying physical event values.
5. Update focused tests for tracking context, schema assembly, Smart Q&A behavior, event catalog, and Excel management preservation.
6. Run targeted pytest, Ruff on changed backend files, and the Trellis quality check; record commands and results in the task check log.
7. If local runtime verification is required, restart the complete local stack from the task worktree and verify API/MCP/Worker/frontend plus the three LLM timeout values.

## Primary Files

- `backend/apps/system/crud/tracking_config.py`
- `backend/apps/datasource/crud/datasource.py`
- `backend/apps/chat/task/smart_qa_graph.py` if post-check decoupling is required
- `backend/tests/test_tracking_context_projection.py`
- `backend/tests/test_tracking_event_schema_projection.py` or replacement schema assembly tests
- `backend/tests/test_smart_qa_graph.py`

## Validation Commands

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_context_projection.py backend/tests/test_tracking_event_schema_projection.py backend/tests/test_smart_qa_graph.py
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_excel.py backend/tests/test_tracking_event_groups.py backend/tests/test_sql_engine_context.py
backend\.venv\Scripts\python.exe -m ruff check backend/apps/system/crud/tracking_config.py backend/apps/datasource/crud/datasource.py backend/apps/chat/task/smart_qa_graph.py backend/tests/test_tracking_context_projection.py backend/tests/test_smart_qa_graph.py
```

## Rollback Point

Before runtime changes, the task contains planning files only. The runtime change is code-only and can be reverted without database cleanup.

## Implementation Result

- [x] Added a shared AI-only tracking configuration projection that removes event defaults, event mappings, and event groups before Prompt/schema validation.
- [x] Removed event dictionary sections from `<Workspace-Tracking-Rules>` while preserving non-event tables, fields, field roles, SQL rules, and workspace notes.
- [x] Removed request-level event attribute projection from workspace `m-schema` assembly.
- [x] Disabled Smart Q&A physical event probing when the configured-event marker is absent.
- [x] Added regressions for `ShopBuyItem` and `ShopBuyComplete`, including validation-warning leakage.
- [x] Preserved event catalog storage, APIs, permissions, event groups, and Excel import/export behavior.
- [ ] Runtime stack restart was not performed: ports `5173`, `8000`, and `8001` are owned by other running worktrees, and this worktree has no local `backend/.venv`; those processes were left untouched.
