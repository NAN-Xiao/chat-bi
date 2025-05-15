from fastapi import APIRouter
from ..crud.datasource import get_datasource_list, check_status, create_ds, update_ds, delete_ds, getTables, getFields, execSql
from common.core.deps import SessionDep
from ..models.datasource import CoreDatasource, CreateDatasource

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


@router.post("/update", response_model=CoreDatasource)
async def update(session: SessionDep, ds: CoreDatasource):
    return update_ds(session, ds)


@router.post("/delete/{id}", response_model=CoreDatasource)
async def delete(session: SessionDep, id: int):
    return delete_ds(session, id)


@router.post("/getTables/{id}")
async def get_tables(session: SessionDep, id: int):
    return getTables(session, id)


@router.post("/getFields/{id}/{table_name}")
async def get_tables(session: SessionDep, id: int, table_name: str):
    return getFields(session, id, table_name)


@router.post("/execSql/{id}/{sql}")
async def exec_sql(session: SessionDep, id: int, sql: str):
    return execSql(session, id, sql)
