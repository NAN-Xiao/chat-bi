# Task 1 Payload Validation Review Fix

## Red

Command:

```powershell
$env:PYTHONPATH='backend'; & "D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe" -m pytest backend/tests/test_knowledge_base_payload_validation.py -q
```

Initial result: `3 failed, 12 passed`.

- A datasource-neutral document with `orders` did not match a catalog entry named `public.orders`.
- `SELECT INTO` and `SELECT ... FOR UPDATE` passed the read-only parser.
- A `related_objects` declaration without the catalog portion passed until SQL comparison.

## Green

- Catalog keys now expose their terminal table name for document physical-identifier detection.
- Business declarations are resolved against the current validation catalog before SQL AST comparison. Missing context, incomplete identity, and unknown objects return Chinese validation issues; catalog/schema/table comparisons are exact.
- SQL read-only validation rejects `INTO` and locking clauses in addition to write expressions.

## Final Verification

Command:

```powershell
$env:PYTHONPATH='backend'; & "D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe" -m pytest backend/tests/test_knowledge_base_payload_validation.py backend/tests/test_data_skill_sql_validation.py -q
```

Final output: `25 passed, 235 warnings in 6.80s`.

## Second Review Fix

### Red

Command:

```powershell
$env:PYTHONPATH='backend'; & "D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe" -m pytest backend/tests/test_knowledge_base_payload_validation.py -q
```

Initial result: `3 failed, 15 passed`.

- The root-only read-only check missed `SELECT INTO` in a CTE and `FOR UPDATE` in a UNION branch.
- A datasource-bound document did not validate its `object_references` against the catalog.
- JSON extraction accepted an extra random function and a subquery table reference.

### Green

- Read-only SQL now rejects `Insert`, `Lock`, and all write expressions anywhere in the parsed AST.
- Datasource-bound documents reuse complete object-reference validation; only catalog-resolved declarations satisfy document physical-object references.
- JSON expressions allow one unqualified host column and static JSON operations only. Random functions, subqueries, tables, and other columns are rejected.
- FIELD and JSON_PATH declarations resolve their host fields through the same full Catalog/Schema/Table identity, avoiding cross-catalog fallback.

Final focused output: `29 passed, 235 warnings in 6.76s`.

## Final Important Fix

### Red

Initial payload validation result: `2 failed, 20 passed`.

- FIELD and JSON_PATH declarations were checked only against the catalog, not against the SQL AST objects actually used by an example.
- Datasource-neutral document scanning did not accept case-insensitive field, JSON Path, or event identifiers from the current catalog context.

### Green

- BUSINESS SQL now compares valid FIELD declarations with resolved SQL table/column accesses and JSON_PATH declarations with resolved static JSON accesses. TABLE declarations retain their table-level behavior.
- Datasource-neutral documents perform case-insensitive boundary matching for current catalog table names, fields, configured JSON Paths, and workspace event names. An empty context still contributes no inferred identifier.
- JSON expression functions now use an explicit dialect-aware whitelist of extraction nodes/functions; an unknown `JSON_EVIL` wrapper is rejected.

Final focused output: `32 passed, 235 warnings in 7.15s`.

## Local Alias Scope Fix

### Red

The nested CTE regression failed with `1 failed, 22 passed`: the validator used one global alias table, so an inner `orders o` and outer `users o` could resolve to the same physical table.

### Green

- FIELD and JSON_PATH AST access resolution now finds the nearest `SELECT` for each column/access.
- Each select builds aliases only from its direct `FROM` and `JOIN` physical tables.
- A nested CTE can reuse an alias without leaking its object identity into an outer select.

Final focused output: `33 passed, 235 warnings in 8.13s`.

## Unqualified Table Fix

### Red

The SQLite regression `select amount from orders` failed because local select resolution discarded every table without a catalog or schema.

### Green

Local select resolution now excludes only unqualified names that are visible CTEs. It retains legitimate unqualified physical tables for dialects such as SQLite.

Final focused output: `34 passed, 235 warnings in 6.62s`.
