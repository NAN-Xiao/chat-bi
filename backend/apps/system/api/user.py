from fastapi import APIRouter, Depends, Request    
from common.core.deps import CurrentUser

router = APIRouter(tags=["user"], prefix="/user")


@router.get("/info")
async def user_info(current_user: CurrentUser):
    return current_user.to_dict()