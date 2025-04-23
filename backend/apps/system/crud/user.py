
from sqlmodel import Session, select
from ..models.user import sys_user
from common.core.security import verify_md5pwd

def get_user_by_account(*, session: Session, account: str) -> sys_user | None:
    statement = select(sys_user).where(sys_user.account == account)
    session_user = session.exec(statement).first()
    return session_user

def authenticate(*, session: Session, account: str, password: str) -> sys_user | None:
    db_user = get_user_by_account(session=session, account=account)
    if not db_user:
        return None
    if not verify_md5pwd(password, db_user.password):
        return None
    return db_user