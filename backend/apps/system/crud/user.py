
from sqlmodel import Session, select
from ..models.user import sys_user, user_grid
from common.core.security import verify_md5pwd

def get_user_by_account(*, session: Session, account: str) -> sys_user | None:
    #statement = select(sys_user).where(sys_user.account == account)
    statement = select(user_grid.id, user_grid.account, user_grid.oid, user_grid.password).where(user_grid.account == account)
    session_user = session.exec(statement).first()
    result_user = sys_user.model_validate(session_user)
    return result_user

def authenticate(*, session: Session, account: str, password: str) -> sys_user | None:
    db_user = get_user_by_account(session=session, account=account)
    if not db_user:
        return None
    if not verify_md5pwd(password, db_user.password):
        return None
    return db_user