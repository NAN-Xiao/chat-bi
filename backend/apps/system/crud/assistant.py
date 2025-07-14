

from sqlmodel import Session, select
from apps.datasource.models.datasource import CoreDatasource
from apps.system.models.system_model import AssistantModel
from apps.system.schemas.auth import CacheName, CacheNamespace
from apps.system.schemas.system_schema import UserInfoDTO
from common.core.sqlbot_cache import cache


@cache(namespace=CacheNamespace.EMBEDDED_INFO, cacheName=CacheName.ASSISTANT_INFO, keyExpression="assistant_id")
async def get_assistant_info(*, session: Session, assistant_id: int) -> AssistantModel | None:
    db_model = session.get(AssistantModel, assistant_id)
    return db_model

def get_assistant_user(*, id: int):
    return UserInfoDTO(id=id, account="sqlbot-inner-assistant", oid=1, name="sqlbot-inner-assistant", email="sqlbot-inner-assistant@sqlbot.com")

def get_assistant_ds(*, session: Session, assistant: AssistantModel):
    type = assistant.type
    if type == 0:
        db_ds_list = session.exec(select(CoreDatasource.id, CoreDatasource.name, CoreDatasource.description)).all()
        # filter private ds if offline
        return db_ds_list
    pass
