# Verification

- `pytest tests/test_knowledge_base_state_machine.py tests/test_knowledge_base_workspace_management.py -q`: 32 passed.
- `pytest tests/test_knowledge_base_management_api.py -q -k "restore_route_is_registered"`: 1 passed.
- `node --test` for the knowledge layout, document editor, row actions, and
  source-upload contract files: 21 passed.
- `npm run build`: passed (`vue-tsc -b` and Vite production build).
- `git diff --check`: passed; only repository line-ending warnings were emitted.

Additional main-session verification after adding explicit activation:

- Focused backend suite: 42 passed, 2 unrelated tests deselected.
- Ruff on all affected backend and test files: passed.
- Frontend knowledge contract suite: 21 passed.
- Frontend production build (`vue-tsc -b` + Vite): passed.
- Current-workspace runtime instances verified on frontend `5190`, API `8020`,
  MCP `8021`, plus Worker queue `local-DONGJINCHAO-chat-bi_ver`.
- HTTP checks: frontend 200, API authentication boundary 401, MCP root 404.
- Runtime model configuration: `120 900 1`.
- Current repository module-path check confirms `GET /knowledge-base/list`,
  `POST /knowledge-base/{id}/restore`, and `PUT /knowledge-base/{id}/active`.
- Browser checks at desktop and 375 px mobile widths found no document-level
  horizontal overflow. The browser session had no administrator login state,
  so the route guard redirected to login and the authenticated archive-row
  click path could not be exercised.

Authenticated runtime API and browser verification were not run in this
implementation subtask; the local stack/session was not started here.

The complete `test_knowledge_base_management_api.py` file still has two
pre-existing failures unrelated to this task: its application-router fixture
encounters `_IncludedRouter` without `.path`, and its legacy capability
expectation says `LEGACY` while current behavior returns `UPGRADING`.
