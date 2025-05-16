from fastapi import APIRouter
from ..crud.datasource import get_datasource_list, check_status, create_ds, update_ds, delete_ds, getTables, getFields, \
    execSql, update_table_and_fields, getTablesByDs, chooseTables
from common.core.deps import SessionDep
from ..models.datasource import CoreDatasource, CreateDatasource, EditObj, CoreTable
from ..crud.table import get_tables_by_ds_id
from ..crud.field import get_fields_by_table_id
from typing import List

router = APIRouter(tags=["datasource"], prefix="/datasource")


@router.get("/list")
async def datasource_list(session: SessionDep):
    return get_datasource_list(session=session)


@router.post("/check")
async def check(session: SessionDep, ds: CoreDatasource):
    return check_status(session, ds)


@router.post("/add", response_model=CoreDatasource)
async def add(session: SessionDep, ds: CreateDatasource):
    return create_ds(session, ds)


@router.post("/chooseTables/{id}")
async def choose_tables(session: SessionDep, id: int, tables: List[CoreTable]):
    chooseTables(session, id, tables)


@router.post("/update", response_model=CoreDatasource)
async def update(session: SessionDep, ds: CoreDatasource):
    return update_ds(session, ds)


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
async def get_tables(session: SessionDep, id: int, table_name: str):
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
async def edit_local(session: SessionDep, data: EditObj):
    update_table_and_fields(session, data)
