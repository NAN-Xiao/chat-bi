"""Exercise the knowledge-schema chain against an explicit isolated PostgreSQL."""

from __future__ import annotations

import pytest

from tests.knowledge_migration_support import (
    HEAD_REVISION,
    TEST_DATABASE_ENV,
    IsolatedMigrationDatabase,
    isolated_database_url,
    migration_database_fixture,  # noqa: F401
)


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "postgresql+psycopg://root@10.1.5.28:5432/zhishu_bi_2.0.0",
        "postgresql+psycopg://postgres@127.0.0.1:5432/slg_bi_mock",
        "postgresql+psycopg://postgres@127.0.0.1:55439/postgres",
    ],
)
def test_migration_gate_rejects_non_isolated_database(
    monkeypatch: pytest.MonkeyPatch,
    unsafe_url: str,
) -> None:
    monkeypatch.setenv(TEST_DATABASE_ENV, unsafe_url)

    with pytest.raises(pytest.fail.Exception):
        isolated_database_url()


def test_knowledge_schema_upgrade_downgrade_upgrade(
    migrated_database: IsolatedMigrationDatabase,
) -> None:
    assert migrated_database.current_revision() == HEAD_REVISION
