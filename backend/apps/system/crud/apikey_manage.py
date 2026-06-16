
from sqlmodel import select

from apps.system.models.system_model import ApiKeyModel
from apps.system.schemas.auth import CacheName, CacheNamespace
from common.core.deps import SessionDep
from common.core.app_cache import cache, clear_cache
from common.utils.utils import AppLogUtil

@cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.ASK_INFO, keyExpression="access_key")
async def get_api_key(session: SessionDep, access_key: str) -> ApiKeyModel | None:
    query = select(ApiKeyModel).where(ApiKeyModel.access_key == access_key)
    return session.exec(query).first()

@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.ASK_INFO, keyExpression="access_key")
async def clear_api_key_cache(access_key: str):
     AppLogUtil.info(f"Api key cache for [{access_key}] has been cleaned")