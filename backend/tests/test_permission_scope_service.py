"""Verify semantic permission epoch storage invariants."""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, text
from sqlmodel import Session, create_engine

from apps.datasource.models.datasource import SemanticScopeEpoch, SemanticScopeType
from tests.metadata_permission_fixtures import insert_rule, metadata_permission_session
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
    from apps.datasource.models.datasource import (
        ColumnSchema,
        CoreDatasource,
        CoreTable,
    )

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


def test_permission_scope_repository_uses_read_only_repeatable_read() -> None:
    from apps.datasource.crud.permission_scope import PermissionScopeSnapshot
    from apps.datasource.crud.permission_scope_repository import (
        PermissionScopeRepository,
    )

    expected = PermissionScopeSnapshot(
        tenant_id=2,
        user_id=7,
        datasource_id=9,
        permission_version="v1",
        schema_hash="a" * 64,
        allowed_object_keys=frozenset(),
        denied_object_keys=frozenset(),
        row_constraints_hash="r1",
    )
    calls: list[object] = []

    class Transaction:
        def rollback(self):
            calls.append("rollback")

    class Connection:
        def __enter__(self):
            calls.append("enter")
            return self

        def __exit__(self, *_args):
            calls.append("exit")

        def execution_options(self, **options):
            calls.append(("execution_options", options))
            return self

        def begin(self):
            calls.append("begin")
            return Transaction()

        def exec_driver_sql(self, statement):
            calls.append(("sql", statement))

    class Engine:
        dialect = type("Dialect", (), {"name": "postgresql"})()

        @staticmethod
        def connect():
            calls.append("connect")
            return Connection()

    class Repository(PermissionScopeRepository):
        def _read_snapshot(self, connection, *, tenant_id, user_id, datasource_id):
            calls.append(("read", tenant_id, user_id, datasource_id, connection))
            return expected

    assert Repository(Engine()).build_snapshot(
        tenant_id=2,
        user_id=7,
        datasource_id=9,
    ) == expected
    assert calls.index(("execution_options", {"isolation_level": "REPEATABLE READ"})) < calls.index("begin")
    assert calls.index("begin") < calls.index(("sql", "SET TRANSACTION READ ONLY"))
    assert calls.index(("sql", "SET TRANSACTION READ ONLY")) < next(
        index for index, call in enumerate(calls) if isinstance(call, tuple) and call[0] == "read"
    )
    assert calls[-2:] == ["rollback", "exit"]


def test_permission_scope_repository_retries_once_then_returns_chinese_error() -> None:
    from apps.datasource.crud.permission_scope import PermissionScopeUnavailableError
    from apps.datasource.crud.permission_scope_repository import (
        PermissionScopeReadError,
        PermissionScopeRepository,
    )

    class FailingRepository(PermissionScopeRepository):
        attempts = 0

        def _build_snapshot_once(self, *, tenant_id, user_id, datasource_id):
            self.attempts += 1
            raise PermissionScopeReadError("transient")

    repository = FailingRepository(object())
    with pytest.raises(PermissionScopeUnavailableError, match="无法读取一致的权限状态，请稍后重试"):
        repository.build_snapshot(tenant_id=2, user_id=7, datasource_id=9)
    assert repository.attempts == 2


def test_permission_scope_snapshot_version_changes_with_authority_epoch(tmp_path) -> None:
    from apps.datasource.crud.permission_scope import bump_semantic_scope_epoch
    from apps.datasource.crud.permission_scope_repository import (
        PermissionScopeRepository,
    )

    with metadata_permission_session(tmp_path / "permission-snapshot.db") as session:
        repository = PermissionScopeRepository(session.get_bind())
        before = repository.build_snapshot(tenant_id=2, user_id=7, datasource_id=9)

        bump_semantic_scope_epoch(
            session,
            scope_type=SemanticScopeType.DATASOURCE_ROLE,
            tenant_id=2,
            datasource_id=9,
            subject_id=7,
        )
        session.commit()

        after = repository.build_snapshot(tenant_id=2, user_id=7, datasource_id=9)

    assert before.permission_version != after.permission_version
    assert before.schema_hash == "a" * 64
    assert before.allowed_object_keys
    assert before.denied_object_keys == frozenset()
    assert len(before.row_constraints_hash) == 64


def test_permission_scope_service_rejects_mismatched_request_context(tmp_path) -> None:
    from apps.datasource.crud.permission_scope import (
        PermissionScopeService,
        PermissionScopeUnavailableError,
    )
    from tests.metadata_permission_fixtures import workspace_user

    with metadata_permission_session(tmp_path / "permission-service.db") as session:
        with pytest.raises(PermissionScopeUnavailableError, match="权限上下文不一致"):
            PermissionScopeService.build_snapshot(
                session=session,
                current_user=workspace_user(user_id=7, tenant_id=3),
                tenant_id=2,
                datasource_id=9,
            )


def test_permission_scope_snapshot_fails_closed_for_invalid_tracking_authority(tmp_path) -> None:
    from apps.datasource.crud.permission_scope import PermissionScopeUnavailableError
    from apps.datasource.crud.permission_scope_repository import (
        PermissionScopeRepository,
    )

    invalid_mapping = json.dumps(
        [
            {
                "event_name": "purchase",
                "properties": [
                    {
                        "property_name": "secret",
                        "source_field": "missing_payload",
                        "json_path": "$.secret",
                    }
                ],
            }
        ]
    )
    with metadata_permission_session(tmp_path / "permission-invalid-tracking.db") as session:
        session.execute(
            text(
                "UPDATE sys_tenant_tracking_config "
                "SET event_name_mappings = :mapping WHERE tenant_id = 2 AND datasource_id = 9"
            ),
            {"mapping": invalid_mapping},
        )
        session.commit()

        with pytest.raises(PermissionScopeUnavailableError, match="无法读取一致的权限状态，请稍后重试"):
            PermissionScopeRepository(session.get_bind()).build_snapshot(
                tenant_id=2,
                user_id=7,
                datasource_id=9,
            )


def test_row_constraint_hash_is_independent_of_query_order() -> None:
    from apps.datasource.crud.permission_scope_objects import row_constraints_hash

    constraints = [
        {
            "table": "orders",
            "table_id": 91,
            "permission_id": 12,
            "deny_sql": "region = 'blocked'",
            "enforcement_sql": "region <> 'blocked'",
        },
        {
            "table": "events",
            "table_id": 90,
            "permission_id": 11,
            "deny_sql": "country = 'blocked'",
            "enforcement_sql": "country <> 'blocked'",
        },
    ]

    assert row_constraints_hash(constraints) == row_constraints_hash(
        list(reversed(constraints))
    )


def test_permission_scope_ignores_enabled_fields_under_disabled_table(tmp_path) -> None:
    from apps.datasource.crud.permission_scope_repository import (
        PermissionScopeRepository,
    )

    with metadata_permission_session(tmp_path / "permission-disabled-table.db") as session:
        session.execute(text("UPDATE core_table SET checked = 0 WHERE id = 91"))
        session.execute(
            text(
                "INSERT INTO core_field "
                "(id, ds_id, table_id, checked, field_name, field_type, field_comment, "
                "custom_comment, field_index, field_key) VALUES "
                "(903, 9, 91, 1, 'archived_value', 'text', '', '', 1, 'archived_value')"
            )
        )
        session.commit()

        snapshot = PermissionScopeRepository(session.get_bind()).build_snapshot(
            tenant_id=2,
            user_id=7,
            datasource_id=9,
        )

    assert snapshot.allowed_object_keys


@pytest.mark.parametrize(
    ("permission_type", "table_id", "targets", "descendant_type", "descendant_values"),
    [
        (
            "schema",
            None,
            [{"catalog_key": "", "schema_key": "public", "enable": False}],
            "TABLE",
            {"catalog": "", "schema": "public", "table": "events"},
        ),
        (
            "table",
            90,
            [],
            "FIELD",
            {
                "catalog": "",
                "schema": "public",
                "table": "events",
                "field": "payload",
            },
        ),
        (
            "column",
            90,
            [{"field_id": 902, "field_name": "payload", "enable": False}],
            "JSON_PATH",
            {
                "catalog": "",
                "schema": "public",
                "table": "events",
                "field": "payload",
                "json_path": "$.amount",
            },
        ),
    ],
)
def test_permission_scope_parent_denials_remove_descendant_objects(
    tmp_path,
    permission_type,
    table_id,
    targets,
    descendant_type,
    descendant_values,
) -> None:
    from apps.datasource.crud.permission_scope_repository import (
        PermissionScopeRepository,
    )
    from apps.datasource.crud.semantic_object_key import (
        SemanticObjectKey,
        canonical_object_key,
    )

    with metadata_permission_session(tmp_path / f"permission-{permission_type}-inheritance.db") as session:
        insert_rule(
            session,
            permission_id=20,
            permission_type=permission_type,
            table_id=table_id,
            targets=targets,
        )

        snapshot = PermissionScopeRepository(session.get_bind()).build_snapshot(
            tenant_id=2,
            user_id=7,
            datasource_id=9,
        )

    descendant_key = canonical_object_key(
        SemanticObjectKey(
            object_type=descendant_type,
            tenant_id=2,
            datasource_id=9,
            **descendant_values,
        )
    )
    assert descendant_key in snapshot.denied_object_keys
    assert descendant_key not in snapshot.allowed_object_keys


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ds_rules SET permission_list = '{broken' WHERE id = 1021",
        "UPDATE ds_permission SET permissions = '{broken' WHERE id = 21",
    ],
)
def test_permission_scope_fails_closed_for_malformed_permission_json(tmp_path, statement) -> None:
    from apps.datasource.crud.permission_scope import PermissionScopeUnavailableError
    from apps.datasource.crud.permission_scope_repository import (
        PermissionScopeRepository,
    )

    with metadata_permission_session(tmp_path / "permission-malformed-json.db") as session:
        insert_rule(
            session,
            permission_id=21,
            permission_type="schema",
            targets=[{"catalog_key": "", "schema_key": "public", "enable": False}],
        )
        session.execute(text(statement))
        session.commit()

        with pytest.raises(PermissionScopeUnavailableError, match="无法读取一致的权限状态，请稍后重试"):
            PermissionScopeRepository(session.get_bind()).build_snapshot(
                tenant_id=2,
                user_id=7,
                datasource_id=9,
            )


def test_permission_scope_does_not_fallback_when_binding_authority_read_fails(
    tmp_path,
    monkeypatch,
) -> None:
    from apps.datasource.crud import binding
    from apps.datasource.crud.permission_scope import PermissionScopeUnavailableError
    from apps.datasource.crud.permission_scope_repository import (
        PermissionScopeRepository,
    )

    with metadata_permission_session(tmp_path / "permission-binding-read.db") as session:
        session.execute(text("UPDATE core_datasource SET tenant_id = 2 WHERE id = 9"))
        session.commit()

        def fail_inspection(_connection):
            raise RuntimeError("binding authority unavailable")

        monkeypatch.setattr(binding, "inspect", fail_inspection)

        with pytest.raises(PermissionScopeUnavailableError, match="无法读取一致的权限状态，请稍后重试"):
            PermissionScopeRepository(session.get_bind()).build_snapshot(
                tenant_id=2,
                user_id=7,
                datasource_id=9,
            )


def test_postgresql_snapshot_keeps_epoch_and_permission_content_consistent() -> None:
    """A revocation committed mid-read cannot create a mixed authority view."""
    pytest.importorskip("psycopg")
    from sqlalchemy import create_engine

    from apps.datasource.crud.permission_scope import PermissionScopeSnapshot
    from apps.datasource.crud.permission_scope_repository import (
        PermissionScopeRepository,
    )
    from tests.knowledge_migration_support import isolated_database_url

    database_url = isolated_database_url()
    schema = f"permission_snapshot_{uuid.uuid4().hex[:12]}"
    admin_engine = create_engine(database_url)
    engine = create_engine(database_url, connect_args={"options": f"-csearch_path={schema}"})
    revoker_engine = create_engine(
        database_url,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    ready = threading.Event()
    committed = threading.Event()
    table_name = f'"{schema}".permission_probe'

    with admin_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"CREATE TABLE {table_name} (epoch INTEGER NOT NULL, denied BOOLEAN NOT NULL)"
            )
            connection.exec_driver_sql(f"INSERT INTO {table_name} VALUES (1, FALSE)")

        class ProbeRepository(PermissionScopeRepository):
            def _read_snapshot(self, connection, *, tenant_id, user_id, datasource_id):
                first = connection.exec_driver_sql(
                    f"SELECT epoch, denied FROM {table_name}"
                ).one()
                ready.set()
                assert committed.wait(10)
                second = connection.exec_driver_sql(
                    f"SELECT epoch, denied FROM {table_name}"
                ).one()
                return PermissionScopeSnapshot(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    datasource_id=datasource_id,
                    permission_version=str(second.epoch),
                    schema_hash="a" * 64,
                    allowed_object_keys=frozenset() if second.denied else frozenset({"orders"}),
                    denied_object_keys=frozenset({"orders"}) if second.denied else frozenset(),
                    row_constraints_hash=str(first.epoch),
                )

        def revoke() -> None:
            assert ready.wait(10)
            with revoker_engine.begin() as connection:
                connection.exec_driver_sql(
                    f"UPDATE {table_name} SET epoch = 2, denied = TRUE"
                )
            committed.set()

        revoker = threading.Thread(target=revoke)
        revoker.start()
        snapshot = ProbeRepository(engine).build_snapshot(
            tenant_id=2,
            user_id=7,
            datasource_id=9,
        )
        revoker.join(timeout=10)

        assert not revoker.is_alive()
        assert snapshot.permission_version == "1"
        assert snapshot.allowed_object_keys == frozenset({"orders"})
        assert snapshot.denied_object_keys == frozenset()
    finally:
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin_engine.dispose()
        engine.dispose()
        revoker_engine.dispose()
