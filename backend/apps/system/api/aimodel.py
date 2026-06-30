"""
脚本说明：这个脚本放系统管理的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
import json

import httpx
from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import BigInteger, Text, case, cast
from sqlmodel import func, select, update

from apps.ai_model.model_factory import LLMConfig, LLMFactory, _normalize_api_base_url
from apps.chat.models.chat_model import ChatLog
from apps.swagger.i18n import PLACEHOLDER_PREFIX
from apps.system.crud.aimodel_manage import get_ai_model_list
from apps.system.models.system_model import AiModelBrief, AiModelDetail
from apps.system.schemas.ai_model_schema import (
    AiModelConfigItem,
    AiModelCreator,
    AiModelEditor,
    AiModelGridItem,
    AiModelRemoteListRequest,
    AiModelRemoteModel,
)
from apps.system.schemas.permission import AppPermission, require_permissions
from common.audit.models.log_model import OperationModules, OperationType
from common.audit.schemas.logger_decorator import LogConfig, system_log
from common.core.deps import CurrentUser, SessionDep, Trans
from common.utils.crypto import shuzhi_decrypt, shuzhi_encrypt
from common.utils.time import get_timestamp
from common.utils.utils import AppLogUtil, prepare_model_arg

router = APIRouter(tags=["system_model"], prefix="/system/aimodel")


async def _encrypt_ai_model_secrets(data: dict) -> dict:
    """
    是什么：_encrypt_ai_model_secrets 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    encrypted = dict(data)
    for key in ("api_key", "api_domain"):
        if key in encrypted and encrypted[key] is not None:
            encrypted[key] = await shuzhi_encrypt(encrypted[key])
    return encrypted


def _chat_log_total_tokens_expr():
    """
    是什么：_chat_log_total_tokens_expr 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    token_usage_type = func.jsonb_typeof(ChatLog.token_usage)
    object_total_tokens = cast(
        func.coalesce(func.nullif(ChatLog.token_usage.op("->>")("total_tokens"), ""), "0"),
        BigInteger,
    )
    number_total_tokens = cast(cast(ChatLog.token_usage, Text), BigInteger)
    return case(
        (token_usage_type == "object", object_total_tokens),
        (token_usage_type == "number", number_total_tokens),
        else_=0,
    )


def _extract_remote_models(payload: object) -> list[AiModelRemoteModel]:
    """
    是什么：_extract_remote_models 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if isinstance(payload, dict):
        raw_models = payload.get("data") or payload.get("models") or []
    elif isinstance(payload, list):
        raw_models = payload
    else:
        raw_models = []

    models: list[AiModelRemoteModel] = []
    seen: set[str] = set()
    for item in raw_models:
        if isinstance(item, dict):
            model_id = item.get("id") or item.get("name") or item.get("model")
        else:
            model_id = item
        if model_id is None:
            continue
        model_name = str(model_id).strip()
        if not model_name or model_name in seen:
            continue
        seen.add(model_name)
        models.append(AiModelRemoteModel(id=model_name, name=model_name))
    return sorted(models, key=lambda model: model.name.lower())


@router.post("/models", response_model=list[AiModelRemoteModel], include_in_schema=False)
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def list_remote_models(info: AiModelRemoteListRequest, trans: Trans):
    """
    是什么：list_remote_models 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    try:
        base_url = _normalize_api_base_url(info.api_domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    models_url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {info.api_key.strip()}"} if info.api_key else {}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(models_url, headers=headers)
            response.raise_for_status()
        return _extract_remote_models(response.json())
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch model list from /models: {detail}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch model list from /models: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid /models response.") from exc


@router.post("/status", include_in_schema=False)
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def check_llm(info: AiModelCreator, trans: Trans):
    """
    是什么：check_llm 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    async def generate():
        """
        是什么：generate 是一个可以复用的小步骤，负责系统管理相关的一件事。
        谁调用：外层函数 check_llm 跑到对应步骤时会调用它。
        做了什么：根据已有信息生成系统管理的结果，比如答案、SQL、图表或建议。
        """
        try:
            additional_params = {item.key: prepare_model_arg(item.val) for item in info.config_list if
                                 item.key and item.val}
            config = LLMConfig(
                model_type="openai" if info.protocol == 1 else "vllm",
                model_name=info.base_model,
                api_key=info.api_key,
                api_base_url=_normalize_api_base_url(info.api_domain),
                additional_params=additional_params,
            )
            llm_instance = LLMFactory.create_llm(config)
            async for chunk in llm_instance.llm.astream("1+1=?"):
                AppLogUtil.info(chunk)
                if chunk and isinstance(chunk, str):
                    yield json.dumps({"content": chunk}) + "\n"
                if chunk and isinstance(chunk, dict) and chunk.content:
                    yield json.dumps({"content": chunk.content}) + "\n"

        except Exception as e:
            AppLogUtil.error(f"Error checking LLM: {e}")
            error_msg = trans('i18n_llm.validate_error', msg=str(e))
            yield json.dumps({"error": error_msg}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.get("/default", include_in_schema=False)
async def check_default(session: SessionDep, trans: Trans):
    """
    是什么：check_default 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    db_model = session.exec(
        select(AiModelDetail).where(AiModelDetail.default_model)
    ).first()
    if not db_model:
        raise Exception(trans('i18n_llm.miss_default'))


@router.put("/default/{id}", summary=f"{PLACEHOLDER_PREFIX}system_model_default",
            description=f"{PLACEHOLDER_PREFIX}system_model_default")
@require_permissions(permission=AppPermission(role=['platform_admin']))
@system_log(LogConfig(operation_type=OperationType.UPDATE, module=OperationModules.AI_MODEL, resource_id_expr="id"))
async def set_default(session: SessionDep, id: int = Path(description="ID")):
    """
    是什么：set_default 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理相关的信息改成最新状态，并保存这些变化。
    """
    db_model = session.get(AiModelDetail, id)
    if not db_model:
        raise ValueError(f"AiModelDetail with id {id} not found")
    if db_model.default_model:
        return

    try:
        session.exec(
            update(AiModelDetail).values(default_model=False)
        )
        db_model.default_model = True
        session.add(db_model)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e


@router.get("", response_model=list[AiModelGridItem], summary=f"{PLACEHOLDER_PREFIX}system_model_grid",
            description=f"{PLACEHOLDER_PREFIX}system_model_grid")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def query(
        session: SessionDep,
        keyword: str | None = Query(default=None, max_length=255, description=f"{PLACEHOLDER_PREFIX}keyword")
):
    """
    是什么：query 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    statement = (
        select(
            AiModelDetail.id,
            AiModelDetail.name,
            AiModelDetail.model_type,
            AiModelDetail.base_model,
            AiModelDetail.supplier,
            AiModelDetail.protocol,
            AiModelDetail.default_model,
        )
    )
    if keyword is not None:
        statement = statement.where(AiModelDetail.name.like(f"%{keyword}%"))
    statement = statement.order_by(AiModelDetail.default_model.desc(), AiModelDetail.name, AiModelDetail.create_time)
    items = session.exec(statement).all()
    model_ids = [item.id for item in items]
    usage_map: dict[int, dict[str, int]] = {}
    if model_ids:
        usage_rows = session.exec(
            select(
                ChatLog.ai_modal_id,
                func.count(ChatLog.id),
                func.coalesce(func.sum(_chat_log_total_tokens_expr()), 0),
            )
            .where(ChatLog.ai_modal_id.in_(model_ids))
            .group_by(ChatLog.ai_modal_id)
        ).all()
        usage_map = {
            int(model_id): {
                "usage_count": int(usage_count or 0),
                "total_tokens": int(total_tokens or 0),
            }
            for model_id, usage_count, total_tokens in usage_rows
            if model_id is not None
        }
    return [
        AiModelGridItem(
            **item._asdict(),
            **usage_map.get(int(item.id), {}),
        )
        for item in items
    ]


@router.get("/{id}", response_model=AiModelEditor, summary=f"{PLACEHOLDER_PREFIX}system_model_query",
            description=f"{PLACEHOLDER_PREFIX}system_model_query")
@require_permissions(permission=AppPermission(role=['platform_admin']))
async def get_model_by_id(
        session: SessionDep,
        id: int = Path(description="ID")
):
    """
    是什么：get_model_by_id 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    db_model = session.get(AiModelDetail, id)
    if not db_model:
        raise ValueError(f"AiModelDetail with id {id} not found")

    config_list: list[AiModelConfigItem] = []
    if db_model.config:
        try:
            raw = json.loads(db_model.config)
            config_list = [AiModelConfigItem(**item) for item in raw]
        except Exception:
            pass
    data = AiModelDetail.model_validate(db_model).model_dump(exclude_unset=True)
    try:
        if db_model.api_key:
            data["api_key"] = await shuzhi_decrypt(db_model.api_key)
        if db_model.api_domain:
            data["api_domain"] = await shuzhi_decrypt(db_model.api_domain)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail="AI model sensitive configuration cannot be decrypted.",
        ) from exc
    except Exception:
        pass
    data.pop("config", None)
    data["config_list"] = config_list
    return AiModelEditor(**data)


@router.post("", summary=f"{PLACEHOLDER_PREFIX}system_model_create",
             description=f"{PLACEHOLDER_PREFIX}system_model_create")
@require_permissions(permission=AppPermission(role=['platform_admin']))
@system_log(LogConfig(operation_type=OperationType.CREATE, module=OperationModules.AI_MODEL, result_id_expr="id"))
async def add_model(
        session: SessionDep,
        creator: AiModelCreator
):
    """
    是什么：add_model 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    data = creator.model_dump(exclude_unset=True)
    data["config"] = json.dumps([item.model_dump(exclude_unset=True) for item in creator.config_list])
    data.pop("config_list", None)
    data = await _encrypt_ai_model_secrets(data)
    detail = AiModelDetail.model_validate(data)
    detail.create_time = get_timestamp()
    count = session.exec(select(func.count(AiModelDetail.id))).one()
    if count == 0:
        detail.default_model = True
    session.add(detail)
    session.commit()
    return detail


@router.put("", summary=f"{PLACEHOLDER_PREFIX}system_model_update",
            description=f"{PLACEHOLDER_PREFIX}system_model_update")
@require_permissions(permission=AppPermission(role=['platform_admin']))
@system_log(
    LogConfig(operation_type=OperationType.UPDATE, module=OperationModules.AI_MODEL, resource_id_expr="editor.id"))
async def update_model(
        session: SessionDep,
        editor: AiModelEditor
):
    """
    是什么：update_model 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理相关的信息改成最新状态，并保存这些变化。
    """
    id = int(editor.id)
    data = editor.model_dump(exclude_unset=True)
    data["config"] = json.dumps([item.model_dump(exclude_unset=True) for item in editor.config_list])
    data.pop("config_list", None)
    data = await _encrypt_ai_model_secrets(data)
    db_model = session.get(AiModelDetail, id)
    # update_data = AiModelDetail.model_validate(data)
    db_model.sqlmodel_update(data)
    session.add(db_model)
    session.commit()


@router.delete("/{id}", summary=f"{PLACEHOLDER_PREFIX}system_model_del",
               description=f"{PLACEHOLDER_PREFIX}system_model_del")
@require_permissions(permission=AppPermission(role=['platform_admin']))
@system_log(LogConfig(operation_type=OperationType.DELETE, module=OperationModules.AI_MODEL, resource_id_expr="id"))
async def delete_model(
        session: SessionDep,
        trans: Trans,
        id: int = Path(description="ID")
):
    """
    是什么：delete_model 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理不再需要的数据、缓存或临时内容清理掉。
    """
    item = session.get(AiModelDetail, id)
    if item.default_model:
        raise Exception(trans('i18n_llm.delete_default_error', key=item.name))
    session.delete(item)
    session.commit()


@router.get("/list/available", response_model=list[AiModelBrief], summary=f"{PLACEHOLDER_PREFIX}system_model_list_available",
            description=f"{PLACEHOLDER_PREFIX}system_model_list_available")
async def get_available_models(
        session: SessionDep,
        _current_user: CurrentUser
):
    """
    是什么：get_available_models 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    return get_ai_model_list(session, False)
