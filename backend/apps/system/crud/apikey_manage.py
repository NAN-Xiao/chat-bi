"""
脚本说明：这个脚本封装系统管理的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""

from sqlmodel import select

from apps.system.models.system_model import ApiKeyModel
from apps.system.schemas.auth import CacheName, CacheNamespace
from common.core.deps import SessionDep
from common.core.app_cache import cache, clear_cache
from common.utils.utils import AppLogUtil

@cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.ASK_INFO, keyExpression="access_key")
async def get_api_key(session: SessionDep, access_key: str) -> ApiKeyModel | None:
    """
    是什么：get_api_key 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    query = select(ApiKeyModel).where(ApiKeyModel.access_key == access_key)
    return session.exec(query).first()

@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.ASK_INFO, keyExpression="access_key")
async def clear_api_key_cache(access_key: str, session: SessionDep | None = None):
     """
     是什么：clear_api_key_cache 是一个可以复用的小步骤，负责系统管理相关的一件事。
     谁调用：后端其他代码在需要这个功能时会调用它。
     做了什么：把系统管理不再需要的数据、缓存或临时内容清理掉。
     """
     AppLogUtil.info(f"Api key cache for [{access_key}] has been cleaned")
