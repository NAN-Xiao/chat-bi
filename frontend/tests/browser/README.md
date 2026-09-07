# Analysis Picker Browser Regression

Start Vite from this worktree, then from the repository root run:

```powershell
New-Item -ItemType Directory -Path output/playwright -Force
npx --yes --package @playwright/cli playwright-cli -s=analysis-pickers open http://127.0.0.1:5174/tests/browser/analysis-pickers.html
npx --yes --package @playwright/cli playwright-cli -s=analysis-pickers run-code --filename frontend/tests/browser/analysis-pickers.run.js
npx --yes --package @playwright/cli playwright-cli -s=analysis-pickers close
```

Use the port of the current worktree's Vite server. The fixture mounts the actual
editor and field picker, and supplies local metadata without connecting to a
business datasource or persisting a dashboard. The script discovers model labels
from the UI, checks real pointer hit testing after model switches and reopening
the drawer, selects funnel subjects/events, and checks the empty-event state.
It stages the component library's global z-index counter above 5001 to reproduce
a long editing session, then exercises controls with real browser clicks.
Screenshots cover 1280px and 720px viewports. This checks interactions and layering,
not SQL generation, execution, or datasource permissions.
