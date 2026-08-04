---
name: update-slg-bi-mock
description: Use when regenerating, refreshing, or repairing the SLG BI Mock database, especially when 投放看板 or 出征看板 is empty, stale, or points at the wrong dates.
---

# Update SLG BI Mock

Use the repository's complete pipeline for SLG BI Mock data updates. The pipeline binds to the datasource currently assigned to the example workspace, creates a PostgreSQL backup before mutation, then runs the three required data stages in order.

## Required Workflow

1. Confirm the requested business date window. Do not repair a date problem by changing dashboard JSON alone.
2. Run from the repository root with the project virtual environment:

```powershell
.\backend\.venv\Scripts\python.exe .\tools\seed_slg_bi_mock_complete.py --recreate
```

3. Treat the command as fail-fast. The stages are:

   - `create_slg_bi_mock.py`: base dimensions and event/detail facts.
   - `seed_slg_bi_acquisition_dashboard.py`: player acquisition attribution and cost fields used by 投放看板.
   - `seed_slg_bi_expedition_dashboard.py`: `fact_expeditions` detail rows and 出征看板 payloads.

4. Do not continue to a later stage after a non-zero exit code. Preserve the backup path and the first failing stage in the report.
5. After completion, verify the output contains successful counts for the base stage, attributed players for 投放, expedition rows for 出征, and non-empty chart results. A dashboard refresh without these checks is not proof of a successful update.

## Datasource Rules

- Resolve the example workspace's tenant from the canonical expedition dashboard, then resolve its current `core_datasource_tenant_binding` entry named `SLG BI Mock`.
- Use the decrypted datasource host, port, database, user, and password for every stage.
- Never substitute `127.0.0.1`, `postgres/111111`, datasource ID `1`, or a tenant-name lookup when the binding query fails.
- If the dashboard, binding, PostgreSQL type, or encrypted configuration is missing, stop and report the exact error.

## Backup And Recovery

The complete pipeline performs the backup before `--recreate` can drop the database. Do not run the base generator directly with `--recreate` unless the same backup has already succeeded. Backups belong under `.codex-runtime/pg-backups` and must not be committed.

## Date And Scope Checks

- Use one explicit start/end window for the generation request and check the generated tables' `min(event_date)` and `max(event_date)` afterward.
- The pipeline above covers base, 投放, and 出征 data. It does not claim that every other recommended dashboard has been regenerated.
- If a dashboard still has no data, inspect its dependency script and table before changing its SQL or cached chart payload.

## Common Mistakes

- Running only the base generator and assuming 投放/出征 enrichment exists.
- Running the three scripts with different database credentials.
- Clicking chart refresh before checking the underlying detail tables.
- Continuing after a failed child script and overwriting dashboards with empty results.
- Reporting success without recording the backup and row/date verification output.

## Repository Entry Points

- Pipeline: `tools/seed_slg_bi_mock_complete.py`
- Base data: `tools/create_slg_bi_mock_db.py`
- Acquisition data: `tools/seed_slg_bi_acquisition_dashboard.py`
- Expedition data: `tools/seed_slg_bi_expedition_dashboard.py`
- Backup helper: `tools/postgres-backup-local.ps1`
