from fastapi import APIRouter

from fastapi import Depends, HTTPException

from apps.datasource.crud.datasource import update_ds_recommended_config
from apps.datasource.crud.permission import has_datasource_access
from apps.datasource.crud.recommended_problem import get_datasource_recommended, \
    save_recommended_problem, get_datasource_recommended_base
from apps.datasource.models.datasource import RecommendedProblemBase
from apps.swagger.i18n import PLACEHOLDER_PREFIX
from apps.system.schemas.business_access import require_chatbi_business_or_platform_admin
from apps.system.schemas.permission import AppPermission, require_permissions
from common.audit.models.log_model import OperationType, OperationModules
from common.audit.schemas.logger_decorator import LogConfig, system_log
from common.core.deps import SessionDep, CurrentUser

router = APIRouter(
    tags=["recommended problem"],
    prefix="/recommended_problem",
    dependencies=[Depends(require_chatbi_business_or_platform_admin)],
)


@router.get("/get_datasource_recommended/{ds_id}", response_model=None, summary=f"{PLACEHOLDER_PREFIX}rp_get")
@require_permissions(permission=AppPermission(type='ds', keyExpression="ds_id"))
async def datasource_recommended(session: SessionDep, _user: CurrentUser, ds_id: int):
    """
    是什么：datasource_recommended 是 backend/apps/datasource/api/recommended_problem.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 datasource_recommended 的语义处理数据源相关逻辑，并把结果返回或写入状态。
    """
    return get_datasource_recommended(session, ds_id)


@router.get("/get_datasource_recommended_base/{ds_id}", response_model=None, summary=f"{PLACEHOLDER_PREFIX}rp_base")
@require_permissions(permission=AppPermission(type='ds', keyExpression="ds_id"))
async def datasource_recommended(session: SessionDep, _user: CurrentUser, ds_id: int):
    """
    是什么：datasource_recommended 是 backend/apps/datasource/api/recommended_problem.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 datasource_recommended 的语义处理数据源相关逻辑，并把结果返回或写入状态。
    """
    return get_datasource_recommended_base(session, ds_id)


@router.post("/save_recommended_problem", response_model=None, summary=f"{PLACEHOLDER_PREFIX}rp_save")
@require_permissions(permission=AppPermission(role=['platform_admin']))
@system_log(
    LogConfig(operation_type=OperationType.UPDATE, module=OperationModules.DATASOURCE,
              resource_id_expr="data_info.datasource_id"))
async def datasource_recommended(session: SessionDep, user: CurrentUser, data_info: RecommendedProblemBase):
    """
    是什么：datasource_recommended 是 backend/apps/datasource/api/recommended_problem.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 datasource_recommended 的语义处理数据源相关逻辑，并把结果返回或写入状态。
    """
    if not has_datasource_access(session, user, data_info.datasource_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    update_ds_recommended_config(session, data_info.datasource_id, data_info.recommended_config)
    return save_recommended_problem(session, user, data_info)
