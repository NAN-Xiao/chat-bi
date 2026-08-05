"""ROI datasource table permission management boundaries."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, create_engine

from apps.datasource.api import permission as permission_api


def make_admin(*, tenant_id: int = 11, user_id: int = 7) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        tenant_id=tenant_id,
        tenant_role="admin",
        system_role="viewer",
        isAdmin=False,
        workspace_status="active",
    )


def roi_rule_payload(permission_type: str) -> dict:
    return {
        "tenant_id": 11,
        "scope": "TENANT",
        "permissions": [
            {
                "id": 9001,
                "name": "ROI 禁止表",
                "enable": True,
                "type": permission_type,
                "ds_id": 202,
                "table_id": 2001,
                "permissions": [],
            }
        ],
        "permission_list": [9001],
        "users": ["7"],
    }


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    statements = [
        """
        CREATE TABLE core_datasource (
            id BIGINT PRIMARY KEY, tenant_id BIGINT, name TEXT, description TEXT,
            type TEXT, type_name TEXT, configuration TEXT, create_time DATETIME,
            create_by BIGINT, status TEXT, num TEXT, table_relation TEXT,
            embedding TEXT, recommended_config BIGINT,
            catalog_complete BOOLEAN NOT NULL DEFAULT 0,
            catalog_incomplete_reason TEXT, physical_schema_hash VARCHAR(64)
        )
        """,
        """
        CREATE TABLE core_datasource_tenant_binding (
            id INTEGER PRIMARY KEY, tenant_id BIGINT, datasource_id BIGINT,
            create_by BIGINT, create_time DATETIME
        )
        """,
        """
        CREATE TABLE core_datasource_user (
            id BIGINT PRIMARY KEY, ds_id BIGINT, user_id BIGINT, role TEXT,
            create_by BIGINT, create_time DATETIME
        )
        """,
        """
        CREATE TABLE core_roi_workspace_config (
            id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL,
            datasource_id BIGINT NOT NULL, version INTEGER NOT NULL,
            create_by BIGINT, update_by BIGINT, create_time BIGINT NOT NULL,
            update_time BIGINT NOT NULL, deleted BOOLEAN NOT NULL
        )
        """,
        """
        CREATE TABLE core_table (
            id BIGINT PRIMARY KEY, ds_id BIGINT, checked BOOLEAN,
            table_name TEXT, table_comment TEXT, custom_comment TEXT, embedding TEXT,
            catalog_name VARCHAR(255), schema_name VARCHAR(255),
            catalog_key VARCHAR(255), schema_key VARCHAR(255), table_key VARCHAR(255)
        )
        """,
        """
        CREATE TABLE ds_permission (
            id BIGINT PRIMARY KEY, name TEXT, enable BOOLEAN, auth_target_type TEXT,
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
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(
            text(
                "INSERT INTO core_datasource "
                "(id, tenant_id, name, description, type, type_name, configuration, "
                "create_by, status, recommended_config) VALUES "
                "(101, 1, '修仙', '', 'pg', 'PostgreSQL', '{}', 1, 'success', 1), "
                "(202, 1, 'ROI_修仙', '', 'pg', 'PostgreSQL', '{}', 1, 'success', 1), "
                "(303, 1, '其他 ROI', '', 'pg', 'PostgreSQL', '{}', 1, 'success', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO core_datasource_tenant_binding "
                "(id, tenant_id, datasource_id) VALUES (1, 11, 101)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO core_roi_workspace_config "
                "(id, tenant_id, datasource_id, version, create_time, update_time, deleted) "
                "VALUES (1, 11, 202, 1, 1, 1, 0), (2, 22, 303, 1, 1, 1, 0)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO core_table "
                "(id, ds_id, checked, table_name, table_comment, custom_comment) VALUES "
                "(1001, 101, 1, 'orders', '', ''), "
                "(2001, 202, 1, 'private_table', '', ''), "
                "(3001, 303, 1, 'other_private_table', '', '')"
            )
        )
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


def test_table_permission_sources_include_bound_and_active_roi(session: Session) -> None:
    rows = permission_api._list_permission_datasources(session, make_admin(), "table")

    assert [(int(row["id"]), row["permission_source"]) for row in rows] == [
        (101, "ordinary"),
        (202, "roi"),
    ]


@pytest.mark.parametrize("permission_type", ["column", "row"])
def test_non_table_permission_sources_exclude_roi(
    session: Session,
    permission_type: str,
) -> None:
    rows = permission_api._list_permission_datasources(
        session,
        make_admin(),
        permission_type,
    )

    assert [int(row["id"]) for row in rows] == [101]


@pytest.mark.parametrize("permission_type", ["column", "row"])
def test_roi_only_datasource_rejects_column_and_row_rules(
    session: Session,
    permission_type: str,
) -> None:
    with pytest.raises(HTTPException) as exc:
        permission_api._validate_permission_rule_scope(
            session,
            make_admin(),
            roi_rule_payload(permission_type),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "ROI 数据源仅支持表禁止"


def test_roi_table_rule_is_visible_only_in_configured_workspace(session: Session) -> None:
    rule = roi_rule_payload("table")

    assert permission_api._filter_rule_for_current_context(
        session,
        make_admin(tenant_id=11),
        rule,
    )
    assert (
        permission_api._filter_rule_for_current_context(
            session,
            make_admin(tenant_id=22),
            rule,
        )
        is None
    )
