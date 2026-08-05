"""Safety helpers for destructive knowledge-schema migration tests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

from alembic import command

BASE_REVISION = "152platformsqlaliasquote"
HEAD_REVISION = "155semanticpermepoch"
TEST_DATABASE_ENV = "KNOWLEDGE_MIGRATION_TEST_DATABASE_URL"
TEST_DATABASE_PREFIX = "chat_bi_kb_migration"


@dataclass(frozen=True)
class IsolatedMigrationDatabase:
    engine: Engine
    alembic_config: Config

    def current_revision(self) -> str | None:
        with self.engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()

    def upgrade(self, revision: str) -> None:
        command.upgrade(self.alembic_config, revision)

    def downgrade(self, revision: str) -> None:
        command.downgrade(self.alembic_config, revision)


def isolated_database_url() -> str:
    raw_url = os.getenv(TEST_DATABASE_ENV)
    if not raw_url:
        pytest.skip(f"需要通过 {TEST_DATABASE_ENV} 显式指定本机隔离临时库")

    url = make_url(raw_url)
    if url.host not in {"127.0.0.1", "localhost"}:
        pytest.fail("知识库迁移测试只允许使用本机隔离 PostgreSQL")
    if url.port in {None, 5432}:
        pytest.fail("知识库迁移测试禁止使用默认 PostgreSQL 端口")
    if not (url.database or "").startswith(TEST_DATABASE_PREFIX):
        pytest.fail(f"知识库迁移测试数据库名必须以 {TEST_DATABASE_PREFIX} 开头")
    return raw_url


def build_migration_database() -> IsolatedMigrationDatabase:
    from common.core.config import settings

    raw_url = isolated_database_url()
    settings.SHUZHI_DB_URL = raw_url

    config = Config()
    config.set_main_option(
        "script_location",
        str((Path(__file__).resolve().parents[1] / "alembic").resolve()),
    )
    return IsolatedMigrationDatabase(
        engine=create_engine(raw_url, pool_pre_ping=True),
        alembic_config=config,
    )


@pytest.fixture(name="migrated_database", scope="module")
def migration_database_fixture() -> IsolatedMigrationDatabase:
    from common.core.config import settings

    previous_database_url = settings.SHUZHI_DB_URL
    database = build_migration_database()
    try:
        current = database.current_revision()
        if current is None:
            database.upgrade(BASE_REVISION)
        elif current != BASE_REVISION:
            database.downgrade(BASE_REVISION)

        assert database.current_revision() == BASE_REVISION
        database.upgrade(HEAD_REVISION)
        assert database.current_revision() == HEAD_REVISION
        database.downgrade(BASE_REVISION)
        assert database.current_revision() == BASE_REVISION
        database.upgrade(HEAD_REVISION)
        assert database.current_revision() == HEAD_REVISION

        yield database
    finally:
        database.engine.dispose()
        settings.SHUZHI_DB_URL = previous_database_url
