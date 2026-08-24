"""Verify the legacy knowledge-base state removal migration contract."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


class _OperationRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def __getattr__(self, name: str):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return record


def _load_migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "166_remove_legacy_knowledge_base_status.py"
    )
    spec = spec_from_file_location("remove_legacy_knowledge_base_status", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_drops_index_before_legacy_columns(monkeypatch) -> None:
    migration = _load_migration()
    recorder = _OperationRecorder()
    monkeypatch.setattr(migration, "op", recorder)

    migration.upgrade()

    assert migration.revision == "166removelegacykbstate"
    assert migration.down_revision == "165mergerelease1into2"
    assert [(name, args[:2]) for name, args, _ in recorder.calls] == [
        ("drop_index", ("idx_knowledge_base_status",)),
        ("drop_column", ("knowledge_base", "error_message")),
        ("drop_column", ("knowledge_base", "task_id")),
        ("drop_column", ("knowledge_base", "status")),
    ]


def test_downgrade_restores_empty_compatibility_columns_and_index(monkeypatch) -> None:
    migration = _load_migration()
    recorder = _OperationRecorder()
    monkeypatch.setattr(migration, "op", recorder)

    migration.downgrade()

    add_columns = [args[1] for name, args, _ in recorder.calls if name == "add_column"]
    assert [column.name for column in add_columns] == ["status", "task_id", "error_message"]
    assert add_columns[0].server_default is None
    assert add_columns[0].nullable is True
    assert add_columns[1].nullable is True
    assert add_columns[2].nullable is True
    assert recorder.calls[-1][0] == "create_index"
    assert recorder.calls[-1][1][:2] == (
        "idx_knowledge_base_status",
        "knowledge_base",
    )
