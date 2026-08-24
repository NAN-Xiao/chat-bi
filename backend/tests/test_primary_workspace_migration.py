"""Validate primary-workspace duplicate repair and uniqueness enforcement."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


def _load_migration() -> ModuleType:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "167_primary_workspace_uniqueness.py"
    )
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_primary_workspace_migration_repairs_duplicates_before_unique_index() -> None:
    migration = _load_migration()
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE sys_tenant (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    status INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE sys_tenant_user (
                    id INTEGER PRIMARY KEY,
                    tenant_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    is_primary BOOLEAN NOT NULL,
                    status INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO sys_tenant (id, name, status) VALUES
                    (1, 'Default', 1),
                    (200, 'Workspace B', 1),
                    (300, 'Workspace A', 1),
                    (400, 'Disabled Workspace', 0)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO sys_tenant_user
                    (id, tenant_id, user_id, is_primary, status)
                VALUES
                    (1, 1, 10, true, 1),
                    (2, 200, 10, true, 1),
                    (3, 300, 10, true, 1),
                    (4, 400, 10, true, 1),
                    (5, 200, 11, true, 1)
                """
            )
        )
        connection.execute(text(migration.REPAIR_DUPLICATE_PRIMARY_SQL))
        connection.execute(text(migration.CREATE_UNIQUE_INDEX_SQL))

        rows = connection.execute(
            text(
                """
                SELECT tenant_id, is_primary
                FROM sys_tenant_user
                WHERE user_id = 10
                ORDER BY tenant_id
                """
            )
        ).all()

    assert rows == [(1, 0), (200, 0), (300, 1), (400, 0)]

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO sys_tenant_user
                    (id, tenant_id, user_id, is_primary, status)
                VALUES
                    (6, 400, 10, true, 0),
                    (7, 300, 12, true, 1)
                """
            )
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO sys_tenant_user
                        (id, tenant_id, user_id, is_primary, status)
                    VALUES (8, 200, 10, true, 1)
                    """
                )
            )


def test_primary_workspace_migration_revision_contract() -> None:
    migration = _load_migration()

    assert migration.revision == "167primaryworkspaceunique"
    assert migration.down_revision == "166removelegacykbstate"
    assert migration.INDEX_NAME == "uq_sys_tenant_user_active_primary"
