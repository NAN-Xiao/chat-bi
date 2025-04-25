from fastapi import APIRouter, HTTPException
from ..crud.datasource import get_datasource_list
from common.core.deps import SessionDep

router = APIRouter(tags=["datasource"], prefix="/datasource")

@router.get("/list")
def datasource_list(session: SessionDep):
    return get_datasource_list(session=session)