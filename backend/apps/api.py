from fastapi import APIRouter

from apps.system.api import login, user
from apps.settings.api import terminology

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(user.router)
api_router.include_router(terminology.router)


