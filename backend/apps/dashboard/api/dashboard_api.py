from xmlrpc.client import Boolean

from fastapi import APIRouter, File, UploadFile, HTTPException

from apps.dashboard.crud.dashboard_service import get_dashboard_list, preview_with_id, \
    create_resource, create_canvas, validate_name
from apps.dashboard.models.dashboard_model import CreateDashboard, BaseDashboard, QueryDashboard
from common.core.deps import SessionDep, CurrentUser

router = APIRouter(tags=["dashboard"], prefix="/dashboard")

@router.post("/list")
async def datasource_list(session: SessionDep,dashboard: QueryDashboard):
    return get_dashboard_list(session=session,dashboard=dashboard)

@router.get("/preview_dashboard/{id}")
async def preview_dashboard(session: SessionDep,id:str):
    return preview_with_id(session=session,dashboard_id=id)

@router.post("/add", response_model=BaseDashboard)
async def add(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    return create_resource(session, user, dashboard)

@router.post("/update", response_model=BaseDashboard)
async def update(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    return create_resource(session, user, dashboard)

@router.post("/add_canvas", response_model=BaseDashboard)
async def add_canvas(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    return create_canvas(session, user, dashboard)

@router.post("/update_canvas", response_model=BaseDashboard)
async def update(session: SessionDep, user: CurrentUser, dashboard: CreateDashboard):
    return

@router.post("/check_name")
async def check_name(session: SessionDep, dashboard: QueryDashboard):
    return validate_name(session,dashboard)

