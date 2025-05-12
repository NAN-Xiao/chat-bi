from fastapi import APIRouter

from apps.system.api import login, user, aimodel
from apps.settings.api import terminology
from apps.datasource.api import datasource
from apps.chat.api import chat


api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(user.router)
api_router.include_router(aimodel.router)
api_router.include_router(terminology.router)
api_router.include_router(datasource.router)
api_router.include_router(chat.router)


