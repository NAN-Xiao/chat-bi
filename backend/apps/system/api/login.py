from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from apps.system.schemas.system_schema import BaseUserDTO
from common.core.deps import SessionDep
from ..crud.user import authenticate
from common.core.security import create_access_token
from datetime import timedelta
from common.core.config import settings
from common.core.schemas import Token
router = APIRouter(tags=["login"], prefix="/login")

@router.post("/access-token")
def local_login(
    session: SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Token:
    user: BaseUserDTO = authenticate(session=session, account=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect account or password")
    
    if not user.oid or user.oid == 0:
        raise HTTPException(status_code=400, detail="No associated workspace, Please contact the administrator")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    user_dict = user.to_dict()
    return Token(access_token=create_access_token(
        user_dict, expires_delta=access_token_expires
    ))