from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
# from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session
from apps.system.crud.user import get_user_info
from apps.system.schemas.system_schema import UserInfoDTO
from common.core.schemas import TokenPayload, XOAuth2PasswordBearer
from common.core import security
from common.core.config import settings
from common.core.db import get_session
from common.utils.locale import I18n
reusable_oauth2 = XOAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


    

SessionDep = Annotated[Session, Depends(get_session)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]
i18n = I18n()
async def get_i18n(request: Request):
    return i18n(request)

Trans = Annotated[I18n, Depends(get_i18n)]
async def get_current_user(session: SessionDep, token: TokenDep) -> UserInfoDTO:
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
    session_user = await get_user_info(session = session, user_id = token_data.id)
    session_user = UserInfoDTO.model_validate(session_user)
    if not session_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if session_user.status != 1:
        raise HTTPException(status_code=400, detail="Inactive user")
    return session_user
CurrentUser = Annotated[UserInfoDTO, Depends(get_current_user)]



