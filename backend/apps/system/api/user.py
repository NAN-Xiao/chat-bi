from fastapi import APIRouter, Depends, Request    
from common.core.deps import CurrentUser

router = APIRouter(tags=["user"], prefix="/user")


@router.get("/info")
async def user_info():
    return {
        "name": "admin"
    }