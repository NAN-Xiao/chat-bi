# Knowledge Base RAG Batch 03 Catalog and Permission Epoch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish complete physical-object identity, metadata permissions, monotonic permission epochs, consistent permission snapshots, and execution-time permission revalidation.

**Architecture:** Extend `CoreTable/CoreField` as the sole physical catalog, normalize identifiers with datasource dialect rules, and represent authorized objects by SHA-256 canonical keys. Build snapshots on a dedicated read-only `REPEATABLE READ` connection, cache only after computing the version, and recheck that version immediately before SQL execution.

**Tech Stack:** SQLModel/SQLAlchemy, PostgreSQL, sqlglot, FastAPI, Redis scoped cache, pytest.

## Global Constraints

- Do not add a parallel physical catalog.
- A naked table name resolves only when exactly one full catalog/schema/table match exists in the current datasource.
- Multiple or missing matches return explicit Chinese ambiguity/missing errors; never select the first table.
- Schema, event, and event-property permissions extend the existing `ds_rules`/`ds_permission` binding model and keep its deny semantics.
- Epoch increments occur in the same transaction as the authority write.
- Permission snapshots fail closed when consistent authority state cannot be read after one retry.
- Execution-time recheck never executes SQL under a stale permission version.

---

### Task 1: Canonical Object Keys and Full Catalog Synchronization

**Files:**
- Create: `backend/apps/datasource/crud/semantic_object_key.py`
- Modify: `backend/apps/datasource/crud/datasource.py`
- Modify: `backend/apps/datasource/crud/table.py`
- Modify: `backend/apps/datasource/crud/field.py`
- Test: `backend/tests/test_semantic_object_key.py`
- Test: `backend/tests/test_datasource_field_list_items.py`

**Interfaces:**
- Consumes: catalog columns from revision 155 and datasource dialect/configuration.
- Produces: `DeclaredObjectPath`, `SemanticObjectKey`, `canonical_object_key()`, `resolve_table_key()`, and `physical_schema_hash()`.

- [ ] **Step 1: Write normalization and ambiguity tests**

```python
def test_same_table_name_in_two_schemas_has_distinct_keys():
    left = SemanticObjectKey(object_type="TABLE", tenant_id=2, datasource_id=9, schema="public", table="orders")
    right = SemanticObjectKey(object_type="TABLE", tenant_id=2, datasource_id=9, schema="archive", table="orders")
    assert canonical_object_key(left) != canonical_object_key(right)


def test_unqualified_table_is_ambiguous_in_multi_schema(session):
    seed_table(session, ds_id=9, schema="public", table="orders")
    seed_table(session, ds_id=9, schema="archive", table="orders")
    result = resolve_table_key(session, datasource_id=9, declared=DeclaredObjectPath(object_type="TABLE", table="orders"))
    assert result.status == "AMBIGUOUS"
    assert result.key is None
```

- [ ] **Step 2: Run tests and confirm naked-name behavior fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_semantic_object_key.py backend/tests/test_datasource_field_list_items.py -q`

Expected: FAIL because canonical types/resolution are absent and current lookups use naked table names.

- [ ] **Step 3: Implement immutable keys and migrate synchronization**

```python
@dataclass(frozen=True)
class SemanticObjectKey:
    object_type: Literal["SCHEMA", "TABLE", "FIELD", "JSON_PATH", "EVENT", "EVENT_PROPERTY"]
    tenant_id: int
    datasource_id: int
    catalog: str | None = None
    schema: str | None = None
    table: str | None = None
    field: str | None = None
    json_path: str | None = None
    event_name: str | None = None
    event_property_key: str | None = None


def canonical_object_key(value: SemanticObjectKey) -> str:
    payload = dataclasses.asdict(value)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
```

Update schema synchronization to persist raw and normalized catalog/schema/table/field values, delete stale full-key records, compute the sorted physical schema hash after the transaction's final catalog state, and mark incompleteness instead of inventing a schema.

- [ ] **Step 4: Run catalog tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_semantic_object_key.py backend/tests/test_datasource_field_list_items.py backend/tests/test_table_embedding_fallback.py -q`

Expected: PASS; existing embedding behavior sees the same authorized table set but full keys disambiguate schemas.

- [ ] **Step 5: Commit canonical catalog work**

```powershell
git add backend/apps/datasource/crud/semantic_object_key.py backend/apps/datasource/crud/datasource.py backend/apps/datasource/crud/table.py backend/apps/datasource/crud/field.py backend/tests/test_semantic_object_key.py backend/tests/test_datasource_field_list_items.py
git commit -m "feat: 使用完整目录键标识数据源对象"
```

### Task 2: Metadata Permission DTOs and Services

**Files:**
- Create: `backend/apps/datasource/crud/metadata_permission.py`
- Modify: `backend/apps/datasource/api/permission.py`
- Modify: `backend/apps/datasource/crud/permission.py`
- Modify: `backend/apps/datasource/crud/permission_rules.py`
- Modify: `backend/apps/system/schemas/permission.py`
- Test: `backend/tests/test_metadata_permission_service.py`
- Test: `backend/tests/test_event_permission_enforcement.py`

**Interfaces:**
- Consumes: current tenant/datasource binding, `ds_rules`, `ds_permission`, tracking catalog, and canonical object keys.
- Produces: permission types `schema`, `event`, `event_property` and `MetadataPermissionService.resolve_denied_objects()`.

- [ ] **Step 1: Write stable-key and tenant-boundary tests**

```python
@pytest.mark.parametrize("permission_type", ["schema", "event", "event_property"])
def test_metadata_permission_rejects_foreign_workspace_object(permission_type, client, foreign_object):
    response = client.post("/ds_permission/save", json=permission_payload(permission_type, foreign_object))
    assert response.status_code in {403, 404}
    assert "foreign" not in response.text


def test_event_names_are_unique_per_workspace_not_per_table(session):
    seed_event(session, tenant_id=2, table="events_a", event_name="purchase")
    with pytest.raises(MetadataPermissionValidationError):
        validate_event_target(session, tenant_id=2, table="events_b", event_name="purchase")
```

- [ ] **Step 2: Run tests and confirm unsupported permission types**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_metadata_permission_service.py backend/tests/test_event_permission_enforcement.py -q`

Expected: FAIL because the API accepts only row/column/table.

- [ ] **Step 3: Extend permission types without a new binding model**

Set `PERMISSION_TYPES = {"row", "column", "table", "schema", "event", "event_property"}`. Add the exact callable `MetadataPermissionService.resolve_denied_objects(*, session: Session, current_user: CurrentUser, tenant_id: int, datasource_id: int) -> frozenset[str]` and make it return only canonical denied keys loaded from the current authority records.

For every submitted stable key, reload the current tenant, bound datasource, physical catalog or tracking object server-side. Store no client-provided display names as authority. When no explicit event permission exists, inherit table, event-name field, source field, and JSON-path restrictions.

- [ ] **Step 4: Run metadata permission tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_metadata_permission_service.py backend/tests/test_event_permission_enforcement.py tests/test_datasource_permission_roles.py -q`

Expected: PASS with platform/workspace isolation and current deny semantics preserved.

- [ ] **Step 5: Commit metadata permissions**

```powershell
git add backend/apps/datasource/crud/metadata_permission.py backend/apps/datasource/api/permission.py backend/apps/datasource/crud/permission.py backend/apps/datasource/crud/permission_rules.py backend/apps/system/schemas/permission.py backend/tests/test_metadata_permission_service.py backend/tests/test_event_permission_enforcement.py tests/test_datasource_permission_roles.py
git commit -m "feat: 扩展 Schema 与事件元数据权限"
```

### Task 3: Epoch Service and Every Authority Write Path

**Files:**
- Create: `backend/apps/datasource/crud/permission_scope.py`
- Modify: `backend/apps/datasource/crud/permission.py`
- Modify: `backend/apps/datasource/crud/permission_rules.py`
- Modify: `backend/apps/system/crud/tenant.py`
- Modify: `backend/apps/system/api/tenant.py`
- Modify: `backend/apps/system/api/user.py`
- Modify: `backend/apps/system/crud/tracking_config.py`
- Modify: `backend/apps/datasource/crud/binding.py`
- Modify: `backend/apps/datasource/crud/datasource.py`
- Test: `backend/tests/test_permission_scope_service.py`
- Test: `backend/tests/test_tenant_binding_transactions.py`

**Interfaces:**
- Consumes: `semantic_scope_epoch` table.
- Produces: `bump_semantic_scope_epoch()` and `load_semantic_scope_epochs()`.

- [ ] **Step 1: Add parameterized public-write epoch tests**

```python
@pytest.mark.parametrize(
    ("mutation", "scope"),
    [
        (mutate_permission_rule, "PERMISSION"),
        (mutate_system_role, "SYSTEM_ROLE"),
        (mutate_membership, "MEMBERSHIP"),
        (mutate_datasource_access, "DATASOURCE_ACCESS"),
        (mutate_datasource_role, "DATASOURCE_ROLE"),
        (mutate_tracking, "TRACKING"),
        (mutate_binding, "DATASOURCE_BINDING"),
        (mutate_schema_catalog, "SCHEMA"),
    ],
)
def test_public_write_increments_epoch_in_same_transaction(session, mutation, scope):
    before = read_epoch(session, scope)
    mutation(session)
    session.commit()
    assert read_epoch(session, scope) == before + 1
```

- [ ] **Step 2: Run and identify uncovered writes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_permission_scope_service.py backend/tests/test_tenant_binding_transactions.py -q`

Expected: FAIL for every write path not yet calling the epoch service.

- [ ] **Step 3: Implement one transactional epoch service and wire all writes**

```python
def bump_semantic_scope_epoch(
    session: Session,
    *,
    scope_type: SemanticScopeType,
    tenant_id: int,
    datasource_id: int | None = None,
    subject_id: int | None = None,
) -> int:
    statement = pg_insert(SemanticScopeEpoch).values(
        scope_type=scope_type.value,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        subject_id=subject_id,
        epoch=1,
        update_time=func.now(),
    )
    statement = statement.on_conflict_do_update(
        index_elements=(
            SemanticScopeEpoch.scope_type,
            SemanticScopeEpoch.tenant_id,
            func.coalesce(SemanticScopeEpoch.datasource_id, 0),
            func.coalesce(SemanticScopeEpoch.subject_id, 0),
        ),
        set_={"epoch": SemanticScopeEpoch.epoch + 1, "update_time": func.now()},
    ).returning(SemanticScopeEpoch.epoch)
    return int(session.exec(statement).one())
```

Call it before the same transaction commits in all eight authority areas. Batch catalog refreshes to one `SCHEMA` bump per datasource refresh transaction.

- [ ] **Step 4: Audit direct authority writes outside public services**

Run: `rg -n "(update|delete|insert).*?(ds_rules|ds_permission|sys_tenant_user|core_datasource_user|core_datasource_tenant_binding|sys_tenant_tracking|core_table|core_field)" backend tools --glob "*.py"`

Expected: each application or management-script write is either routed through a domain service that bumps the matching epoch or has an explicit same-transaction `bump_semantic_scope_epoch()` call; seed-only test fixtures are documented in the test setup and do not represent public writes.

- [ ] **Step 5: Run all authority-write tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_permission_scope_service.py backend/tests/test_tenant_binding_transactions.py tests/test_user_tenant_roles.py tests/test_project_permission_boundaries.py -q`

Expected: PASS; rollback restores both authority data and epoch.

- [ ] **Step 6: Commit epoch wiring**

```powershell
git add backend/apps/datasource/crud/permission_scope.py backend/apps/datasource/crud/permission.py backend/apps/datasource/crud/permission_rules.py backend/apps/system/crud/tenant.py backend/apps/system/api/tenant.py backend/apps/system/api/user.py backend/apps/system/crud/tracking_config.py backend/apps/datasource/crud/binding.py backend/apps/datasource/crud/datasource.py backend/tests/test_permission_scope_service.py backend/tests/test_tenant_binding_transactions.py tests/test_user_tenant_roles.py tests/test_project_permission_boundaries.py
git commit -m "feat: 统一维护语义权限版本纪元"
```

### Task 4: Repeatable-Read Permission Snapshot and Cache Versioning

**Files:**
- Create: `backend/apps/datasource/crud/permission_scope_repository.py`
- Modify: `backend/apps/datasource/crud/permission_scope.py`
- Test: `backend/tests/test_permission_scope_service.py`
- Test: `backend/tests/test_redis_key_scoping.py`

**Interfaces:**
- Consumes: epoch loader, canonical catalog, existing row/table/column permissions, metadata permissions, current user/workspace/datasource authority.
- Produces: `PermissionScopeRepository.build_snapshot()` and `PermissionScopeService.build_snapshot()`.

- [ ] **Step 1: Write consistency and cache-key tests**

```python
def test_snapshot_uses_one_repeatable_read_authority_view(permission_repository, concurrent_revoker):
    concurrent_revoker.revoke_between_epoch_and_permissions()
    snapshot = permission_repository.build_snapshot(tenant_id=2, user_id=8, datasource_id=9)
    assert snapshot.permission_version in concurrent_revoker.valid_complete_versions


def test_permission_cache_key_contains_version_tenant_user_and_datasource(snapshot):
    key = permission_cache_key(snapshot)
    assert all(str(value) in key for value in (snapshot.tenant_id, snapshot.user_id, snapshot.datasource_id))
    assert snapshot.permission_version in key
```

- [ ] **Step 2: Run and confirm no consistent repository exists**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_permission_scope_service.py backend/tests/test_redis_key_scoping.py -q`

Expected: FAIL because snapshot calculation is not isolated or version-keyed.

- [ ] **Step 3: Implement a dedicated read-only transaction**

```python
class PermissionScopeRepository:
    def build_snapshot(self, *, tenant_id: int, user_id: int, datasource_id: int) -> PermissionScopeSnapshot:
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            transaction = connection.begin()
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            try:
                return self._read_complete_snapshot(connection, tenant_id, user_id, datasource_id)
            finally:
                transaction.rollback()
```

Read epochs, roles/status, membership, datasource access/role, binding, catalog hash, and permissions inside that transaction. Compute `permission_version` before any permission-content cache lookup. Retry the whole snapshot once on a transient consistency failure; then return a safe Chinese failure instead of stale cache.

- [ ] **Step 4: Run snapshot and Redis scope tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_permission_scope_service.py backend/tests/test_redis_key_scoping.py backend/tests/test_redis_client_scope.py -q`

Expected: PASS and no unscoped Redis key is introduced.

- [ ] **Step 5: Commit permission snapshots**

```powershell
git add backend/apps/datasource/crud/permission_scope_repository.py backend/apps/datasource/crud/permission_scope.py backend/tests/test_permission_scope_service.py backend/tests/test_redis_key_scoping.py
git commit -m "feat: 使用一致性快照构建运行时权限范围"
```

### Task 5: Full-Key SQL Validation, Event Enforcement, and Pre-Execution Recheck

**Files:**
- Modify: `backend/apps/datasource/crud/sql_permission.py`
- Modify: `backend/apps/datasource/crud/sql_engine_executor.py`
- Modify: `backend/apps/datasource/crud/row_permission.py`
- Test: `backend/tests/test_event_permission_enforcement.py`
- Test: `backend/tests/test_sql_engine_context.py`
- Test: `backend/tests/test_db_query_execution_controls.py`

**Interfaces:**
- Consumes: `PermissionScopeSnapshot`, canonical key resolver, and existing sqlglot read-only/column/row checks.
- Produces: `validate_sql_object_scope()`, `compile_event_constraints()`, and `revalidate_permission_version()`.

- [ ] **Step 1: Write cross-schema, dynamic JSON path, event, and revocation-race tests**

```python
def test_authorized_public_orders_does_not_authorize_archive_orders(snapshot):
    sql = 'select * from archive.orders'
    with pytest.raises(SqlPermissionError):
        validate_sql_object_scope(sql, snapshot=snapshot, dialect="postgres")


def test_permission_change_before_execute_forces_revalidation(executor, snapshot, revoke_permission):
    revoke_permission()
    result = executor.execute("select amount from public.orders", permission_snapshot=snapshot)
    assert result.error_type == "permission_denied"
    assert result.message == "权限已发生变化，请重新提交查询。"
```

- [ ] **Step 2: Run tests and observe naked-table authorization**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_event_permission_enforcement.py backend/tests/test_sql_engine_context.py backend/tests/test_db_query_execution_controls.py -q`

Expected: FAIL because tables are extracted without full catalog/schema identity and there is no version recheck.

- [ ] **Step 3: Enforce complete object keys and event constraints**

Extract `exp.Table.catalog`, `exp.Table.db`, and `exp.Table.name`; bind columns and static JSON paths to the resolved full table key. Block dynamic JSON paths when path restrictions exist. Compile denied events to existing row-condition AST injection only when semantics are preserved; block unsafe outer-join, aggregation-level, subquery, or dynamic-predicate cases. Re-run read-only, object, field, JSON, event, and row validation after rewrite.

- [ ] **Step 4: Recheck permission version immediately before execution**

Read the short version fingerprint from a fresh consistent query. If unchanged, execute. If changed, rebuild the snapshot and rerun every AST check once; if rebuild or validation fails, return `permission_denied` with the Chinese message and never call the datasource driver.

- [ ] **Step 5: Run SQL permission regressions**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_event_permission_enforcement.py backend/tests/test_sql_engine_context.py backend/tests/test_db_query_execution_controls.py backend/tests/test_data_skill_sql_validation.py tests/test_sql_row_permission_relation.py -q`

Expected: PASS for cross-schema names, `SELECT *`, JSON paths, event filtering, row permissions, and concurrent revocation.

- [ ] **Step 6: Commit execution enforcement**

```powershell
git add backend/apps/datasource/crud/sql_permission.py backend/apps/datasource/crud/sql_engine_executor.py backend/apps/datasource/crud/row_permission.py backend/tests/test_event_permission_enforcement.py backend/tests/test_sql_engine_context.py backend/tests/test_db_query_execution_controls.py
git commit -m "feat: 强制校验完整对象权限与执行前版本"
```
