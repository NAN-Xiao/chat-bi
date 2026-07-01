"""
脚本说明：这个脚本放后端业务相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from fastapi import APIRouter

from apps.analysis_assistant.api import analysis_assistant
from apps.chat.api import chat
from apps.dashboard.api import dashboard_api
from apps.datasource.api import (
    datasource,
    permission,
    recommended_problem,
    table_relation,
)
from apps.external_mcp import api as external_mcp_api
from apps.knowledge_base.api import knowledge_base
from apps.settings.api import base
from apps.system.api import (
    aimodel,
    apikey,
    assistant,
    audit,
    custom_prompt,
    login,
    parameter,
    sso,
    task_queue,
    tenant,
    tracking_config,
    user,
    variable_api,
)
from common.core.config import settings

#from audit.api import audit_api


api_router = APIRouter()
api_router.include_router(analysis_assistant.router)
api_router.include_router(login.router)
api_router.include_router(sso.login_router)
api_router.include_router(user.router)
api_router.include_router(assistant.router)
api_router.include_router(aimodel.router)
api_router.include_router(base.router)
api_router.include_router(datasource.router)
api_router.include_router(external_mcp_api.router)
api_router.include_router(permission.router)
api_router.include_router(chat.router)
api_router.include_router(dashboard_api.router)
api_router.include_router(dashboard_api.platform_router)
api_router.include_router(knowledge_base.router)
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
api_router.include_router(task_queue.router)
api_router.include_router(tenant.router)
api_router.include_router(tracking_config.router)
api_router.include_router(sso.admin_router)
