

from sqlmodel import Session
from apps.system.models.system_model import AssistantModel
from apps.system.schemas.auth import CacheName, CacheNamespace
from common.core.sqlbot_cache import cache


@cache(namespace=CacheNamespace.EMBEDDED_INFO, cacheName=CacheName.ASSISTANT_INFO, keyExpression="assistant_id")
async def get_assistant_info(*, session: Session, assistant_id: int) -> AssistantModel | None:
    db_model = session.get(AssistantModel, assistant_id)
    return db_model