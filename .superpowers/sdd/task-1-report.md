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
