from fastapi import APIRouter

from apps.analysis_assistant.api import analysis_assistant
from apps.chat.api import chat
from apps.dashboard.api import dashboard_api
from apps.data_training.api import data_training
from apps.datasource.api import datasource, table_relation, recommended_problem, permission
from apps.system.api import login, user, aimodel, assistant, parameter, apikey, variable_api, audit, custom_prompt
from apps.terminology.api import terminology
from common.core.config import settings
from apps.settings.api import base
#from audit.api import audit_api


api_router = APIRouter()
api_router.include_router(analysis_assistant.router)
api_router.include_router(login.router)
api_router.include_router(user.router)
api_router.include_router(assistant.router)
api_router.include_router(aimodel.router)
api_router.include_router(base.router)
api_router.include_router(terminology.router)
api_router.include_router(data_training.router)
api_router.include_router(datasource.router)
api_router.include_router(permission.router)
api_router.include_router(chat.router)
api_router.include_router(dashboard_api.router)
if settings.MCP_ENABLED:
    from apps.mcp import mcp

    api_router.include_router(mcp.router)
api_router.include_router(table_relation.router)
api_router.include_router(parameter.router)
api_router.include_router(apikey.router)

api_router.include_router(recommended_problem.router)

api_router.include_router(variable_api.router)
api_router.include_router(audit.router)
api_router.include_router(custom_prompt.router)
