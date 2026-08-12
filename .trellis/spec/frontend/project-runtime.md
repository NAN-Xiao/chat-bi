# Frontend Project Runtime And Quality Gates

## Project Shape

- Frontend source is under `frontend/` and uses Vue 3, TypeScript, Vite, Pinia, and Element Plus.
- The frontend dev server must bind to `0.0.0.0:5173` and proxies API requests through the existing Vite configuration.
- Existing frontend dependencies are installed under `frontend/node_modules`; use the scripts declared in `frontend/package.json`.

## Required Checks

Run the production build from `frontend/`:

```powershell
npm run build
```

The build includes the Vue TypeScript project check (`vue-tsc -b`). Use the existing focused tests when they cover the changed behavior:

```powershell
npm run test:format-arg
npm run test:permission-json-fields
```

`npm run lint` invokes ESLint with the repository's current `--fix` behavior. Review the resulting diff carefully and do not use it as a substitute for runtime verification.

## Runtime And Browser Verification

- After a user-visible change, restart or verify the frontend process serving the page and confirm `http://127.0.0.1:5173/` returns HTTP 200.
- Exercise the changed workflow through the browser, including the real click path for downloads, navigation, authentication, or API-backed actions.
- For Blob-backed browser downloads, remove the temporary anchor after its click but defer `URL.revokeObjectURL(...)` until a later task. Revoking the URL in the click call stack can race the browser's download handoff.
- Check representative desktop and mobile viewports for every affected primary page.
- Confirm page-level horizontal overflow is absent:

```javascript
document.documentElement.scrollWidth <= document.documentElement.clientWidth + 2
```

- For desktop top bars, also verify the navigation/action container has no hidden overflow by comparing its `scrollWidth` and `clientWidth`.
- Save and inspect screenshots for affected primary pages when validating layout or other user-visible changes.

## Data And Rendering Rules

- Use the currently selected and authorized datasource context; do not infer a datasource from question wording or semantic examples.
- Preserve generic chart configuration when copying a chart between Smart Q&A and dashboards, including axes, columns, insight/summary, pivot, datasource, SQL, and result data.
- Bind chart libraries to the component-owned DOM ref. Do not globally query chart IDs because duplicate source records can be rendered in dialogs, previews, and dashboards at the same time.
- Do not silently substitute a first column or another field when an explicit chart field is missing or invalid. Clear the invalid configuration or show an actionable validation state.
- Keep the Smart Q&A analysis/prediction actions and theme infrastructure compatible while their current product switches remain disabled.

## UI Quality

- Keep management views scannable: readable cards or dense tables, visible status/action columns, and pagination attached to the list it controls.
- Avoid rendering long AI reports or logs in the first viewport of management consoles.
- Verify that labels, buttons, and dynamic content fit their containers at both desktop and mobile widths.
- In the top-navigation workspace management shell, keep the desktop workspace sidebar at `240px`, but collapse it to a `64px` icon rail at `680px` and below. Hide sidebar labels/header and reduce content padding so management pages retain a usable mobile content width and the root document stays within `clientWidth + 2`.
