"""Verify semantic permission epoch storage invariants."""

from __future__ import annotations

import os
import subprocess
import sys
import importlib.util
import inspect
from pathlib import Path

from sqlalchemy import CheckConstraint, text
from sqlmodel import Session, create_engine

from apps.datasource.models.datasource import SemanticScopeEpoch, SemanticScopeType
from tests.permission_scope_fixtures import (
    permission_engine,
    read_epoch,
    schema_engine,
    tracking_engine,
)


def _constraint(table, name: str, constraint_type):
    return next(
        constraint
        for constraint in table.constraints
        if constraint.name == name and isinstance(constraint, constraint_type)
    )


def test_semantic_scope_types_cover_all_authority_domains() -> None:
    assert [scope.value for scope in SemanticScopeType] == [
        "PERMISSION",
        "SYSTEM_ROLE",
        "MEMBERSHIP",
        "DATASOURCE_ACCESS",
        "DATASOURCE_ROLE",
        "TRACKING",
        "DATASOURCE_BINDING",
        "SCHEMA",
    ]


def test_semantic_epoch_has_full_nullable_scope_key() -> None:
    assert SemanticScopeEpoch.__tablename__ == "semantic_scope_epoch"
    indexes = {index.name: index for index in SemanticScopeEpoch.__table__.indexes}
    scope_index = indexes["uq_semantic_scope_epoch_scope"]
    assert scope_index.unique is True
    expression = ", ".join(str(item) for item in scope_index.expressions)
    assert "scope_type" in expression
    assert "tenant_id" in expression
    assert "COALESCE(datasource_id, 0)" in expression
    assert "COALESCE(subject_id, 0)" in expression


def test_semantic_epoch_model_defaults_and_scope_check() -> None:
    row = SemanticScopeEpoch(
        scope_type=SemanticScopeType.SCHEMA,
        tenant_id=2,
    )
    assert row.epoch == 0
    assert row.datasource_id is None
    assert row.subject_id is None

    constraint = _constraint(
        SemanticScopeEpoch.__table__,
        "ck_semantic_scope_epoch_scope_type",
        CheckConstraint,
    )
    expression = str(constraint.sqltext)
    for scope in SemanticScopeType:
        assert scope.value in expression


def test_datasource_entrypoint_registers_semantic_epoch_metadata() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from apps.datasource.models.datasource import CoreDatasource; "
            "from sqlmodel import SQLModel; "
            "print([table.name for table in SQLModel.metadata.sorted_tables])",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    assert result.returncode == 0, result.stderr
    assert "semantic_scope_epoch" in result.stdout


def test_alembic_metadata_entrypoint_registers_datasource_models() -> None:
    env_source = (
        Path(__file__).resolve().parents[1] / "alembic" / "env.py"
    ).read_text(encoding="utf-8")

    assert "import apps.datasource.models.datasource" in env_source


def test_semantic_epoch_migration_uses_named_expression_index() -> None:
    from tests.test_semantic_object_key import _load_migration, _offline_sql

    sql = _offline_sql(_load_migration(), "upgrade")
    assert "CREATE TABLE semantic_scope_epoch" in sql
    assert "CREATE UNIQUE INDEX uq_semantic_scope_epoch_scope" in sql
    assert "scope_type, tenant_id, COALESCE(datasource_id, 0), COALESCE(subject_id, 0)" in sql


def _epoch_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'semantic_scope_epoch.db'}")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE semantic_scope_epoch (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_type VARCHAR(32) NOT NULL,
                tenant_id BIGINT NOT NULL,
                datasource_id BIGINT,
                subject_id BIGINT,
                epoch BIGINT NOT NULL DEFAULT 0,
                update_time DATETIME
            )
        """))
        connection.execute(text("""
            CREATE UNIQUE INDEX uq_semantic_scope_epoch_scope
            ON semantic_scope_epoch (
                scope_type,
                tenant_id,
                COALESCE(datasource_id, 0),
                COALESCE(subject_id, 0)
            )
        """))
    return engine


def test_bump_and_load_semantic_scope_epoch(tmp_path) -> None:
    from apps.datasource.crud.permission_scope import (
        SemanticScopeCoordinate,
        bump_semantic_scope_epoch,
        load_semantic_scope_epochs,
    )

    engine = _epoch_engine(tmp_path)
    coordinate = SemanticScopeCoordinate(
        scope_type=SemanticScopeType.PERMISSION,
        tenant_id=2,
        datasource_id=9,
        subject_id=7,
    )
    with Session(engine) as session:
        assert bump_semantic_scope_epoch(session, coordinate=coordinate) == 1
        assert bump_semantic_scope_epoch(session, coordinate=coordinate) == 2
        assert load_semantic_scope_epochs(session, coordinates=[coordinate]) == {
            coordinate: 2,
        }
        session.commit()

    engine.dispose()


def test_postgresql_epoch_upsert_uses_literal_expression_index() -> None:
    from sqlalchemy.dialects import postgresql

    from apps.datasource.crud.permission_scope import bump_semantic_scope_epoch

    class ScalarResult:
        @staticmethod
        def scalar_one():
            return 1

    class RecordingSession:
        statement = None

        @staticmethod
        def get_bind():
            return type("Bind", (), {"dialect": postgresql.dialect()})()

        def execute(self, statement):
            self.statement = statement
            return ScalarResult()

    session = RecordingSession()
    assert bump_semantic_scope_epoch(
        session,
        scope_type=SemanticScopeType.SCHEMA,
        tenant_id=2,
        datasource_id=9,
    ) == 1

    compiled = session.statement.compile(dialect=postgresql.dialect())
    assert not any(name.startswith("coalesce_") for name in compiled.params)
    assert "coalesce(datasource_id, 0)" in str(compiled).lower()
    assert "coalesce(subject_id, 0)" in str(compiled).lower()


def test_load_semantic_scope_epochs_defaults_missing_scope_to_zero(tmp_path) -> None:
    from apps.datasource.crud.permission_scope import (
        SemanticScopeCoordinate,
        load_semantic_scope_epochs,
    )

    engine = _epoch_engine(tmp_path)
    coordinate = SemanticScopeCoordinate(
        scope_type=SemanticScopeType.TRACKING,
        tenant_id=2,
        datasource_id=9,
    )
    with Session(engine) as session:
        assert load_semantic_scope_epochs(session, coordinates=[coordinate]) == {
            coordinate: 0,
        }

    engine.dispose()


def test_semantic_scope_epoch_rolls_back_with_authority_write(tmp_path) -> None:
    from apps.datasource.crud.permission_scope import (
        SemanticScopeCoordinate,
        bump_semantic_scope_epoch,
        load_semantic_scope_epochs,
    )

    engine = _epoch_engine(tmp_path)
    coordinate = SemanticScopeCoordinate(
        scope_type=SemanticScopeType.MEMBERSHIP,
        tenant_id=2,
        subject_id=7,
    )
    with Session(engine) as session:
        bump_semantic_scope_epoch(session, coordinate=coordinate)
        session.rollback()
        assert load_semantic_scope_epochs(session, coordinates=[coordinate]) == {
            coordinate: 0,
        }

    engine.dispose()


def test_permission_rule_write_increments_epoch_in_same_transaction(tmp_path) -> None:
    from apps.datasource.crud.permission_rules import save_rule_dto

    engine = permission_engine(tmp_path)
    with Session(engine) as session:
        save_rule_dto(
            session,
            {
                "enable": True,
                "name": "orders deny",
                "tenant_id": 2,
                "scope": "TENANT",
                "users": [7],
                "permissions": [
                    {
                        "name": "orders",
                        "enable": True,
                        "type": "table",
                        "ds_id": 9,
                        "table_id": 90,
                        "permissions": [],
                    }
                ],
            },
        )

        assert read_epoch(
            session,
            SemanticScopeType.PERMISSION,
            tenant_id=2,
            datasource_id=9,
        ) == 1

    engine.dispose()


def test_tracking_write_increments_epoch_before_commit(tmp_path) -> None:
    from apps.system.crud.tracking_config import save_tracking_config
    from apps.system.schemas.tenant_schema import TenantTrackingConfigEditor

    engine = tracking_engine(tmp_path)
    with Session(engine) as session:
        save_tracking_config(
            session,
            2,
            TenantTrackingConfigEditor(enabled=True),
            datasource_id=9,
            current_user_id=7,
        )

        assert read_epoch(
            session,
            SemanticScopeType.TRACKING,
            tenant_id=2,
            datasource_id=9,
        ) == 1

    engine.dispose()


def test_schema_refresh_increments_epoch_once_per_transaction(tmp_path) -> None:
    from apps.datasource.crud.datasource import sync_fields
    from apps.datasource.models.datasource import ColumnSchema, CoreDatasource, CoreTable

    engine = schema_engine(tmp_path)
    with Session(engine) as session:
        datasource = session.get(CoreDatasource, 9)
        table = session.get(CoreTable, 90)
        assert datasource is not None
        assert table is not None

        sync_fields(
            session,
            datasource,
            table,
            [ColumnSchema("amount", "numeric", "order amount")],
        )

        assert read_epoch(
            session,
            SemanticScopeType.SCHEMA,
            tenant_id=2,
            datasource_id=9,
        ) == 1

    engine.dispose()


def test_schema_metadata_update_commits_once(tmp_path, monkeypatch) -> None:
    from apps.datasource.crud import datasource as datasource_crud
    from apps.datasource.models.datasource import CoreTable

    engine = schema_engine(tmp_path)
    with Session(engine) as session:
        table = session.get(CoreTable, 90)
        assert table is not None
        table.custom_comment = "updated comment"
        commit_calls = 0
        original_commit = session.commit

        def counting_commit():
            nonlocal commit_calls
            commit_calls += 1
            original_commit()

        monkeypatch.setattr(session, "commit", counting_commit)
        monkeypatch.setattr(datasource_crud, "run_save_table_embeddings", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(datasource_crud, "run_save_ds_embeddings", lambda *_args, **_kwargs: None)

        datasource_crud.updateTable(session, table, tenant_id=2)

        assert commit_calls == 1
        assert read_epoch(
            session,
            SemanticScopeType.SCHEMA,
            tenant_id=2,
            datasource_id=9,
        ) == 1

    engine.dispose()


def test_orphan_field_metadata_update_still_commits_authority_transaction(
    tmp_path,
    monkeypatch,
) -> None:
    from apps.datasource.crud import datasource as datasource_crud
    from apps.datasource.models.datasource import CoreField, CoreTable

    engine = schema_engine(tmp_path)
    with Session(engine) as session:
        field = session.get(CoreField, 901)
        assert field is not None
        session.query(CoreTable).filter(CoreTable.id == 90).delete()
        session.commit()
        field.custom_comment = "orphan field comment"
        commit_calls = 0
        original_commit = session.commit

        def counting_commit():
            nonlocal commit_calls
            commit_calls += 1
            original_commit()

        monkeypatch.setattr(session, "commit", counting_commit)
        monkeypatch.setattr(datasource_crud, "run_save_table_embeddings", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(datasource_crud, "run_save_ds_embeddings", lambda *_args, **_kwargs: None)

        datasource_crud.updateField(session, field, tenant_id=2)

        assert commit_calls == 1
        assert read_epoch(
            session,
            SemanticScopeType.SCHEMA,
            tenant_id=2,
            datasource_id=9,
        ) == 1

    engine.dispose()


def test_datasource_delete_uses_one_authority_transaction() -> None:
    from apps.datasource.crud.datasource import delete_ds

    source = inspect.getsource(delete_ds)

    assert source.count("session.commit()") == 1
    assert "bind_datasource_to_tenant" in source
    assert "delete_field_by_ds_id(session, id, commit=False)" in source
    assert "delete_table_by_ds_id(session, id, commit=False)" in source


def test_management_script_epoch_upsert_uses_callers_cursor() -> None:
    helper_path = Path(__file__).resolve().parents[2] / "tools" / "semantic_scope_epoch_sql.py"
    spec = importlib.util.spec_from_file_location("semantic_scope_epoch_sql", helper_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class RecordingCursor:
        calls = []

        def execute(self, statement, parameters):
            self.calls.append((statement, parameters))

    cursor = RecordingCursor()
    module.bump_semantic_scope_epoch_cursor(
        cursor,
        scope_type="TRACKING",
        tenant_id=2,
        datasource_id=9,
    )

    assert len(cursor.calls) == 1
    statement, parameters = cursor.calls[0]
    assert "INSERT INTO semantic_scope_epoch" in statement
    assert "ON CONFLICT" in statement
    assert "epoch = semantic_scope_epoch.epoch + 1" in statement
    assert parameters == ("TRACKING", 2, 9, None)


def test_management_script_epoch_upsert_supports_sqlalchemy_connection() -> None:
    helper_path = Path(__file__).resolve().parents[2] / "tools" / "semantic_scope_epoch_sql.py"
    spec = importlib.util.spec_from_file_location("semantic_scope_epoch_sql_connection", helper_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class RecordingConnection:
        calls = []

        def execute(self, statement, parameters):
            self.calls.append((str(statement), parameters))

    connection = RecordingConnection()
    module.bump_semantic_scope_epoch_connection(
        connection,
        scope_type="PERMISSION",
        tenant_id=2,
        datasource_id=9,
    )

    statement, parameters = connection.calls[0]
    assert "INSERT INTO semantic_scope_epoch" in statement
    assert parameters == {
        "scope_type": "PERMISSION",
        "tenant_id": 2,
        "datasource_id": 9,
        "subject_id": None,
    }
