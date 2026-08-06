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
