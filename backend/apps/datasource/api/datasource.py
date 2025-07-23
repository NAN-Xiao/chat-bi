import hashlib
import os
import uuid
from typing import List

import pandas as pd
from fastapi import APIRouter, File, UploadFile, HTTPException

from apps.db.engine import create_table, get_data_engine, insert_data
from common.core.deps import SessionDep, CurrentUser, Trans
from ..crud.datasource import get_datasource_list, check_status, create_ds, update_ds, delete_ds, getTables, getFields, \
    execSql, update_table_and_fields, getTablesByDs, chooseTables, preview, updateTable, updateField, get_ds, fieldEnum
from ..crud.field import get_fields_by_table_id
from ..crud.table import get_tables_by_ds_id
from ..models.datasource import CoreDatasource, CreateDatasource, TableObj, CoreTable, CoreField

router = APIRouter(tags=["datasource"], prefix="/datasource")
path = "/opt/sqlbot/data/excel"


@router.get("/list")
async def datasource_list(session: SessionDep, user: CurrentUser):
    return get_datasource_list(session=session, user=user)


@router.post("/get/{id}")
async def get_datasource(session: SessionDep, id: int):
    return get_ds(session, id)


@router.post("/check")
async def check(session: SessionDep, ds: CoreDatasource):
    return check_status(session, ds, True)


@router.post("/add", response_model=CoreDatasource)
async def add(session: SessionDep, trans: Trans, user: CurrentUser, ds: CreateDatasource):
    return create_ds(session, trans, user, ds)


@router.post("/chooseTables/{id}")
async def choose_tables(session: SessionDep, id: int, tables: List[CoreTable]):
    chooseTables(session, id, tables)


@router.post("/update", response_model=CoreDatasource)
async def update(session: SessionDep, trans: Trans, user: CurrentUser, ds: CoreDatasource):
    return update_ds(session, trans, user, ds)


@router.post("/delete/{id}", response_model=CoreDatasource)
async def delete(session: SessionDep, id: int):
    return delete_ds(session, id)


@router.post("/getTables/{id}")
async def get_tables(session: SessionDep, id: int):
    return getTables(session, id)


@router.post("/getTablesByConf")
async def get_tables_by_conf(session: SessionDep, ds: CoreDatasource):
    return getTablesByDs(session, ds)


@router.post("/getFields/{id}/{table_name}")
async def get_fields(session: SessionDep, id: int, table_name: str):
    return getFields(session, id, table_name)


@router.post("/execSql/{id}/{sql}")
async def exec_sql(session: SessionDep, id: int, sql: str):
    return execSql(session, id, sql)


@router.post("/tableList/{id}")
async def table_list(session: SessionDep, id: int):
    return get_tables_by_ds_id(session, id)


@router.post("/fieldList/{id}")
async def field_list(session: SessionDep, id: int):
    return get_fields_by_table_id(session, id)


@router.post("/editLocalComment")
async def edit_local(session: SessionDep, data: TableObj):
    update_table_and_fields(session, data)


@router.post("/editTable")
async def edit_table(session: SessionDep, table: CoreTable):
    updateTable(session, table)


@router.post("/editField")
async def edit_field(session: SessionDep, field: CoreField):
    updateField(session, field)


@router.post("/previewData/{id}")
async def edit_local(session: SessionDep, current_user: CurrentUser, id: int, data: TableObj):
    return preview(session, current_user, id, data)


@router.post("/fieldEnum/{id}")
async def field_enum(session: SessionDep, id: int):
    return fieldEnum(session, id)


@router.post("/uploadExcel")
async def upload_excel(session: SessionDep, file: UploadFile = File(...)):
    ALLOWED_EXTENSIONS = {"xlsx", "xls", "csv"}
    if not file.filename.lower().endswith(tuple(ALLOWED_EXTENSIONS)):
        raise HTTPException(400, "Only support .xlsx/.xls/.csv")

    os.makedirs(path, exist_ok=True)
    filename = f"{file.filename.split('.')[0]}_{hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:10]}.{file.filename.split('.')[1]}"
    save_path = os.path.join(path, filename)
    with open(save_path, "wb") as f:
        f.write(await file.read())

    conn = get_data_engine()
    sheets = []
    if filename.endswith(".csv"):
        df = pd.read_csv(save_path)
        tableName = f"sheet1_{hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:10]}"
        sheets.append({"tableName": tableName, "tableComment": ""})
        column_len = len(df.dtypes)
        fields = []
        for i in range(column_len):
            # build fields
            fields.append({"name": df.columns[i], "type": str(df.dtypes[i]), "relType": ""})
        # create table
        create_table(conn, tableName, fields)

        data = [
            {df.columns[i]: None if pd.isna(row[i]) else (int(row[i]) if "int" in str(df.dtypes[i]) else row[i])
             for i in range(len(row))}
            for row in df.values
        ]
        # insert data
        insert_data(conn, tableName, fields, data)
    else:
        df_sheets = pd.read_excel(save_path, sheet_name=None)
        # build columns and data to insert db
        for sheet_name, df in df_sheets.items():
            tableName = f"{sheet_name}_{hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:10]}"
            sheets.append({"tableName": tableName, "tableComment": ""})
            column_len = len(df.dtypes)
            fields = []
            for i in range(column_len):
                # build fields
                fields.append({"name": df.columns[i], "type": str(df.dtypes[i]), "relType": ""})
            # create table
            create_table(conn, tableName, fields)

            data = [
                {df.columns[i]: None if pd.isna(row[i]) else (int(row[i]) if "int" in str(df.dtypes[i]) else row[i])
                 for i in range(len(row))}
                for row in df.values
            ]
            # insert data
            insert_data(conn, tableName, fields, data)
    conn.close()

    os.remove(save_path)
    return {"filename": filename, "sheets": sheets}
