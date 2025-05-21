import datetime
import json
from typing import List

from sqlalchemy import and_, text
from sqlmodel import select

from apps.datasource.utils.utils import aes_decrypt
from apps.db.db import get_engine, get_tables, get_fields, exec_sql
from apps.db.engine import get_engine_config
from apps.db.engine import get_engine_conn
from common.core.deps import SessionDep, CurrentUser
from common.utils.utils import deepcopy_ignore_extra
from ..crud.field import delete_field_by_ds_id, update_field
from ..crud.table import delete_table_by_ds_id, update_table
from ..models.datasource import CoreDatasource, CreateDatasource, CoreTable, CoreField, ColumnSchema, EditObj, \
    DatasourceConf


def get_datasource_list(session: SessionDep):
    statement = select(CoreDatasource).order_by(CoreDatasource.create_time.desc())
    datasource_list = session.exec(statement).fetchall()
    return datasource_list


def check_status(session: SessionDep, ds: CoreDatasource):
    conn = get_engine(ds)
    try:
        with conn.connect() as connection:
            print("success")
            return True
    except Exception as e:
        print("Fail:", e)
        return False


def create_ds(session: SessionDep, user: CurrentUser, create_ds: CreateDatasource):
    ds = CoreDatasource()
    deepcopy_ignore_extra(create_ds, ds)
    ds.create_time = datetime.datetime.now()
    # status = check_status(session, ds)
    ds.create_by = user.id
    ds.status = "Success"
    record = CoreDatasource(**ds.model_dump())
    session.add(record)
    session.flush()
    session.refresh(record)
    ds.id = record.id
    session.commit()

    # save tables and fields
    sync_table(session, ds, create_ds.tables)
    return ds


def chooseTables(session: SessionDep, id: int, tables: List[CoreTable]):
    ds = session.query(CoreDatasource).filter(CoreDatasource.id == id).first()
    sync_table(session, ds, tables)


def update_ds(session: SessionDep, ds: CoreDatasource):
    ds.id = int(ds.id)
    status = check_status(session, ds)
    ds.status = "Success" if status is True else "Fail"
    record = session.exec(select(CoreDatasource).where(CoreDatasource.id == ds.id)).first()
    update_data = ds.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(record, field, value)
    session.add(record)
    session.commit()
    return ds


def delete_ds(session: SessionDep, id: int):
    term = session.exec(select(CoreDatasource).where(CoreDatasource.id == id)).first()
    if term.type == "excel":
        # drop all tables for current datasource
        engine = get_engine_conn()
        conf = DatasourceConf(**json.loads(aes_decrypt(term.configuration)))
        with engine.connect() as conn:
            for sheet in conf.sheets:
                conn.execute(text(f'DROP TABLE IF EXISTS "{sheet["tableName"]}"'))
            conn.commit()

    session.delete(term)
    session.commit()
    delete_table_by_ds_id(session, id)
    delete_field_by_ds_id(session, id)
    return {
        "message": f"Datasource with ID {id} deleted successfully."
    }


def getTables(session: SessionDep, id: int):
    ds = session.exec(select(CoreDatasource).where(CoreDatasource.id == id)).first()
    tables = get_tables(ds)
    return tables


def getTablesByDs(session: SessionDep, ds: CoreDatasource):
    tables = get_tables(ds)
    return tables


def getFields(session: SessionDep, id: int, table_name: str):
    ds = session.exec(select(CoreDatasource).where(CoreDatasource.id == id)).first()
    fields = get_fields(ds, table_name)
    return fields


def getFieldsByDs(session: SessionDep, ds: CoreDatasource, table_name: str):
    fields = get_fields(ds, table_name)
    return fields


def execSql(session: SessionDep, id: int, sql: str):
    ds = session.exec(select(CoreDatasource).where(CoreDatasource.id == id)).first()
    return exec_sql(ds, sql)


def sync_table(session: SessionDep, ds: CoreDatasource, tables: List[CoreTable]):
    id_list = []
    for item in tables:
        statement = select(CoreTable).where(and_(CoreTable.ds_id == ds.id, CoreTable.table_name == item.table_name))
        record = session.exec(statement).first()
        # update exist table, only update table_comment
        if record is not None:
            item.id = record.id
            id_list.append(record.id)

            record.table_comment = item.table_comment
            session.add(record)
            session.commit()
        else:
            # save new table
            table = CoreTable(ds_id=ds.id, checked=True, table_name=item.table_name, table_comment=item.table_comment,
                              custom_comment=item.table_comment)
            session.add(table)
            session.flush()
            session.refresh(table)
            item.id = table.id
            id_list.append(table.id)
            session.commit()

        # sync field
        fields = getFieldsByDs(session, ds, item.table_name)
        sync_fields(session, ds, item, fields)

    if len(id_list) > 0:
        session.query(CoreTable).filter(and_(CoreTable.ds_id == ds.id, CoreTable.id.not_in(id_list))).delete(
            synchronize_session=False)
        session.query(CoreField).filter(and_(CoreField.ds_id == ds.id, CoreField.table_id.not_in(id_list))).delete(
            synchronize_session=False)
        session.commit()


def sync_fields(session: SessionDep, ds: CoreDatasource, table: CoreTable, fields: List[ColumnSchema]):
    id_list = []
    for item in fields:
        statement = select(CoreField).where(
            and_(CoreField.table_id == table.id, CoreField.field_name == item.fieldName))
        record = session.exec(statement).first()
        if record is not None:
            item.id = record.id
            id_list.append(record.id)

            record.field_comment = item.fieldComment
            session.add(record)
            session.commit()
        else:
            field = CoreField(ds_id=ds.id, table_id=table.id, checked=True, field_name=item.fieldName,
                              field_type=item.fieldType, field_comment=item.fieldComment,
                              custom_comment=item.fieldComment)
            session.add(field)
            session.flush()
            session.refresh(field)
            item.id = field.id
            id_list.append(field.id)
            session.commit()

    if len(id_list) > 0:
        session.query(CoreField).filter(and_(CoreField.table_id == table.id, CoreField.id.not_in(id_list))).delete(
            synchronize_session=False)
        session.commit()


def update_table_and_fields(session: SessionDep, data: EditObj):
    update_table(session, data.table)
    for field in data.fields:
        update_field(session, field)


def preview(session: SessionDep, id: int, data: EditObj):
    ds = session.query(CoreDatasource).filter(CoreDatasource.id == id).first()
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration))) if ds.type != "excel" else get_engine_config()
    sql: str = ""
    if ds.type == "mysql":
        sql = f"""SELECT `{"`, `".join([f.field_name for f in data.fields if f.checked])}` FROM `{data.table.table_name}` LIMIT 100"""
    elif ds.type == "sqlServer":
        sql = f"""SELECT [{"], [".join([f.field_name for f in data.fields if f.checked])}] FROM [{conf.dbSchema}].[{data.table.table_name}]
            ORDER BY [{data.fields[0].field_name}]
            OFFSET 0 ROWS FETCH NEXT 100 ROWS ONLY"""
    elif ds.type == "pg" or ds.type == "excel":
        sql = f"""SELECT "{'", "'.join([f.field_name for f in data.fields if f.checked])}" FROM "{conf.dbSchema}"."{data.table.table_name}" LIMIT 100"""
    return exec_sql(ds, sql)
