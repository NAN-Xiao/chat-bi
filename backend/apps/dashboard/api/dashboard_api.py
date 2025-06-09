
from fastapi import APIRouter, File, UploadFile, HTTPException

from apps.dashboard.crud.dashboard_service import get_dashboard_list, preview_with_id, \
    create_resource, create_canvas
from apps.dashboard.models.dashboard_model import CreateDashboard
from common.core.deps import SessionDep, CurrentUser

router = APIRouter(tags=["dashboard"], prefix="/dashboard")

@router.post("/list")
async def datasource_list(session: SessionDep):
    return get_dashboard_list(session=session)

@router.get("/preview_dashboard/{id}")
async def preview_dashboard(session: SessionDep,id:str):
    return preview_with_id(session=session,dashboard_id=id)

@router.post("/add", response_model=CreateDashboard)
async def add(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    return create_resource(session, user, dashboard)

@router.post("/update", response_model=CreateDashboard)
async def update(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    return create_resource(session, user, dashboard)

@router.post("/add_dashboard", response_model=CreateDashboard)
async def add_dashboard(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    return create_canvas(session, user, dashboard)

@router.post("/update_dashboard", response_model=CreateDashboard)
async def update(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    return