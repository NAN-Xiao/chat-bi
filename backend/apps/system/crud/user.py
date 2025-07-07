
from sqlmodel import Session, select

from apps.system.schemas.system_schema import BaseUserDTO
from ..models.user import UserModel
from common.core.security import verify_md5pwd

def get_db_user(*, session: Session, user_id: int) -> UserModel:
    db_user = session.get(UserModel, user_id)
    if not db_user:
        raise RuntimeError("user not exist")
    return db_user

def get_user_by_account(*, session: Session, account: str) -> BaseUserDTO | None:
    statement = select(UserModel).where(UserModel.account == account)
    db_user = session.exec(statement).first()
    if not db_user:
        return None
    return BaseUserDTO.model_validate(db_user.model_dump())

def get_user_info(*, session: Session, user_id: int) -> BaseUserDTO | None:
    db_user = get_db_user(session = session, user_id = user_id)
    return BaseUserDTO.model_validate(db_user.model_dump())

def authenticate(*, session: Session, account: str, password: str) -> BaseUserDTO | None:
    db_user = get_user_by_account(session=session, account=account)
    if not db_user:
        return None
    if not verify_md5pwd(password, db_user.password):
        return None
    return db_user