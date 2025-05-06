from fastapi import APIRouter, HTTPException
from ..crud.datasource import get_datasource_list, check_status, create_ds
from common.core.deps import SessionDep
from ..models.datasource import DatasourceConf, CoreDatasource

router = APIRouter(tags=["datasource"], prefix="/datasource")

@router.get("/list")
def datasource_list(session: SessionDep):
    return get_datasource_list(session=session)

@router.post("/check")
def check(session: SessionDep, conf: DatasourceConf):
    return check_status(session, conf)

@router.post("/add", response_model=CoreDatasource)
def check(session: SessionDep, ds: CoreDatasource):
    return create_ds(session, ds)
