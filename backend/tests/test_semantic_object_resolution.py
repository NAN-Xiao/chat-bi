"""Resolution tests for declared objects against the bound datasource catalog."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session

from apps.datasource.crud.semantic_object_key import (
    DeclaredObjectPath,
    SemanticObjectKey,
)
from apps.datasource.crud.semantic_object_resolution import (
    ObjectResolutionStatus,
    resolve_table_key,
)


@pytest.fixture
def catalog_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'semantic-catalog.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE core_datasource ("
            "id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, type VARCHAR(64), "
            "catalog_complete BOOLEAN NOT NULL, physical_schema_hash VARCHAR(64))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE core_datasource_tenant_binding ("
            "id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, datasource_id BIGINT NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE core_table ("
            "id BIGINT PRIMARY KEY, ds_id BIGINT NOT NULL, checked BOOLEAN NOT NULL, "
            "table_name TEXT NOT NULL, catalog_name VARCHAR(255), schema_name VARCHAR(255), "
            "catalog_key VARCHAR(255) NOT NULL, schema_key VARCHAR(255) NOT NULL, "
            "table_key VARCHAR(255) NOT NULL)"
        )
        connection.execute(
            text(
                "INSERT INTO core_datasource "
                "(id, tenant_id, type, catalog_complete, physical_schema_hash) "
                "VALUES (9, 2, 'pg', true, :schema_hash)"
            ),
            {"schema_hash": "a" * 64},
        )
        connection.exec_driver_sql(
            "INSERT INTO core_datasource_tenant_binding "
            "(id, tenant_id, datasource_id) VALUES (1, 2, 9)"
        )
    with Session(engine) as session:
        yield session
    engine.dispose()


def _seed_catalog_table(session: Session, *, row_id: int, schema: str, table_name: str) -> None:
    session.exec(
        text(
            "INSERT INTO core_table "
            "(id, ds_id, checked, table_name, catalog_name, schema_name, "
            "catalog_key, schema_key, table_key) "
            "VALUES (:id, 9, true, :table_name, NULL, :schema, '', :schema, :table_key)"
        ),
        params={
            "id": row_id,
            "table_name": table_name,
            "schema": schema,
            "table_key": table_name.lower(),
        },
    )
    session.commit()


def test_unqualified_table_is_ambiguous_in_multi_schema(catalog_session: Session) -> None:
    _seed_catalog_table(catalog_session, row_id=1, schema="public", table_name="orders")
    _seed_catalog_table(catalog_session, row_id=2, schema="archive", table_name="orders")

    result = resolve_table_key(
        catalog_session,
        datasource_id=9,
        declared=DeclaredObjectPath(object_type="TABLE", table="orders"),
    )

    assert result.status == ObjectResolutionStatus.AMBIGUOUS
    assert result.key is None
    assert result.message == "对象 orders 在当前数据源中存在多个匹配，请指定 Schema。"


def test_qualified_table_resolves_to_bound_workspace(catalog_session: Session) -> None:
    _seed_catalog_table(catalog_session, row_id=1, schema="public", table_name="orders")

    result = resolve_table_key(
        catalog_session,
        datasource_id=9,
        declared=DeclaredObjectPath(object_type="TABLE", schema="public", table="orders"),
    )

    assert result.status == ObjectResolutionStatus.RESOLVED
    assert result.key == SemanticObjectKey(
        object_type="TABLE",
        tenant_id=2,
        datasource_id=9,
        catalog="",
        schema="public",
        table="orders",
    )
