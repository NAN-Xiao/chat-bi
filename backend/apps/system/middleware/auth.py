
from typing import Optional
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
import jwt
from sqlmodel import Session
from starlette.middleware.base import BaseHTTPMiddleware
from apps.system.models.system_model import AssistantModel
from common.core.db import engine 
from apps.system.crud.assistant import get_assistant_info, get_assistant_user
from apps.system.crud.user import get_user_info
from apps.system.schemas.system_schema import AssistantHeader, UserInfoDTO
from common.core import security
from common.core.config import settings
from common.core.schemas import TokenPayload
from common.utils.whitelist import whiteUtils
from fastapi.security.utils import get_authorization_scheme_param
class TokenMiddleware(BaseHTTPMiddleware):
    
    
    
    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request, call_next):
        
        if self.is_options(request) or whiteUtils.is_whitelisted(request.url.path):
            return await call_next(request)
        assistantTokenKey = settings.ASSISTANT_TOKEN_KEY
        assistantToken = request.headers.get(assistantTokenKey)
        #if assistantToken and assistantToken.lower().startswith("assistant "):
        if assistantToken:
            validator: tuple[any] = await self.validateAssistant(assistantToken)
            if validator[0]:
                request.state.current_user = validator[1]
                request.state.assistant = validator[2]
                return await call_next(request)
            return JSONResponse({"msg": f"Unauthorized:[{validator[1]}]"}, status_code=401, headers={"Access-Control-Allow-Origin": "*"})
        #validate pass
        tokenkey = settings.TOKEN_KEY
        token = request.headers.get(tokenkey)
        validate_pass, data = await self.validateToken(token)
        if validate_pass:
            request.state.current_user = data
            return await call_next(request)
        return JSONResponse({"msg": f"Unauthorized:[{data}]"}, status_code=401, headers={"Access-Control-Allow-Origin": "*"})
    
    def is_options(self, request: Request):
        return request.method == "OPTIONS"
    
    async def validateToken(self, token: Optional[str]):
        if not token:
            return False, f"Miss Token[{settings.TOKEN_KEY}]!"
        schema, param = get_authorization_scheme_param(token)
        if schema.lower() != "bearer":
            return False, f"Token schema error!"
        payload = jwt.decode(
            param, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
        try: 
            with Session(engine) as session:
                session_user = await get_user_info(session = session, user_id = token_data.id)
                session_user = UserInfoDTO.model_validate(session_user)
                session_user = UserInfoDTO.model_validate(session_user)
                """ if token_data.oid != session_user.oid:
                    raise HTTPException(
                        status_code=401,
                        detail="Default space has been changed, please login again!"
                    ) """
                return True, session_user
        except Exception as e:
            return False, e
            
    
    async def validateAssistant(self, assistantToken: Optional[str]) -> tuple[any]:
        if not assistantToken:
            return False, f"Miss Token[{settings.TOKEN_KEY}]!"
        schema, param = get_authorization_scheme_param(assistantToken)
        if schema.lower() != "assistant":
            return False, f"Token schema error!"
        payload = jwt.decode(
            param, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
        if not payload['assistant_id']:
            return False, f"Miss assistant payload error!"
        try: 
            with Session(engine) as session:
                """ session_user = await get_user_info(session = session, user_id = token_data.id)
                session_user = UserInfoDTO.model_validate(session_user) """
                session_user = get_assistant_user(id = token_data.id)
                assistant_info = await get_assistant_info(session=session, assistant_id=payload['assistant_id'])
                assistant_info = AssistantModel.model_validate(assistant_info)
                assistant_info = AssistantHeader.model_validate(assistant_info.model_dump(exclude_unset=True))
                return True, session_user, assistant_info
        except Exception as e:
            return False, e