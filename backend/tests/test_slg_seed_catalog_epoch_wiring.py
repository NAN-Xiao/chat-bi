"""Guard direct SLG seed writes against stale catalog and permission versions."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
TOOLS_DIR = ROOT / "tools"
for path in (BACKEND_DIR, TOOLS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _load_tool(name: str):
    path = ROOT / "tools" / f"{name}.py"
    assert path.exists(), f"缺少运维脚本模块: {path.name}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_management_catalog_hash_matches_application_hash() -> None:
    helper = _load_tool("catalog_metadata_sql")
    from apps.datasource.crud.semantic_object_key import physical_schema_hash

    tables = [
        {
            "id": 7,
            "catalog_key": "",
            "schema_key": "public",
            "table_key": "orders",
        }
    ]
    fields = [
        {"table_id": 7, "field_key": "amount", "field_type": "numeric"},
        {"table_id": 7, "field_key": "created_at", "field_type": "timestamp"},
    ]

    expected = physical_schema_hash(
        [SimpleNamespace(**tables[0])],
        [SimpleNamespace(**field) for field in reversed(fields)],
    )

    assert helper.physical_schema_hash_rows(tables, fields) == expected


def test_refresh_physical_schema_hash_marks_complete_catalog() -> None:
    helper = _load_tool("catalog_metadata_sql")
    calls: list[tuple[str, object]] = []
    result_sets = [
        [{"id": 7, "catalog_key": "", "schema_key": "public", "table_key": "orders"}],
        [{"table_id": 7, "field_key": "amount", "field_type": "numeric"}],
    ]

    class FakeCursor:
        rowcount = 0

        def execute(self, statement, parameters):
            calls.append((str(statement), parameters))
            self.rowcount = 1 if "UPDATE public.core_datasource" in str(statement) else 0

        def fetchall(self):
            return result_sets.pop(0)

    cursor = FakeCursor()
    schema_hash = helper.refresh_physical_schema_hash_cursor(cursor, datasource_id=9)

    assert len(schema_hash) == 64
    assert calls[-1][1] == (schema_hash, 9)
    assert "catalog_complete = true" in calls[-1][0]


def test_refresh_physical_schema_hash_rejects_legacy_catalog_key() -> None:
    helper = _load_tool("catalog_metadata_sql")
    result_sets = [
        [
            {
                "id": 7,
                "catalog_key": "",
                "schema_key": "__legacy_schema__:7",
                "table_key": "orders",
            }
        ],
        [],
    ]

    class FakeCursor:
        rowcount = 0

        def execute(self, _statement, _parameters):
            return None

        def fetchall(self):
            return result_sets.pop(0)

    with pytest.raises(RuntimeError, match="物理目录键不完整"):
        helper.refresh_physical_schema_hash_cursor(FakeCursor(), datasource_id=9)


@pytest.mark.parametrize(
    ("module_name", "function_name"),
    [
        ("seed_slg_bi_activity_dashboard", "sync_datasource_field_metadata"),
        ("seed_slg_bi_expedition_dashboard", "sync_expedition_metadata"),
    ],
)
def test_slg_metadata_sync_maintains_full_keys_hash_and_epoch(
    module_name: str,
    function_name: str,
) -> None:
    module = _load_tool(module_name)
    source = inspect.getsource(getattr(module, function_name))

    for column in ("catalog_key", "schema_key", "table_key", "field_key"):
        assert column in source
    assert "refresh_physical_schema_hash_cursor" in source
    assert "bump_semantic_scope_epoch_cursor" in source
    assert source.index("refresh_physical_schema_hash_cursor") < source.index(
        "bump_semantic_scope_epoch_cursor"
    )
    assert "DATASOURCE_ID" not in source


def test_activity_metadata_sync_uses_resolved_datasource_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_tool("seed_slg_bi_activity_dashboard")
    calls: list[tuple[str, object]] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, parameters):
            calls.append((str(statement), parameters))

        def fetchone(self):
            return {"tenant_id": 12}

        def fetchall(self):
            return []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self, **_kwargs):
            return FakeCursor()

    refreshed: list[int] = []
    bumped: list[dict[str, object]] = []
    monkeypatch.setattr(module, "load_physical_columns", lambda _connection: {})
    monkeypatch.setattr(
        module,
        "refresh_physical_schema_hash_cursor",
        lambda _cursor, *, datasource_id: refreshed.append(datasource_id),
    )
    monkeypatch.setattr(
        module,
        "bump_semantic_scope_epoch_cursor",
        lambda _cursor, **kwargs: bumped.append(kwargs),
    )

    module.sync_datasource_field_metadata(FakeConnection(), object(), datasource_id=37)

    assert calls[0][1] == (37,)
    assert calls[1][1] == (37,)
    assert refreshed == [37]
    assert bumped == [{"scope_type": "SCHEMA", "tenant_id": 12, "datasource_id": 37}]
