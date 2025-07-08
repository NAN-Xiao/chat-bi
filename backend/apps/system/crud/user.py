
from sqlmodel import Session, select

from apps.system.models.system_model import UserWsModel
from apps.system.schemas.auth import CacheName, CacheNamespace
from apps.system.schemas.system_schema import BaseUserDTO, UserInfoDTO
from common.core.sqlbot_cache import cache
from ..models.user import UserModel
from common.core.security import verify_md5pwd

def get_db_user(*, session: Session, user_id: int) -> UserModel:
    db_user = session.get(UserModel, user_id)
    return db_user

def get_user_by_account(*, session: Session, account: str) -> BaseUserDTO | None:
    statement = select(UserModel).where(UserModel.account == account)
    db_user = session.exec(statement).first()
    if not db_user:
        return None
    return BaseUserDTO.model_validate(db_user.model_dump())

@cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="user_id")
async def get_user_info(*, session: Session, user_id: int) -> UserInfoDTO | None:
    db_user: UserModel = get_db_user(session = session, user_id = user_id)
    userInfo = UserInfoDTO.model_validate(db_user.model_dump())
    userInfo.isAdmin = userInfo.id == 1 and userInfo.account == 'admin'
    if userInfo.isAdmin:
        return userInfo
    ws_model: UserWsModel = session.exec(select(UserWsModel).where(UserWsModel.uid == userInfo.id, UserWsModel.oid == userInfo.oid)).first()
    userInfo.weight = ws_model.weight if ws_model else -1
    return userInfo

def authenticate(*, session: Session, account: str, password: str) -> BaseUserDTO | None:
    db_user = get_user_by_account(session=session, account=account)
    if not db_user:
        return None
    if not verify_md5pwd(password, db_user.password):
        return None
    return db_user