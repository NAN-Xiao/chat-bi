# Verification

- Database inspection confirmed workspace `flam` is bound to datasource `3` and another affected workspace is bound to datasource `6`; both datasource rows are `Success`.
- Backend logs confirmed `GET /api/v1/datasource/accessible/list` returned `count=1` for the active `flam` workspace.
- Focused datasource, Smart Q&A, and workspace-switch tests: 20 passed.
- `npm run test:format-arg`: 3 passed.
- `npm run test:permission-json-fields`: passed.
- `npm run build`: passed (`vue-tsc -b` and Vite production build); existing Rollup annotation, dynamic import, and chunk-size warnings remain.
- ESLint passed for the datasource store, `ChatCreator.vue`, and both new regression tests after preserving the repository line-ending convention. Full-file lint for legacy `index.vue` remains blocked by pre-existing formatting diagnostics and the pre-existing unused `_index` template variable.
- Vite worktree server: `http://127.0.0.1:5175/` returned the application login page.
- Authenticated browser verification is blocked because the isolated browser has no local application login state and the Chrome browser connection is unavailable. No login credentials were entered or transmitted.
