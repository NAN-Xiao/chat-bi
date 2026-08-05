"""Catalog synchronization tests for complete physical object identities."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlmodel import Session, select

from apps.datasource.crud import datasource as datasource_crud
from apps.datasource.models.datasource import (
    ColumnSchema,
    CoreDatasource,
    CoreField,
    CoreTable,
)


def _catalog_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'catalog-sync.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE core_datasource ("
            "id INTEGER PRIMARY KEY, tenant_id BIGINT NOT NULL, name TEXT NOT NULL, "
            "description TEXT, type TEXT, type_name TEXT, configuration TEXT, "
            "create_time DATETIME, create_by BIGINT, status TEXT, num TEXT, "
            "table_relation JSON, embedding TEXT, recommended_config BIGINT, "
            "catalog_complete BOOLEAN NOT NULL, catalog_incomplete_reason TEXT, "
            "physical_schema_hash VARCHAR(64))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE core_table ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, ds_id BIGINT NOT NULL, "
            "checked BOOLEAN NOT NULL, table_name TEXT NOT NULL, table_comment TEXT, "
            "custom_comment TEXT, embedding TEXT, catalog_name TEXT, schema_name TEXT, "
            "catalog_key TEXT NOT NULL, schema_key TEXT NOT NULL, table_key TEXT NOT NULL, "
            "UNIQUE (ds_id, catalog_key, schema_key, table_key))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE core_field ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, ds_id BIGINT NOT NULL, "
            "table_id BIGINT NOT NULL, checked BOOLEAN NOT NULL, field_name TEXT NOT NULL, "
            "field_type TEXT, field_comment TEXT, custom_comment TEXT, field_index BIGINT, "
            "field_key TEXT NOT NULL, UNIQUE (table_id, field_key))"
        )
        connection.execute(
            text(
                "INSERT INTO core_datasource "
                "(id, tenant_id, name, type, configuration, status, recommended_config, "
                "catalog_complete) VALUES "
                "(9, 2, 'test', 'pg', :configuration, 'Success', 1, false)"
            ),
            {"configuration": '{"database":"app","dbSchema":"public"}'},
        )
    return engine


def test_sync_table_persists_full_keys_and_final_schema_hash(tmp_path, monkeypatch) -> None:
    engine = _catalog_engine(tmp_path)
    monkeypatch.setattr(
        datasource_crud,
        "getFieldsByDs",
        lambda *_args: [ColumnSchema("amount", "numeric", "")],
    )
    monkeypatch.setattr(datasource_crud, "run_save_table_embeddings", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(datasource_crud, "run_save_ds_embeddings", lambda *_args, **_kwargs: None)

    with Session(engine) as session:
        datasource = session.get(CoreDatasource, 9)
        assert datasource is not None
        datasource_crud.sync_table(
            session,
            datasource,
            [
                CoreTable(table_name="orders", table_comment="", schema_name="public"),
                CoreTable(table_name="orders", table_comment="", schema_name="archive"),
            ],
        )

    with Session(engine) as session:
        datasource = session.get(CoreDatasource, 9)
        tables = session.exec(select(CoreTable).order_by(CoreTable.schema_key)).all()
        fields = session.exec(select(CoreField).order_by(CoreField.table_id)).all()

        assert [(table.schema_key, table.table_key) for table in tables] == [
            ("archive", "orders"),
            ("public", "orders"),
        ]
        assert [field.field_key for field in fields] == ["amount", "amount"]
        assert datasource is not None
        assert datasource.catalog_complete is True
        assert datasource.catalog_incomplete_reason is None
        assert len(datasource.physical_schema_hash or "") == 64

    engine.dispose()


def test_sync_table_marks_catalog_incomplete_when_schema_is_unknown(tmp_path, monkeypatch) -> None:
    engine = _catalog_engine(tmp_path)
    monkeypatch.setattr(datasource_crud, "getFieldsByDs", lambda *_args: [])
    monkeypatch.setattr(datasource_crud, "run_save_table_embeddings", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(datasource_crud, "run_save_ds_embeddings", lambda *_args, **_kwargs: None)

    with Session(engine) as session:
        datasource = session.get(CoreDatasource, 9)
        assert datasource is not None
        datasource.type = "oracle"
        datasource.configuration = '{"database":"app","dbSchema":""}'
        datasource_crud.sync_table(
            session,
            datasource,
            [CoreTable(table_name="ORDERS", table_comment="")],
        )

    with Session(engine) as session:
        datasource = session.get(CoreDatasource, 9)
        assert datasource is not None
        assert datasource.catalog_complete is False
        assert datasource.catalog_incomplete_reason == "CATALOG_SCHEMA_REQUIRED"
        assert datasource.physical_schema_hash is None

    engine.dispose()
