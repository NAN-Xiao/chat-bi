import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session


def test_date_metadata_is_scoped_to_workspace_datasource_and_allowed_fields():
    from apps.datasource.crud.sql_date_metadata import load_date_field_encodings

    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE sys_tenant_tracking_config (tenant_id BIGINT, datasource_id BIGINT, enabled BOOLEAN)')
        connection.exec_driver_sql('CREATE TABLE sys_tenant_tracking_field (tenant_id BIGINT, datasource_id BIGINT, table_name TEXT, field_name TEXT, extra_properties JSON, expression TEXT, json_path TEXT)')
        connection.exec_driver_sql('INSERT INTO sys_tenant_tracking_config VALUES (1, 10, 1), (2, 10, 1), (1, 20, 1), (1, 30, 0)')
        for tenant_id, datasource_id, field, encoding in [
            (1, 10, 'day', 'yyyymmdd'), (2, 10, 'day', 'iso_date'),
            (1, 20, 'day', 'iso_date'), (1, 10, 'hidden', 'yyyymmdd'),
            (1, 30, 'day', 'yyyymmdd'),
        ]:
            connection.execute(text('INSERT INTO sys_tenant_tracking_field VALUES (:tenant, :ds, :table, :field, :extra, NULL, NULL)'),
                               {'tenant': tenant_id, 'ds': datasource_id, 'table': 'orders', 'field': field, 'extra': json.dumps({'encoding': encoding})})
    with Session(engine) as session:
        assert load_date_field_encodings(session, 1, 10, {'orders': {'fields': {'day'}}}) == {('orders', 'day'): '%Y%m%d'}
        assert load_date_field_encodings(session, 1, 20, {'orders': {'fields': {'day'}}}) == {('orders', 'day'): '%Y-%m-%d'}
        assert load_date_field_encodings(session, 1, 30, {'orders': {'fields': {'day'}}}) == {}
        assert load_date_field_encodings(session, 1, 10, {'orders': {'fields': set()}}) == {}


def test_shared_query_entry_rejects_metadata_conflict(monkeypatch):
    import sqlglot
    from apps.datasource.crud import sql_engine_executor as executor
    from common.utils.sql_date_validation import SqlDateConversionError

    sql = "SELECT STR_TO_DATE(CAST(day AS CHAR), '%Y-%m-%d') FROM orders"
    monkeypatch.setattr(executor, 'check_sql_read', lambda *args: (True, ''))
    monkeypatch.setattr(executor, 'validate_sql_scope', lambda *args, **kwargs: ([sqlglot.parse_one(sql, read='mysql')], {'orders'}, {'orders': {'fields': {'day'}}}))
    monkeypatch.setattr(executor, 'load_date_field_encodings', lambda *args: {('orders', 'day'): '%Y%m%d'})
    with pytest.raises(SqlDateConversionError):
        executor.prepare_query_sql(None, SimpleNamespace(tenant_id=1), SimpleNamespace(id=10, type='mysql'), sql, apply_row_permissions=False)
