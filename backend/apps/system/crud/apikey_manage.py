
from sqlmodel import select

from apps.system.models.system_model import ApiKeyModel
from apps.system.schemas.auth import CacheName, CacheNamespace
from common.core.deps import SessionDep
from common.core.app_cache import cache, clear_cache
from common.utils.utils import AppLogUtil

@cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.ASK_INFO, keyExpression="access_key")
async def get_api_key(session: SessionDep, access_key: str) -> ApiKeyModel | None:
    """
    是什么：get_api_key 是 backend/apps/system/crud/apikey_manage.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    query = select(ApiKeyModel).where(ApiKeyModel.access_key == access_key)
    return session.exec(query).first()

@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.ASK_INFO, keyExpression="access_key")
async def clear_api_key_cache(access_key: str):
     """
     是什么：clear_api_key_cache 是 backend/apps/system/crud/apikey_manage.py 中的异步函数。
     谁调用：由后端业务代码、框架回调或测试代码按需调用。
     做了什么：删除或清理系统管理相关数据、缓存或临时状态。
     """
     AppLogUtil.info(f"Api key cache for [{access_key}] has been cleaned")