"""Verify the workspace ROI project ID migration contract."""

from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_FILENAME = "157_workspace_roi_project_id.py"


def _load_migration() -> ModuleType:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / MIGRATION_FILENAME
    )
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _offline_sql(module: ModuleType, operation: str) -> str:
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    module.op = Operations(context)
    getattr(module, operation)()
    return output.getvalue()


def test_workspace_roi_project_id_migration_is_linear_and_non_destructive() -> None:
    module = _load_migration()

    assert module.revision == "157workspaceprojectid"
    assert module.down_revision == "156knowledgedocblock"
    upgrade_sql = _offline_sql(module, "upgrade")
    assert "ALTER TABLE sys_tenant ADD COLUMN roi_project_id VARCHAR(128)" in upgrade_sql
    assert "UPDATE sys_tenant" not in upgrade_sql


def test_workspace_roi_project_id_migration_downgrade_drops_only_the_column() -> None:
    downgrade_sql = _offline_sql(_load_migration(), "downgrade")

    assert "ALTER TABLE sys_tenant DROP COLUMN roi_project_id" in downgrade_sql
    assert "DROP TABLE" not in downgrade_sql
