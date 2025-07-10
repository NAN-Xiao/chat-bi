
from typing import Optional
from fastapi import Request
from fastapi.responses import JSONResponse
import jwt
from sqlmodel import Session
from starlette.middleware.base import BaseHTTPMiddleware
from common.core.db import engine 
from apps.system.crud.assistant import get_assistant_info
from apps.system.crud.user import get_user_info
from apps.system.schemas.system_schema import UserInfoDTO
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
            validate_pass, data, assistant = await self.validateAssistant(assistantToken)
            if validate_pass:
                request.state.current_user = data
                request.state.assistant = assistant
                return await call_next(request)
            return JSONResponse({"error": f"Unauthorized:[{data}]"}, status_code=401)
        #validate pass
        tokenkey = settings.TOKEN_KEY
        token = request.headers.get(tokenkey)
        validate_pass, data = await self.validateToken(token)
        if validate_pass:
            request.state.current_user = data
            return await call_next(request)
        return JSONResponse({"error": f"Unauthorized:[{data}]"}, status_code=401)
    
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
                return True, session_user
        except Exception as e:
            return False, e
            
    
    async def validateAssistant(self, assistantToken: Optional[str]):
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
                session_user = await get_user_info(session = session, user_id = token_data.id)
                session_user = UserInfoDTO.model_validate(session_user)
                assistant_info = get_assistant_info(session, payload['assistant_id'])
                return True, session_user, assistant_info
        except Exception as e:
            return False, e