# B2B Multi-Tenant ChatBI Architecture

This document records the current product direction for 星通智数 as a commercial B2B ChatBI platform.

## Product Scope

The core user workflow is:

1. Select an authorized datasource.
2. Ask a natural-language data question in Smart Q&A.
3. Generate safe SQL, execute it under datasource permissions, and render a chart.
4. Add the generated chart to a datasource-scoped dashboard.
5. Use custom Agents and the analysis assistant with the same datasource, permission, semantic-layer, and tenant context.

SLG fixtures are demo data only. Runtime code must stay datasource-agnostic and domain-agnostic.

## Tenant Model

- `sys_tenant` stores enterprise tenants and plan information.
- `sys_tenant_user` stores membership and tenant roles: `owner`, `admin`, `member`.
- Request tenant context is resolved from verified login tokens, API keys, or embedded assistant tokens. A user can only switch to a tenant they belong to, except platform administrators.
- Core business assets carry tenant scope: datasource, terminology, SQL examples, custom Agents, ChatBI conversations, chat records, chat logs, dashboards, dashboard shares, API keys, assistants, audit logs, and tenant usage records.

## Permission Model

- Platform administrator: manages platform-wide configuration, tenant approval, production operations, and can switch tenant context for support.
- Tenant `owner/admin`: manages current-tenant users, datasources, public custom Agents, terminology, SQL examples, dashboards, and tenant usage.
- Tenant `member`: can only access explicitly assigned datasources.
- Datasource `viewer/editor`: controls project usage and dashboard editing. It does not grant platform administration.
- Smart Q&A, dashboards, custom Agents, and analysis assistant must all validate tenant and datasource access before reading schema, semantic records, examples, history, SQL, chart data, or execution results.
- Row and column permissions are applied to normal users during schema exposure, SQL validation, SQL execution, chart reload, dashboard load, and analysis assistant execution.

## High Availability

Production should run:

- Nginx or another load balancer as the single external entry.
- Multiple backend API replicas.
- Redis for shared cache, login/rate-limit state, tenant rate limits, task queue, task status, and distributed locks.
- Separate workers for long-running tasks.
- PostgreSQL migrations as a single release step before API replicas start.
- Tenant usage metering and quota enforcement enabled in production.

API replicas must remain stateless. Process-local memory is acceptable only for local development fallback.

## Deployment-Friendly Defaults

- Local development stays simple: frontend, one backend, one MCP server, local PostgreSQL, optional Redis/Nginx.
- Production requires `APP_ENV=production`, Redis cache, disabled API auto-migrations, non-default secrets, strict CORS, upload limits, log rotation, and PostgreSQL backups.
- Temporary datasource Excel/CSV import files are scoped under the current tenant directory.
- Shared local `file/excel/images` directories are acceptable for single-machine multi-replica deployments only. Multi-machine production must move these to shared storage or object storage.

## Current Gaps

- Object storage is not implemented yet.
- Kubernetes, Helm, cross-region failover, and automated multi-region disaster recovery are not part of the current baseline.
- MCP remains a separate single-instance deployment path unless MCP HA is explicitly designed later.
- Full production observability still needs environment-specific dashboards and alert rules.
