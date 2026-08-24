# Verification

- `node --test frontend/src/stores/datasourceContext.selection.test.mjs frontend/src/views/chat/index.datasource-context.test.mjs frontend/src/views/chat/index.workspace-switch.test.mjs frontend/src/stores/workspaceSwitchTransaction.test.mjs` — 13 passed.
- `npm run test:format-arg` — 3 passed.
- `npm run test:permission-json-fields` — passed.
- `npm run build` — passed (`vue-tsc -b` and Vite production build); existing bundle-size and Rollup annotation warnings remain.
- Direct authenticated `GET /api/v1/datasource/accessible/list` check against the core database returned the bound datasource for a valid workspace context.
- Focused ESLint reports existing repository formatting issues and mixed line-ending diagnostics in the touched legacy Vue files; no lint autofix was applied to avoid unrelated formatting churn.
