from fastapi import APIRouter, HTTPException
from ..crud.datasource import get_datasource_list, check_status, create_ds, update_ds, delete_ds
from common.core.deps import SessionDep
from ..models.datasource import DatasourceConf, CoreDatasource

router = APIRouter(tags=["datasource"], prefix="/datasource")

@router.get("/list")
async def datasource_list(session: SessionDep):
    return get_datasource_list(session=session)

@router.post("/check")
async def check(session: SessionDep, ds: CoreDatasource):
    return check_status(session, ds)

@router.post("/add", response_model=CoreDatasource)
async def add(session: SessionDep, ds: CoreDatasource):
    return create_ds(session, ds)

@router.post("/update", response_model=CoreDatasource)
async def update(session: SessionDep, ds: CoreDatasource):
    return update_ds(session, ds)

@router.post("/delete/{id}", response_model=CoreDatasource)
async def delete(session: SessionDep, id: int):
    return delete_ds(session, id)