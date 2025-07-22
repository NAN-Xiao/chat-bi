import datetime
import json
from typing import List

from fastapi import HTTPException
from sqlalchemy import and_, text, cast, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlbot_xpack.permissions.models.ds_permission import DsPermission
from sqlbot_xpack.permissions.models.ds_rules import DsRules
from sqlmodel import select

from apps.datasource.utils.utils import aes_decrypt
from apps.db.constant import DB
from apps.db.db import get_engine, get_tables, get_fields, exec_sql
from apps.db.engine import get_engine_config, get_engine_conn
from apps.db.type import db_type_relation
from common.core.deps import SessionDep, CurrentUser, Trans
from common.utils.utils import deepcopy_ignore_extra
from .table import get_tables_by_ds_id
from ..crud.field import delete_field_by_ds_id, update_field
from ..crud.table import delete_table_by_ds_id, update_table
from ..models.datasource import CoreDatasource, CreateDatasource, CoreTable, CoreField, ColumnSchema, TableObj, \
    DatasourceConf, TableAndFields


def get_datasource_list(session: SessionDep, user: CurrentUser):
    oid = user.oid if user.oid is not None else 1
    return session.query(CoreDatasource).filter(CoreDatasource.oid == oid).order_by(
        CoreDatasource.create_time.desc()).all()


def get_ds(session: SessionDep, id: int):
    statement = select(CoreDatasource).where(CoreDatasource.id == id)
    datasource = session.exec(statement).first()
    return datasource


def check_status(session: SessionDep, ds: CoreDatasource):
    conn = get_engine(ds)
    try:
        with conn.connect() as connection:
            print("success")
            return True
    except Exception as e:
        print("Fail:", e)
        return False


def check_name(session: SessionDep, trans: Trans, user: CurrentUser, ds: CoreDatasource):
    if ds.id is not None:
        ds_list = session.query(CoreDatasource).filter(
            and_(CoreDatasource.name == ds.name, CoreDatasource.id != ds.id, CoreDatasource.oid == user.oid)).all()
        if ds_list is not None and len(ds_list) > 0:
            raise HTTPException(status_code=500, detail=trans('i18n_ds_name_exist'))
    else:
        ds_list = session.query(CoreDatasource).filter(
            and_(CoreDatasource.name == ds.name, CoreDatasource.oid == user.oid)).all()
        if ds_list is not None and len(ds_list) > 0:
            raise HTTPException(status_code=500, detail=trans('i18n_ds_name_exist'))


def create_ds(session: SessionDep, trans: Trans, user: CurrentUser, create_ds: CreateDatasource):
    ds = CoreDatasource()
    deepcopy_ignore_extra(create_ds, ds)
    check_name(session, trans, user, ds)
    ds.create_time = datetime.datetime.now()
    # status = check_status(session, ds)
    ds.create_by = user.id
    ds.oid = user.oid if user.oid is not None else 1
    ds.status = "Success"
    ds.type_name = db_type_relation()[ds.type]
    record = CoreDatasource(**ds.model_dump())
    session.add(record)
    session.flush()
    session.refresh(record)
    ds.id = record.id
    session.commit()

    # save tables and fields
    sync_table(session, ds, create_ds.tables)
    updateNum(session, ds)
    return ds


def chooseTables(session: SessionDep, id: int, tables: List[CoreTable]):
    ds = session.query(CoreDatasource).filter(CoreDatasource.id == id).first()
    sync_table(session, ds, tables)
    updateNum(session, ds)


def update_ds(session: SessionDep, trans: Trans, user: CurrentUser, ds: CoreDatasource):
    ds.id = int(ds.id)
    check_name(session, trans, user, ds)
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
    else:  # delete all tables and fields in this ds
        session.query(CoreTable).filter(CoreTable.ds_id == ds.id).delete(synchronize_session=False)
        session.query(CoreField).filter(CoreField.ds_id == ds.id).delete(synchronize_session=False)
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


def update_table_and_fields(session: SessionDep, data: TableObj):
    update_table(session, data.table)
    for field in data.fields:
        update_field(session, field)


def updateTable(session: SessionDep, table: CoreTable):
    update_table(session, table)


def updateField(session: SessionDep, field: CoreField):
    update_field(session, field)


def preview(session: SessionDep, id: int, data: TableObj):
    if data.fields is None or len(data.fields) == 0:
        return {"fields": [], "data": [], "sql": ''}

    fields = [f.field_name for f in data.fields if f.checked]
    if fields is None or len(fields) == 0:
        return {"fields": [], "data": [], "sql": ''}

    ds = session.query(CoreDatasource).filter(CoreDatasource.id == id).first()
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration))) if ds.type != "excel" else get_engine_config()
    sql: str = ""
    if ds.type == "mysql":
        sql = f"""SELECT `{"`, `".join(fields)}` FROM `{data.table.table_name}` LIMIT 100"""
    elif ds.type == "sqlServer":
        sql = f"""SELECT [{"], [".join(fields)}] FROM [{conf.dbSchema}].[{data.table.table_name}]
            ORDER BY [{data.fields[0].field_name}]
            OFFSET 0 ROWS FETCH NEXT 100 ROWS ONLY"""
    elif ds.type == "pg" or ds.type == "excel":
        sql = f"""SELECT "{'", "'.join(fields)}" FROM "{conf.dbSchema}"."{data.table.table_name}" LIMIT 100"""
    elif ds.type == "oracle":
        sql = f"""SELECT "{'", "'.join(fields)}" FROM "{conf.dbSchema}"."{data.table.table_name}"
            ORDER BY "{data.fields[0].field_name}"
            OFFSET 0 ROWS FETCH NEXT 100 ROWS ONLY"""
    return exec_sql(ds, sql)


def fieldEnum(session: SessionDep, id: int):
    field = session.query(CoreField).filter(CoreField.id == id).first()
    if field is None:
        return []
    table = session.query(CoreTable).filter(CoreTable.id == field.table_id).first()
    if table is None:
        return []
    ds = session.query(CoreDatasource).filter(CoreDatasource.id == table.ds_id).first()
    if ds is None:
        return []

    db = DB.get_db(ds.type)
    sql = f"""SELECT DISTINCT {db.prefix}{field.field_name}{db.suffix} FROM {db.prefix}{table.table_name}{db.suffix}"""
    res = exec_sql(ds, sql)
    return [item.get(res.get('fields')[0]) for item in res.get('data')]


def updateNum(session: SessionDep, ds: CoreDatasource):
    all_tables = get_tables(ds) if ds.type != 'excel' else json.loads(aes_decrypt(ds.configuration)).get('sheets')
    selected_tables = get_tables_by_ds_id(session, ds.id)
    num = f'{len(selected_tables)}/{len(all_tables)}'

    record = session.exec(select(CoreDatasource).where(CoreDatasource.id == ds.id)).first()
    update_data = ds.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(record, field, value)
    record.num = num
    session.add(record)
    session.commit()


def get_table_obj_by_ds(session: SessionDep, current_user: CurrentUser, ds: CoreDatasource) -> List[TableAndFields]:
    _list: List = []
    tables = session.query(CoreTable).filter(CoreTable.ds_id == ds.id).all()
    conf = DatasourceConf(**json.loads(aes_decrypt(ds.configuration))) if ds.type != "excel" else get_engine_config()
    schema = conf.dbSchema if conf.dbSchema is not None and conf.dbSchema != "" else conf.database
    for table in tables:
        fields = session.query(CoreField).filter(and_(CoreField.table_id == table.id, CoreField.checked == True)).all()

        # do column permissions, filter fields
        column_permissions = session.query(DsPermission).filter(
            and_(DsPermission.table_id == table.id, DsPermission.type == 'column')).all()
        if column_permissions is not None:
            for permission in column_permissions:
                # check permission and user in same rules
                obj = session.query(DsRules).filter(
                    and_(DsRules.permission_list.op('@>')(cast([permission.id], JSONB)),
                         or_(DsRules.user_list.op('@>')(cast([f'{current_user.id}'], JSONB)),
                             DsRules.user_list.op('@>')(cast([current_user.id], JSONB))))
                ).first()
                if obj is not None:
                    permission_list = json.loads(permission.permissions)
                    fields = filter_list(fields, permission_list)

        _list.append(TableAndFields(schema=schema, table=table, fields=fields))
    return _list


def get_table_schema(session: SessionDep, current_user: CurrentUser, ds: CoreDatasource) -> str:
    schema_str = ""
    table_objs = get_table_obj_by_ds(session=session, current_user=current_user, ds=ds)
    if len(table_objs) == 0:
        return schema_str
    db_name = table_objs[0].schema
    schema_str += f"【DB_ID】 {db_name}\n【Schema】\n"
    for obj in table_objs:
        schema_str += f"# Table: {db_name}.{obj.table.table_name}" if ds.type != "mysql" else f"# Table: {obj.table.table_name}"
        table_comment = ''
        if obj.table.custom_comment:
            table_comment = obj.table.custom_comment.strip()
        if table_comment == '':
            schema_str += '\n[\n'
        else:
            schema_str += f", {table_comment}\n[\n"

        field_list = []
        for field in obj.fields:
            field_comment = ''
            if field.custom_comment:
                field_comment = field.custom_comment.strip()
            if field_comment == '':
                field_list.append(f"({field.field_name}:{field.field_type})")
            else:
                field_list.append(f"({field.field_name}:{field.field_type}, {field_comment})")
        schema_str += ",\n".join(field_list)
        schema_str += '\n]\n'
    return schema_str


def filter_list(list_a, list_b):
    id_to_invalid = {}
    for b in list_b:
        if not b['enable']:
            id_to_invalid[b['field_id']] = True

    return [a for a in list_a if not id_to_invalid.get(a.id, False)]
