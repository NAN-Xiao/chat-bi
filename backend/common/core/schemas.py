from typing import Optional
from fastapi import HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlmodel import SQLModel
from starlette.status import HTTP_403_FORBIDDEN, HTTP_401_UNAUTHORIZED
from common.core.config import settings
from fastapi.security.utils import get_authorization_scheme_param
class TokenPayload(BaseModel):
    account: str | None = None
    id: int | None = None
    oid: int | None = None
    
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"
    
class XOAuth2PasswordBearer(OAuth2PasswordBearer):
    async def __call__(self, request: Request) -> Optional[str]:
        authorization = request.headers.get(settings.TOKEN_KEY)
        scheme, param = get_authorization_scheme_param(authorization)
        if not authorization or scheme.lower() != "bearer":
            if self.auto_error:
                raise HTTPException(
                    status_code=HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                return None
        return param