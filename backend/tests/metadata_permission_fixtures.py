"""SQLite fixtures shared by metadata-permission tests."""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlmodel import Session


def workspace_user(*, user_id: int = 7, tenant_id: int = 2, role: str = "member") -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        tenant_id=tenant_id,
        tenant_role=role,
        system_role="viewer",
        isAdmin=False,
        workspace_status="active",
    )


@contextmanager
def metadata_permission_session(database_path):
    engine = create_engine(f"sqlite:///{database_path}")
    statements = [
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
        CREATE TABLE core_datasource_tenant_binding (
            id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL,
            datasource_id BIGINT NOT NULL, create_by BIGINT, create_time DATETIME
        )
        """,
        """
        CREATE TABLE core_table (
            id BIGINT PRIMARY KEY, ds_id BIGINT NOT NULL, checked BOOLEAN NOT NULL,
            table_name TEXT NOT NULL, table_comment TEXT, custom_comment TEXT,
            embedding TEXT, catalog_name TEXT, schema_name TEXT,
            catalog_key TEXT NOT NULL, schema_key TEXT NOT NULL,
            table_key TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE core_field (
            id BIGINT PRIMARY KEY, ds_id BIGINT NOT NULL, table_id BIGINT NOT NULL,
            checked BOOLEAN NOT NULL, field_name TEXT NOT NULL, field_type TEXT,
            field_comment TEXT, custom_comment TEXT, field_index BIGINT,
            field_key TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE sys_tenant_tracking_config (
            id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, datasource_id BIGINT,
            enabled BOOLEAN NOT NULL, default_event_table TEXT,
            default_event_name_field TEXT, event_name_mappings TEXT
        )
        """,
        """
        CREATE TABLE sys_tenant_tracking_field (
            id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, datasource_id BIGINT,
            table_name TEXT NOT NULL, field_name TEXT NOT NULL, field_comment TEXT,
            source_field TEXT, json_path TEXT
        )
        """,
        """
        CREATE TABLE ds_permission (
            id INTEGER PRIMARY KEY, name TEXT, enable BOOLEAN, auth_target_type TEXT,
            auth_target_id BIGINT, type TEXT, ds_id BIGINT, table_id BIGINT,
            expression_tree TEXT, permissions TEXT, white_list_user TEXT,
            create_time DATETIME
        )
        """,
        """
        CREATE TABLE ds_rules (
            id INTEGER PRIMARY KEY, enable BOOLEAN, name TEXT, description TEXT,
            tenant_id BIGINT, scope TEXT, permission_list TEXT, user_list TEXT,
            white_list_user TEXT, create_time DATETIME
        )
        """,
        """
        CREATE TABLE core_roi_workspace_config (
            id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL,
            datasource_id BIGINT NOT NULL, deleted BOOLEAN NOT NULL
        )
        """,
    ]
    current_mapping = json.dumps(
        [
            {
                "event_name": "purchase",
                "event_display_name": "Purchase",
                "properties": [
                    {
                        "property_name": "amount",
                        "property_display_name": "Amount",
                        "source_field": "payload",
                        "json_path": "$.amount",
                    }
                ],
            }
        ]
    )
    foreign_mapping = json.dumps(
        [
            {
                "event_name": "foreign_event",
                "properties": [
                    {
                        "property_name": "foreign_property",
                        "source_field": "secret_payload",
                        "json_path": "$.secret",
                    }
                ],
            }
        ]
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(
            text(
                "INSERT INTO core_datasource "
                "(id, tenant_id, name, type, configuration, create_by, recommended_config, "
                "catalog_complete, physical_schema_hash, table_relation) VALUES "
                "(9, 999, 'current', 'pg', '{}', 1, 1, 1, :hash, '[]'), "
                "(10, 999, 'foreign', 'pg', '{}', 1, 1, 1, :hash, '[]')"
            ),
            {"hash": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO core_datasource_tenant_binding "
                "(id, tenant_id, datasource_id) VALUES (1, 2, 9), (2, 3, 10)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO core_table "
                "(id, ds_id, checked, table_name, table_comment, custom_comment, "
                "catalog_name, schema_name, catalog_key, schema_key, table_key) VALUES "
                "(90, 9, 1, 'events', '', '', NULL, 'public', '', 'public', 'events'), "
                "(91, 9, 1, 'orders', '', '', NULL, 'archive', '', 'archive', 'orders'), "
                "(100, 10, 1, 'secret_events', '', '', NULL, 'foreign_schema', "
                "'', 'foreign_schema', 'secret_events')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO core_field "
                "(id, ds_id, table_id, checked, field_name, field_type, field_comment, "
                "custom_comment, field_index, field_key) VALUES "
                "(901, 9, 90, 1, 'event_name', 'text', '', '', 1, 'event_name'), "
                "(902, 9, 90, 1, 'payload', 'jsonb', '', '', 2, 'payload'), "
                "(1001, 10, 100, 1, 'event_name', 'text', '', '', 1, 'event_name'), "
                "(1002, 10, 100, 1, 'secret_payload', 'jsonb', '', '', 2, 'secret_payload')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO sys_tenant_tracking_config "
                "(id, tenant_id, datasource_id, enabled, default_event_table, "
                "default_event_name_field, event_name_mappings) VALUES "
                "(1, 2, 9, 1, 'events', 'event_name', :current_mapping), "
                "(2, 3, 10, 1, 'secret_events', 'event_name', :foreign_mapping)"
            ),
            {"current_mapping": current_mapping, "foreign_mapping": foreign_mapping},
        )
        connection.execute(
            text(
                "INSERT INTO sys_tenant_tracking_field "
                "(id, tenant_id, datasource_id, table_name, field_name, field_comment, "
                "source_field, json_path) VALUES "
                "(200, 2, 9, 'events', 'payload.amount', '', 'payload', '$.amount')"
            )
        )
    with Session(engine) as session:
        yield session
    engine.dispose()


def insert_rule(session: Session, *, permission_id: int, permission_type: str, targets: list[dict], table_id=None):
    session.execute(
        text(
            "INSERT INTO ds_permission "
            "(id, name, enable, auth_target_type, type, ds_id, table_id, "
            "expression_tree, permissions, white_list_user) VALUES "
            "(:id, :name, 1, 'user', :type, 9, :table_id, '{}', :targets, '[]')"
        ),
        {
            "id": permission_id,
            "name": f"permission-{permission_id}",
            "type": permission_type,
            "table_id": table_id,
            "targets": json.dumps(targets),
        },
    )
    session.execute(
        text(
            "INSERT INTO ds_rules "
            "(id, enable, name, description, tenant_id, scope, permission_list, "
            "user_list, white_list_user) VALUES "
            "(:id, 1, :name, '', 2, 'TENANT', :permission_list, '[\"7\"]', '[]')"
        ),
        {
            "id": 1000 + permission_id,
            "name": f"rule-{permission_id}",
            "permission_list": json.dumps([permission_id]),
        },
    )
    session.commit()
