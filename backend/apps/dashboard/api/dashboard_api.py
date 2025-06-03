import hashlib
import os
import uuid
from typing import List
from fastapi import APIRouter, File, UploadFile, HTTPException

from apps.dashboard.crud.dashboard_service import get_dashboard_list, preview_with_id
from common.core.deps import SessionDep

router = APIRouter(tags=["dashboard"], prefix="/dashboard")

@router.get("/list")
async def datasource_list(session: SessionDep):
    return get_dashboard_list(session=session)

@router.get("/preview_dashboard/{id}")
async def preview_dashboard(session: SessionDep,id:str):
    return preview_with_id(session=session,dashboard_id=id)