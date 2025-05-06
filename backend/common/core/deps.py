from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
# from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, ValidationError
from sqlmodel import Session, select
from common.core.schemas import TokenPayload, XOAuth2PasswordBearer
from common.core import security
from common.core.config import settings
from common.core.db import get_session
from apps.system.models.user import sys_user, user_grid
reusable_oauth2 = XOAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


    

SessionDep = Annotated[Session, Depends(get_session)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]

async def get_current_user(session: SessionDep, token: TokenDep) -> sys_user:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    statement = select(user_grid.id, user_grid.account, user_grid.oid, user_grid.password).where(user_grid.id == token_data.id)
    session_user = session.exec(statement).first()
    if not session_user:
        raise HTTPException(status_code=404, detail="User not found")
    user = sys_user.model_validate(session_user)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    """ if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user") """
    return user
CurrentUser = Annotated[sys_user, Depends(get_current_user)]



