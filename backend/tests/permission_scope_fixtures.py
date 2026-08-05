"""SQLite fixtures for permission epoch write-path tests."""

from __future__ import annotations

from sqlalchemy import text
from sqlmodel import Session, create_engine

from apps.datasource.crud.permission_scope import (
    SemanticScopeCoordinate,
    load_semantic_scope_epochs,
)
from apps.datasource.models.semantic_scope import SemanticScopeType

EPOCH_STATEMENTS = (
    """
    CREATE TABLE semantic_scope_epoch (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope_type VARCHAR(32) NOT NULL,
        tenant_id BIGINT NOT NULL,
        datasource_id BIGINT,
        subject_id BIGINT,
        epoch BIGINT NOT NULL DEFAULT 0,
        update_time DATETIME
    )
    """,
    """
    CREATE UNIQUE INDEX uq_semantic_scope_epoch_scope
    ON semantic_scope_epoch (
        scope_type,
        tenant_id,
        COALESCE(datasource_id, 0),
        COALESCE(subject_id, 0)
    )
    """,
)


def create_engine_with_statements(tmp_path, name: str, statements: list[str]):
    engine = create_engine(f"sqlite:///{tmp_path / name}")
    with engine.begin() as connection:
        for statement in (*EPOCH_STATEMENTS, *statements):
            connection.execute(text(statement))
    return engine


def read_epoch(
    session: Session,
    scope_type: SemanticScopeType,
    *,
    tenant_id: int,
    datasource_id: int | None = None,
    subject_id: int | None = None,
) -> int:
    coordinate = SemanticScopeCoordinate(
        scope_type=scope_type,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        subject_id=subject_id,
    )
    return load_semantic_scope_epochs(session, coordinates=[coordinate])[coordinate]


def permission_engine(tmp_path):
    return create_engine_with_statements(
        tmp_path,
        "permission_epoch.db",
        [
            """
            CREATE TABLE ds_permission (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, enable BOOLEAN NOT NULL,
                auth_target_type TEXT, auth_target_id BIGINT, type TEXT NOT NULL,
                ds_id BIGINT, table_id BIGINT, expression_tree TEXT,
                permissions TEXT, white_list_user TEXT, create_time DATETIME
            )
            """,
            """
            CREATE TABLE ds_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT, enable BOOLEAN NOT NULL,
                name TEXT NOT NULL, description TEXT, tenant_id BIGINT NOT NULL,
                scope TEXT NOT NULL, permission_list TEXT, user_list TEXT,
                white_list_user TEXT, create_time DATETIME
            )
            """,
            """
            CREATE TABLE core_datasource (
                id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, name TEXT NOT NULL,
                description TEXT, type TEXT, type_name TEXT, configuration TEXT,
                create_time DATETIME, create_by BIGINT, status TEXT, num TEXT,
                table_relation TEXT, embedding TEXT, recommended_config BIGINT,
                catalog_complete BOOLEAN NOT NULL, catalog_incomplete_reason TEXT,
                physical_schema_hash VARCHAR(64)
            )
            """,
            """
            CREATE TABLE core_table (
                id BIGINT PRIMARY KEY, ds_id BIGINT, checked BOOLEAN,
                table_name TEXT, table_comment TEXT, custom_comment TEXT, embedding TEXT,
                catalog_name TEXT, schema_name TEXT, catalog_key TEXT,
                schema_key TEXT, table_key TEXT
            )
            """,
            """
            INSERT INTO core_datasource (
                id, tenant_id, name, type, configuration, table_relation,
                recommended_config, catalog_complete, physical_schema_hash
            ) VALUES (9, 2, 'orders', 'postgresql', '{}', '[]', 1, 1,
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
            """,
            """
            INSERT INTO core_table (
                id, ds_id, checked, table_name, table_comment, custom_comment,
                catalog_key, schema_key, table_key
            ) VALUES (90, 9, 1, 'orders', '', '', '', 'public', 'orders')
            """,
        ],
    )


def tracking_engine(tmp_path):
    common_columns = """
        id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, datasource_id BIGINT,
        create_by BIGINT, update_by BIGINT, create_time BIGINT NOT NULL,
        update_time BIGINT NOT NULL
    """
    return create_engine_with_statements(
        tmp_path,
        "tracking_epoch.db",
        [
            f"""
            CREATE TABLE sys_tenant_tracking_config (
                {common_columns}, enabled BOOLEAN NOT NULL,
                default_event_table TEXT, default_subject_field TEXT,
                default_event_name_field TEXT, default_event_time_field TEXT,
                field_role_mappings TEXT, event_name_mappings TEXT,
                sql_rules TEXT, notes TEXT
            )
            """,
            f"""
            CREATE TABLE sys_tenant_tracking_table (
                {common_columns}, table_name TEXT NOT NULL, table_comment TEXT,
                table_role TEXT, aliases TEXT, ai_notes TEXT, extra_properties TEXT
            )
            """,
            f"""
            CREATE TABLE sys_tenant_tracking_field (
                {common_columns}, table_name TEXT NOT NULL, field_name TEXT NOT NULL,
                field_comment TEXT, field_role TEXT, semantic_type TEXT,
                source_field TEXT, json_path TEXT, update_mode TEXT, category TEXT,
                aliases TEXT, value_mappings TEXT, expression TEXT,
                required BOOLEAN NOT NULL, example_values TEXT, ai_notes TEXT,
                extra_properties TEXT
            )
            """,
            f"""
            CREATE TABLE sys_tenant_tracking_event_group (
                {common_columns}, group_key TEXT NOT NULL, group_name TEXT NOT NULL,
                description TEXT, event_names TEXT NOT NULL,
                sort_order BIGINT NOT NULL, enabled BOOLEAN NOT NULL
            )
            """,
        ],
    )


def schema_engine(tmp_path):
    return create_engine_with_statements(
        tmp_path,
        "schema_epoch.db",
        [
            """
            CREATE TABLE core_datasource (
                id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, name TEXT NOT NULL,
                description TEXT, type TEXT, type_name TEXT, configuration TEXT,
                create_time DATETIME, create_by BIGINT, status TEXT, num TEXT,
                table_relation TEXT, embedding TEXT, recommended_config BIGINT,
                catalog_complete BOOLEAN NOT NULL, catalog_incomplete_reason TEXT,
                physical_schema_hash VARCHAR(64)
            )
            """,
            """
            CREATE TABLE core_table (
                id BIGINT PRIMARY KEY, ds_id BIGINT, checked BOOLEAN,
                table_name TEXT, table_comment TEXT, custom_comment TEXT, embedding TEXT,
                catalog_name TEXT, schema_name TEXT, catalog_key TEXT,
                schema_key TEXT, table_key TEXT
            )
            """,
            """
            CREATE TABLE core_field (
                id BIGINT PRIMARY KEY, ds_id BIGINT, table_id BIGINT, checked BOOLEAN,
                field_name TEXT, field_type TEXT, field_comment TEXT,
                custom_comment TEXT, field_index BIGINT, field_key TEXT
            )
            """,
            """
            INSERT INTO core_datasource (
                id, tenant_id, name, type, configuration, table_relation,
                recommended_config, catalog_complete, physical_schema_hash
            ) VALUES (9, 2, 'orders', 'postgresql', '{}', '[]', 1, 1,
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
            """,
            """
            INSERT INTO core_table (
                id, ds_id, checked, table_name, table_comment, custom_comment,
                catalog_key, schema_key, table_key
            ) VALUES (90, 9, 1, 'orders', '', '', '', 'public', 'orders')
            """,
            """
            INSERT INTO core_field (
                id, ds_id, table_id, checked, field_name, field_type,
                field_comment, custom_comment, field_index, field_key
            ) VALUES (901, 9, 90, 1, 'amount', 'numeric', '', '', 0, 'amount')
            """,
        ],
    )
