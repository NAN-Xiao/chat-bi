"""
脚本说明：这个脚本放系统管理的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
import json
import os
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.responses import StreamingResponse


async def get_assistant_info(**kwargs):
    """
    是什么：get_assistant_info 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    from apps.system.crud.assistant import get_assistant_info as get_cached_assistant_info

    return await get_cached_assistant_info(**kwargs)


from sqlmodel import select

from apps.datasource.crud.binding import get_bound_datasource_id_for_tenant
from apps.datasource.models.datasource import CoreDatasource
from apps.db.constant import DB
from apps.swagger.i18n import PLACEHOLDER_PREFIX
from apps.system.crud.assistant_manage import dynamic_upgrade_cors, save
from apps.system.crud.user import is_platform_admin, is_platform_workspace_delegate
from apps.system.models.system_model import AssistantModel
from apps.system.schemas.access_context import require_tenant_id
from apps.system.schemas.business_access import require_chatbi_business_user
from apps.system.schemas.auth import CacheName, CacheNamespace
from apps.system.schemas.permission import AppPermission, require_permissions
from apps.system.schemas.system_schema import AssistantBase, AssistantDTO, AssistantPublicInfo, AssistantValidator
from common.core.config import settings
from common.core.deps import CurrentAssistant, SessionDep, Trans, CurrentUser
from common.core.security import create_access_token
from common.core.app_cache import clear_cache
from common.utils.file_utils import AppFileUtils
from common.utils.utils import get_origin_from_referer, origin_match_domain

router = APIRouter(tags=["system_assistant"], prefix="/system/assistant")
from common.audit.models.log_model import OperationType, OperationModules
from common.audit.schemas.logger_decorator import LogConfig, system_log


PUBLIC_CONFIGURATION_KEYS = {
    "name",
    "welcome",
    "welcome_desc",
    "theme",
    "header_font_color",
    "logo",
    "auto_ds",
    "show_guide",
    "float_icon",
    "float_icon_drag",
    "x_type",
    "y_type",
    "x_val",
    "y_val",
}


def _current_tenant_id(current_user: CurrentUser) -> int:
    """
    是什么：_current_tenant_id 是从当前用户里取租户 ID 的小工具。
    谁调用：需要知道当前用户属于哪个租户的接口会调用它。
    做了什么：把用户上下文里的租户 ID 取出来，方便后面做权限和数据隔离。
    """
    return require_tenant_id(getattr(current_user, "tenant_id", None))


def _can_manage_all_assistants(current_user: CurrentUser) -> bool:
    """
    是什么：_can_manage_all_assistants 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return is_platform_admin(current_user) and not is_platform_workspace_delegate(current_user)


def _tenant_scoped_assistant_statement(statement, current_user: CurrentUser):
    """
    是什么：_tenant_scoped_assistant_statement 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if _can_manage_all_assistants(current_user):
        return statement
    return statement.where(AssistantModel.tenant_id == _current_tenant_id(current_user))


def _get_manageable_assistant(session: SessionDep, current_user: CurrentUser, assistant_id: int) -> AssistantModel:
    """
    是什么：_get_manageable_assistant 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    db_model = session.get(AssistantModel, assistant_id)
    if not db_model:
        raise HTTPException(status_code=404, detail=f"AssistantModel with id {assistant_id} not found")
    if (
        not _can_manage_all_assistants(current_user)
        and (
            getattr(db_model, "tenant_id", None) in (None, "")
            or int(db_model.tenant_id) != _current_tenant_id(current_user)
        )
    ):
        raise HTTPException(status_code=404, detail=f"AssistantModel with id {assistant_id} not found")
    return db_model


def _model_tenant_id(db_model: AssistantModel) -> int:
    """
    是什么：_model_tenant_id 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    tenant_id = getattr(db_model, "tenant_id", None)
    if tenant_id in (None, ""):
        raise HTTPException(status_code=403, detail="Assistant tenant is required")
    return int(tenant_id)


def _assistant_tenant_id(current_assistant: CurrentAssistant) -> int:
    """
    是什么：_assistant_tenant_id 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return require_tenant_id(getattr(current_assistant, "tenant_id", None))


def _public_assistant_info(db_model: AssistantModel, include_certificate: bool = False) -> AssistantPublicInfo:
    """
    是什么：_public_assistant_info 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    data = db_model.model_dump(exclude={"app_secret"})
    try:
        configuration = json.loads(data.get("configuration") or "{}")
        allowed_keys = set(PUBLIC_CONFIGURATION_KEYS)
        if include_certificate:
            allowed_keys.add("certificate")
        public_configuration = {
            key: configuration[key]
            for key in allowed_keys
            if key in configuration
        }
        data["configuration"] = json.dumps(public_configuration, ensure_ascii=False)
    except Exception:
        data["configuration"] = "{}"
    return AssistantPublicInfo.model_validate(data)


@router.get("/info/{id}", include_in_schema=False)
async def info(request: Request, response: Response, session: SessionDep, trans: Trans, id: int) -> AssistantPublicInfo:
    """
    是什么：info 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not id:
        raise Exception('miss assistant id')
    db_model = await get_assistant_info(session=session, assistant_id=id)
    if not db_model:
        raise RuntimeError(f"assistant application not exist")
    db_model = AssistantModel.model_validate(db_model)

    origin = request.headers.get("origin") or get_origin_from_referer(request)
    if not origin:
        raise RuntimeError(trans('i18n_embedded.invalid_origin', origin=origin or ''))
    origin = origin.rstrip('/')
    if not origin_match_domain(origin, db_model.domain):
        raise RuntimeError(trans('i18n_embedded.invalid_origin', origin=origin or ''))

    response.headers["Access-Control-Allow-Origin"] = origin
    return _public_assistant_info(db_model, include_certificate=True)


@router.get("/app/{appId}", include_in_schema=False)
async def getApp(request: Request, response: Response, session: SessionDep, trans: Trans, appId: str) -> AssistantPublicInfo:
    """
    是什么：getApp 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    if not appId:
        raise Exception('miss assistant appId')
    db_model = session.exec(select(AssistantModel).where(AssistantModel.app_id == appId)).first()
    if not db_model:
        raise RuntimeError(f"assistant application not exist")
    db_model = AssistantModel.model_validate(db_model)
    origin = request.headers.get("origin") or get_origin_from_referer(request)
    if not origin:
        raise RuntimeError(trans('i18n_embedded.invalid_origin', origin=origin or ''))
    origin = origin.rstrip('/')
    if not origin_match_domain(origin, db_model.domain):
        raise RuntimeError(trans('i18n_embedded.invalid_origin', origin=origin or ''))

    response.headers["Access-Control-Allow-Origin"] = origin
    return _public_assistant_info(db_model, include_certificate=True)


@router.get("/validator", response_model=AssistantValidator, include_in_schema=False)
async def validator(session: SessionDep, id: int, virtual: Optional[int] = Query(None), online: Optional[bool] = Query(False)):
    """
    是什么：validator 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not id:
        raise Exception('miss assistant id')

    db_model = await get_assistant_info(session=session, assistant_id=id)
    if not db_model:
        return AssistantValidator()
    db_model = AssistantModel.model_validate(db_model)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    # 保留查询参数用于兼容前端，但不要把它当作认证信号。
    _ = online
    assistantDict = {
        "id": virtual,
        "account": 'shuzhi-inner-assistant',
        "assistant_id": id,
        "assistant_online": False,
        "tenant_id": _model_tenant_id(db_model),
    }
    access_token = create_access_token(
        assistantDict, expires_delta=access_token_expires
    )
    return AssistantValidator(True, True, True, access_token)


@router.get('/picture/{file_id}', summary=f"{PLACEHOLDER_PREFIX}assistant_picture_api", description=f"{PLACEHOLDER_PREFIX}assistant_picture_api")
async def picture(file_id: str = Path(description="file_id")):
    """
    是什么：picture 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    file_path = AppFileUtils.get_file_path(file_id=file_id)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    if file_id.lower().endswith(".svg"):
        media_type = "image/svg+xml"
    else:
        media_type = "image/jpeg"

    def iterfile():
        """
        是什么：iterfile 是一个可以复用的小步骤，负责系统管理相关的一件事。
        谁调用：外层函数 picture 跑到对应步骤时会调用它。
        做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        with open(file_path, mode="rb") as f:
            yield from f

    return StreamingResponse(iterfile(), media_type=media_type)


@clear_cache(namespace=CacheNamespace.EMBEDDED_INFO, cacheName=CacheName.ASSISTANT_INFO, keyExpression="id")
async def clear_ui_cache(id: int):
    """
    是什么：clear_ui_cache 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理不再需要的数据、缓存或临时内容清理掉。
    """
    pass

@router.get("/ds", include_in_schema=False, response_model=list[dict])
async def ds(session: SessionDep, current_assistant: CurrentAssistant):
    """
    是什么：ds 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if current_assistant.type == 0:
        online = current_assistant.online
        configuration = current_assistant.configuration
        config: dict[any] = json.loads(configuration)
        datasource_id = get_bound_datasource_id_for_tenant(session, _assistant_tenant_id(current_assistant))
        if datasource_id is None:
            return []
        stmt = (
            select(
                CoreDatasource.id,
                CoreDatasource.name,
                CoreDatasource.description,
                CoreDatasource.type,
                CoreDatasource.type_name,
                CoreDatasource.num,
            )
            .where(CoreDatasource.id == datasource_id)
        )
        if not online:
            public_list: list[int] = config.get('public_list') or None
            if public_list:
                stmt = stmt.where(CoreDatasource.id.in_(public_list))
            else:
                return []
        db_ds_list = session.exec(stmt)
        return [
            {
                "id": ds.id,
                "name": ds.name,
                "description": ds.description,
                "type": ds.type,
                "type_name": ds.type_name,
                "num": ds.num,
            }
            for ds in db_ds_list]
    if current_assistant.type == 1:
        from apps.system.crud.assistant import AssistantOutDsFactory

        out_ds_instance = AssistantOutDsFactory.get_instance(current_assistant)
        return [
            {
                "id": str(ds.id),
                "name": ds.name,
                "description": ds.description or ds.comment,
                "type": ds.type,
                "type_name": get_db_type(ds.type),
                "num": len(ds.tables) if ds.tables else 0,
            }
            for ds in out_ds_instance.ds_list
            if get_db_type(ds.type)
        ]

    return None

def get_db_type(type):
    """
    是什么：get_db_type 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    try:
        db = DB.get_db(type)
        return db.db_name
    except Exception:
        return None


@router.get(
    "",
    response_model=list[AssistantModel],
    summary=f"{PLACEHOLDER_PREFIX}assistant_grid_api",
    description=f"{PLACEHOLDER_PREFIX}assistant_grid_api",
    dependencies=[Depends(require_chatbi_business_user)],
)
@require_permissions(permission=AppPermission(role=['admin']))
async def query(session: SessionDep, current_user: CurrentUser):
    """
    是什么：query 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    statement = (
        select(AssistantModel)
        .where(AssistantModel.type != 4)
        .order_by(AssistantModel.name, AssistantModel.create_time)
    )
    list_result = session.exec(_tenant_scoped_assistant_statement(statement, current_user)).all()
    for model in list_result:
        model.enable_custom_model = model.enable_custom_model or False
    return list_result


@router.get(
    "/advanced_application",
    response_model=list[AssistantModel],
    include_in_schema=False,
    dependencies=[Depends(require_chatbi_business_user)],
)
@require_permissions(permission=AppPermission(role=['admin']))
async def query_advanced_application(session: SessionDep, current_user: CurrentUser):
    """
    是什么：query_advanced_application 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    statement = (
        select(AssistantModel)
        .where(AssistantModel.type == 1)
        .order_by(AssistantModel.name, AssistantModel.create_time)
    )
    list_result = session.exec(_tenant_scoped_assistant_statement(statement, current_user)).all()
    return list_result


@router.post(
    "",
    summary=f"{PLACEHOLDER_PREFIX}assistant_create_api",
    description=f"{PLACEHOLDER_PREFIX}assistant_create_api",
    dependencies=[Depends(require_chatbi_business_user)],
)
@require_permissions(permission=AppPermission(role=['admin']))
@system_log(LogConfig(operation_type=OperationType.CREATE, module=OperationModules.APPLICATION, result_id_expr="id"))
async def add(request: Request, session: SessionDep, current_user: CurrentUser, creator: AssistantBase):
    """
    是什么：add 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    return await save(request, session, creator, tenant_id=_current_tenant_id(current_user))


@router.put(
    "",
    summary=f"{PLACEHOLDER_PREFIX}assistant_update_api",
    description=f"{PLACEHOLDER_PREFIX}assistant_update_api",
    dependencies=[Depends(require_chatbi_business_user)],
)
@require_permissions(permission=AppPermission(role=['admin']))
@clear_cache(namespace=CacheNamespace.EMBEDDED_INFO, cacheName=CacheName.ASSISTANT_INFO, keyExpression="editor.id")
@system_log(LogConfig(operation_type=OperationType.UPDATE, module=OperationModules.APPLICATION, resource_id_expr="editor.id"))
async def update(request: Request, session: SessionDep, current_user: CurrentUser, editor: AssistantDTO):
    """
    是什么：update 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理相关的信息改成最新状态，并保存这些变化。
    """
    id = editor.id
    db_model = _get_manageable_assistant(session, current_user, id)
    update_data = editor.model_dump(exclude_unset=True, exclude={"id"})
    db_model.sqlmodel_update(update_data)
    session.add(db_model)
    session.commit()
    dynamic_upgrade_cors(request=request, session=session)


@router.get(
    "/{id}",
    response_model=AssistantPublicInfo,
    summary=f"{PLACEHOLDER_PREFIX}assistant_query_api",
    description=f"{PLACEHOLDER_PREFIX}assistant_query_api",
    dependencies=[Depends(require_chatbi_business_user)],
)
async def get_one(session: SessionDep, current_user: CurrentUser, id: int = Path(description="ID")) -> AssistantPublicInfo:
    """
    是什么：get_one 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    db_model = _get_manageable_assistant(session, current_user, id)
    return _public_assistant_info(db_model)


@router.delete(
    "/{id}",
    summary=f"{PLACEHOLDER_PREFIX}assistant_del_api",
    description=f"{PLACEHOLDER_PREFIX}assistant_del_api",
    dependencies=[Depends(require_chatbi_business_user)],
)
@require_permissions(permission=AppPermission(role=['admin']))
@clear_cache(namespace=CacheNamespace.EMBEDDED_INFO, cacheName=CacheName.ASSISTANT_INFO, keyExpression="id")
@system_log(LogConfig(operation_type=OperationType.DELETE, module=OperationModules.APPLICATION, resource_id_expr="id"))
async def delete(request: Request, session: SessionDep, current_user: CurrentUser, id: int = Path(description="ID")):
    """
    是什么：delete 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理不再需要的数据、缓存或临时内容清理掉。
    """
    db_model = _get_manageable_assistant(session, current_user, id)
    session.delete(db_model)
    session.commit()
    dynamic_upgrade_cors(request=request, session=session)

