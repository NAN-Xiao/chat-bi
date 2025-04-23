from fastapi import APIRouter, HTTPException
from apps.system.schemas.auth import LocalLoginSchema
from common.core.deps import SessionDep
from ..crud.user import authenticate
from common.core.security import create_access_token
from datetime import timedelta
from common.core.config import settings

router = APIRouter(tags=["login"])

@router.post("/localLogin")
def local_login(
    session: SessionDep,
    schema: LocalLoginSchema,
) -> str:
    user = authenticate(session=session, account=schema.account, password=schema.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect account or password")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return create_access_token(
        user.id, expires_delta=access_token_expires
    )