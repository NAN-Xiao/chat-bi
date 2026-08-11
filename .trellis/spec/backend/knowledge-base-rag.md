# Knowledge Base RAG Contracts

## Scenario: Published Version References and Chunk Retrieval

### 1. Scope / Trigger
- Applies to version publication, semantic object resolution, RAG retrieval, report interpretation, and analysis assistant flows.

### 2. Signatures
- `resolve_references_for_context(...)` accepts projected references or persisted reference rows.
- `KnowledgeRetrievalService._load_reference_resolution(...)` resolves a chunk reference directly, then falls back to its matching version reference.
- `knowledge_base_migrate.py status|verify --compatible-builds-confirmed` reports cutover readiness without changing state.

### 3. Contracts
- Publication retains both version-level and chunk-level references; applicability checks both levels.
- A chunk reference without its own resolution inherits the resolution matching `version_id + declared_key + source_kind`.
- Retrieval still enforces workspace, datasource, visibility, schema epoch, and allowed object keys after inheritance.
- Retrieval audit snapshots contain `knowledge_base_id`, `version_id`, `chunk_id`, `score`, and `visibility_scope`.
- Assistant surfaces use `report_interpretation` or `analysis_assistant`; user-visible failures remain safe Chinese messages.

### 4. Validation & Error Matrix
- Workspace or datasource mismatch -> filter the candidate; never fall back across scopes.
- No chunk or matching version resolution -> reject the reference and persist applicability state.
- `storage_probe_ready=false` or pending legacy backfill -> `verify` reports not ready and exits with code 2.
- Concurrent publication of one knowledge base -> return HTTP 409 with a Chinese message.

### 5. Good/Base/Bad Cases
- Good: only the version resolution exists; an authorized chunk inherits it and can be retrieved.
- Base: chunk and version resolutions both exist; validate with the chunk resolution.
- Bad: only an unauthorized workspace resolution exists; return no hit and retain the audit warning.

### 6. Tests Required
- Unit tests cover persisted-reference conversion, version-resolution inheritance, and permission filtering.
- Real calls prove non-empty audit snapshots for `report_interpretation` and `analysis_assistant`.
- Page checks assert `scrollWidth <= clientWidth + 2` at supported desktop viewports.
- Cutover checks preserve raw `status` and `verify` output.

### 7. Wrong vs Correct
#### Wrong
Read only chunk-level resolution and reject a chunk immediately when that row does not exist, producing zero retrieval hits after a valid publication.

#### Correct
Inherit the matching version-level resolution when the chunk row is absent, then continue enforcing workspace, datasource, schema, and object permissions.

### Common Mistake: Deduplicating Persisted Resolution Rows

- `declared_key + source_kind` is a logical projection key, not a database row identity.
- A published version can have one version-level reference and multiple chunk-level references with the same key; every reference needs its own `semantic_object_resolution` row.
- Persist the resolved result to all matching reference IDs, while evaluating the resolver once per logical key to avoid redundant catalog queries.
- Regression coverage must assert that duplicate version/chunk references all receive the same canonical key.

### Common Mistake: Sorting Citation Dictionaries Directly

- A retrieval can legitimately return multiple citations from one published version. Python dictionaries are not orderable, so `sorted(dict_generator)` raises `TypeError` as soon as more than one citation is present.
- Build the redacted citation identity snapshot first, then sort with an explicit tuple key such as `knowledge_base_id + version_id + chunk_id` before hashing.
- The version hash must be stable when citation order changes, and the regression test must contain at least two citations so a single-hit test cannot hide the failure.
